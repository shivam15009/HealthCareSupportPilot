import json
import math
import re
from collections import Counter

from flask import Flask, request, jsonify, render_template

from classifier import classify_query

from priority import (
    operational_severity,
    operational_priority
)

from database import (
    init_db,
    save_ticket,
    get_ticket,
    update_ticket_status,
    get_connection,
    update_ticket_escalation_reasons,
    update_ticket_ai_resolved,
)

from rag.pipeline import run_pipeline


app = Flask(__name__)


HUMAN_REQUEST_INTENTS = (
    "human",
    "person",
    "agent",
    "representative",
    "escalate",
    "talk to someone",
    "call me",
)

ESCALATION_RULES = {
    "critical_priority": "Escalated due to Critical Priority / Severity",
    "low_confidence": "Escalated due to Confidence < 70%",
    "human_intent": "Escalated due to Human-Routing Intent",
    "no_knowledge_evidence": "Escalated due to No Relevant Knowledge Evidence",
}


def get_escalation_reasons(description, priority, confidence, severity=None):
    """Return every safety rule triggered by a ticket."""
    reasons = []
    normalized_priority = str(priority or "").strip().casefold()
    if "p1" in normalized_priority or "critical" in normalized_priority:
        reasons.append("critical_priority")

    if str(severity or "").strip().casefold() == "critical":
        reasons.append("critical_priority")

    try:
        confidence_value = float(confidence)
    except (TypeError, ValueError):
        confidence_value = 0.0

    # The classifier stores percentages (e.g. 70 means 70%, or 0.70).
    confidence_fraction = confidence_value / 100
    if not math.isfinite(confidence_fraction) or confidence_fraction < 0.70:
        reasons.append("low_confidence")

    normalized_description = re.sub(
        r"[^a-z0-9]+",
        " ",
        (description or "").casefold()
    ).strip()
    padded_description = f" {normalized_description} "
    if any(
        f" {intent} " in padded_description
        for intent in HUMAN_REQUEST_INTENTS
    ):
        reasons.append("human_intent")

    return sorted(set(reasons))


def requires_human_escalation(
    description,
    priority,
    confidence,
    severity=None,
):
    """Compatibility wrapper for callers using the previous boolean helper."""
    return bool(
        get_escalation_reasons(
            description,
            priority,
            confidence,
            severity,
        )
    )


# ============================================================
# DATABASE INITIALIZATION
# ============================================================

init_db()


# ============================================================
# PAGE ROUTES
# ============================================================

@app.route("/")
def home():
    """Milestone 1 - Ticket Classification page."""
    return render_template("tickets.html")


@app.route("/rag")
def rag_page():
    """Milestone 2 - AI Resolution / RAG page."""
    return render_template("rag.html")


@app.route("/dashboard")
@app.route("/analytics")
def dashboard_page():
    """Render dashboard and analytics tabs with current ticket metrics."""
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT category, priority, status, confidence,
                   description, severity, escalation_reasons, ai_resolved
            FROM support_tickets
            """
        ).fetchall()

    categories = Counter(row[0] or "Unknown" for row in rows)
    priorities = Counter(row[1] or "Unspecified" for row in rows)
    escalation_counts = Counter()
    resolved_count = 0
    escalated_count = 0

    for row in rows:
        category, priority, status, confidence, description, severity, stored, ai_resolved = row
        reasons = set()
        try:
            reasons.update(json.loads(stored or "[]"))
        except (TypeError, json.JSONDecodeError):
            app.logger.warning("Ignoring invalid escalation reason data in dashboard metrics")

        # Backfill rule counts for tickets predating reason tracking.
        reasons.update(
            get_escalation_reasons(
                description,
                priority,
                confidence,
                severity,
            )
        )
        if status == "ESCALATE":
            escalated_count += 1
            for reason in reasons:
                if reason in ESCALATION_RULES:
                    escalation_counts[reason] += 1
        if ai_resolved:
            resolved_count += 1

    total_tickets = len(rows)
    resolution_rate = (
        round(resolved_count / total_tickets * 100, 1)
        if total_tickets else 0
    )
    return render_template(
        "dashboard.html",
        active_tab="analytics" if request.path == "/analytics" else "dashboard",
        total_tickets=total_tickets,
        ai_resolution_rate=resolution_rate,
        resolved_count=resolved_count,
        escalated_count=escalated_count,
        category_labels=list(categories.keys()),
        category_values=list(categories.values()),
        priority_labels=list(priorities.keys()),
        priority_values=list(priorities.values()),
        escalation_labels=ESCALATION_RULES,
        escalation_counts={
            rule: escalation_counts[rule]
            for rule in ESCALATION_RULES
        },
    )


# ============================================================
# MILESTONE 1
# TICKET CREATION + CLASSIFICATION
# ============================================================

@app.route("/api/ticket", methods=["POST"])
def create_ticket():
    data = request.get_json(silent=True) or {}

    description = (data.get("description") or "").strip()

    if not description:
        return jsonify({
            "error": "description is required"
        }), 400

    # Classification
    result = classify_query(description)

    category = result.get("category", "Unknown")
    confidence = result.get("confidence", 0)

    # Operational severity and priority only.
    severity = operational_severity(
        category,
        description
    )

    priority = operational_priority(
        category,
        description
    )

    status = (
        "ESCALATE"
        if requires_human_escalation(
            description,
            priority,
            confidence,
            severity
        )
        else "Open"
    )
    escalation_reasons = get_escalation_reasons(
        description,
        priority,
        confidence,
        severity,
    )

    ticket = {
        "requester_name": data.get("requester_name"),
        "department": data.get("department"),
        "title": data.get("title"),
        "description": description,
        "category": category,
        "severity": severity,
        "priority": priority,
        "confidence": confidence,
        "status": status,
        "escalation_reasons": json.dumps(escalation_reasons),
    }

    ticket_id = save_ticket(ticket)
    ticket.pop("escalation_reasons")
    ticket["ticket_id"] = ticket_id

    return jsonify(ticket)


# ============================================================
# GET ONE TICKET
# ============================================================

@app.route("/api/ticket/<int:ticket_id>", methods=["GET"])
def get_ticket_details(ticket_id):
    ticket = get_ticket(ticket_id)

    if ticket is None:
        return jsonify({
            "error": "Ticket not found"
        }), 404

    return jsonify(ticket)


# ============================================================
# MILESTONE 2
# RAG + KNOWLEDGE RETRIEVAL + RESOLUTION GENERATION
# ============================================================

@app.route("/api/rag", methods=["POST"])
def rag_resolution():
    data = request.get_json(silent=True) or {}

    ticket_id = data.get("ticket_id")

    if not ticket_id:
        return jsonify({
            "error": "ticket_id is required"
        }), 400

    try:
        ticket_id = int(ticket_id)
    except (TypeError, ValueError):
        return jsonify({
            "error": "ticket_id must be a valid integer"
        }), 400

    # Load the already-created ticket.
    ticket = get_ticket(ticket_id)

    if ticket is None:
        return jsonify({
            "error": "Ticket not found"
        }), 404

    description = (
        ticket.get("description") or ""
    ).strip()

    # Use the category produced during Milestone 1.
    category = (
        ticket.get("category") or "Unknown"
    )

    confidence = ticket.get("confidence") or 0

    if not description:
        return jsonify({
            "error": "Ticket description is empty"
        }), 400

    # Re-apply the safety rules for tickets created before these rules
    # were deployed, as well as tickets whose stored status is stale.
    escalation_reasons = set(
        get_escalation_reasons(
            description,
            ticket.get("priority"),
            confidence,
            ticket.get("severity"),
        )
    )
    try:
        escalation_reasons.update(
            json.loads(ticket.get("escalation_reasons") or "[]")
        )
    except (TypeError, json.JSONDecodeError):
        app.logger.warning(
            "Ignoring invalid escalation reason data for ticket %s",
            ticket_id,
        )
    needs_human_review = bool(escalation_reasons) or ticket.get("status") == "ESCALATE"
    if needs_human_review and ticket.get("status") != "ESCALATE":
        update_ticket_status(ticket_id, "ESCALATE")

    # --------------------------------------------------------
    # Run complete Milestone 2 RAG pipeline
    #
    # Ticket
    #   ↓
    # Predicted Category
    #   ↓
    # Knowledge Retrieval
    #   ↓
    # Top Evidence
    #   ↓
    # Context Augmentation
    #   ↓
    # Operational Resolution
    # --------------------------------------------------------

    rag_result = run_pipeline(
        ticket_text=description,
        category=category,
        top_k=3,
        generate_resolution=not needs_human_review
    )

    evidence = rag_result.get(
        "evidence",
        []
    )

    context = rag_result.get(
        "context",
        ""
    )

    resolution = rag_result.get(
        "resolution",
        ""
    )

    status = ticket.get("status")
    knowledge_requires_escalation = (
        rag_result.get("requires_escalation", False)
        or not evidence
        or (
            not needs_human_review
            and not str(resolution or "").strip()
        )
    )
    if knowledge_requires_escalation:
        escalation_reasons.add("no_knowledge_evidence")
    update_ticket_escalation_reasons(ticket_id, escalation_reasons)
    if needs_human_review or knowledge_requires_escalation:
        status = "ESCALATE"
        if ticket.get("status") != status:
            update_ticket_status(ticket_id, status)
        if needs_human_review:
            resolution = (
                "Issue Summary\n"
                "This ticket was escalated to a human support agent.\n\n"
                "Operational Area\n"
                f"{category}\n\n"
                "Recommended Troubleshooting Steps\n"
                "1. AI auto-resolution was skipped; await human support.\n\n"
                "Knowledge Sources"
            )
        elif not resolution:
            resolution = (
                "No sufficiently relevant knowledge-base evidence "
                "with troubleshooting steps was found for this ticket."
            )
        update_ticket_ai_resolved(ticket_id, False)
    else:
        update_ticket_ai_resolved(ticket_id, True)

    # Return the original ticket information together with
    # all Milestone 2 results needed by rag.html.
    return jsonify({
        # Ticket information
        "ticket_id": ticket.get("ticket_id"),
        "requester_name": ticket.get("requester_name"),
        "department": ticket.get("department"),
        "title": ticket.get("title"),
        "description": description,

        # Milestone 1 results
        "category": category,
        "severity": ticket.get("severity"),
        "priority": ticket.get("priority"),
        "confidence": confidence,
        "status": status,

        # Milestone 2 results
        "evidence": evidence,
        "context": context,
        "resolution": resolution
    })


# ============================================================
# HEALTH CHECK
# ============================================================

@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({
        "status": "healthy",
        "service": "Healthcare Support Pilot",
        "milestone": "Milestone 2",
        "components": [
            "Ticket Classification",
            "Operational Severity",
            "Operational Priority",
            "SQLite Ticket Storage",
            "Knowledge Retrieval",
            "Context Augmentation",
            "Resolution Generation"
        ]
    })


# ============================================================
# APPLICATION START
# ============================================================

if __name__ == "__main__":
    app.run(debug=True)
