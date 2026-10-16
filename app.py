
import json
import math
import re
from collections import Counter

from flask import Flask, request, jsonify, render_template

from classifier import classify_query

from priority import (
    operational_severity,
    operational_priority,
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
from agents.orchestrator import MultiAgentOrchestrator


app = Flask(__name__)


# ============================================================
# MULTI-AGENT FRAMEWORK
# ============================================================

orchestrator = MultiAgentOrchestrator()


# ============================================================
# SAFETY RULES
# ============================================================

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


def get_escalation_reasons(
    description,
    priority,
    confidence,
    severity=None,
):
    """Return every existing application safety rule triggered."""

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

    # Confidence is stored as a percentage, for example 75.5.
    confidence_fraction = confidence_value / 100

    if (
        not math.isfinite(confidence_fraction)
        or confidence_fraction < 0.70
    ):
        reasons.append("low_confidence")

    normalized_description = re.sub(
        r"[^a-z0-9]+",
        " ",
        (description or "").casefold(),
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
    """Compatibility wrapper for the existing application."""

    return bool(
        get_escalation_reasons(
            description,
            priority,
            confidence,
            severity,
        )
    )


def safe_json(value):
    """Convert unexpected values into JSON-compatible data."""

    try:
        json.dumps(value)
        return value
    except (TypeError, ValueError):
        return str(value)


def get_resolution_text(resolution_result):
    """Extract resolution text from the Resolution Agent result."""

    if isinstance(resolution_result, dict):
        return str(resolution_result.get("resolution") or "")

    if isinstance(resolution_result, str):
        return resolution_result

    return ""


def map_agent_reasons_to_application_reasons(agent_reasons):
    """Map validation reasons to the application's dashboard reason codes."""

    mapped = set()

    for reason in agent_reasons or []:
        reason = str(reason).strip().casefold()

        if reason in {
            "low_classification_confidence",
            "low_confidence",
        }:
            mapped.add("low_confidence")

        elif reason in {
            "no_evidence",
            "missing_evidence",
            "insufficient_evidence",
            "low_relevance",
        }:
            mapped.add("no_knowledge_evidence")

        elif reason in {
            "existing_human_review_requirement",
            "critical_priority",
        }:
            mapped.add("critical_priority")

        elif reason == "human_intent":
            mapped.add("human_intent")

    return mapped


# ============================================================
# DATABASE INITIALIZATION
# ============================================================

init_db()


# ============================================================
# PAGE ROUTES
# ============================================================

@app.route("/")
def home():
    """Milestone 1 - Ticket classification page."""

    return render_template("tickets.html")


@app.route("/rag")
def rag_page():
    """Milestone 2 - Existing RAG workflow page."""

    return render_template("rag.html")


@app.route("/agents")
def agents_page():
    """Milestone 4 - Dedicated Multi-Agent Framework page."""

    return render_template("agents.html")


@app.route("/dashboard")
@app.route("/analytics")
def dashboard_page():
    """Render dashboard and analytics metrics."""

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
        (
            category,
            priority,
            status,
            confidence,
            description,
            severity,
            stored,
            ai_resolved,
        ) = row

        reasons = set()

        try:
            reasons.update(json.loads(stored or "[]"))
        except (TypeError, json.JSONDecodeError):
            app.logger.warning(
                "Ignoring invalid escalation reason data in dashboard metrics"
            )

        # Recalculate application rules for older tickets.
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

        # Only count tickets explicitly verified as resolved.
        if ai_resolved:
            resolved_count += 1

    total_tickets = len(rows)

    resolution_rate = (
        round(resolved_count / total_tickets * 100, 1)
        if total_tickets
        else 0
    )

    return render_template(
        "dashboard.html",
        active_tab=(
            "analytics"
            if request.path == "/analytics"
            else "dashboard"
        ),
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
# TICKET CREATION AND CLASSIFICATION
# ============================================================

@app.route("/api/ticket", methods=["POST"])
def create_ticket():
    data = request.get_json(silent=True) or {}

    description = (data.get("description") or "").strip()

    if not description:
        return jsonify({
            "error": "description is required"
        }), 400

    # Classify the operational support ticket.
    result = classify_query(description)

    category = result.get("category", "Unknown")
    confidence = result.get("confidence", 0)

    severity = operational_severity(
        category,
        description,
    )

    priority = operational_priority(
        category,
        description,
    )

    escalation_reasons = get_escalation_reasons(
        description,
        priority,
        confidence,
        severity,
    )

    status = "ESCALATE" if escalation_reasons else "Open"

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
# RAG AND MULTI-AGENT WORKFLOW FOR EXISTING TICKETS
# ============================================================

@app.route("/api/rag", methods=["POST"])
def rag_resolution():
    data = request.get_json(silent=True) or {}

    ticket_id = data.get("ticket_id")

    if ticket_id is None:
        return jsonify({
            "error": "ticket_id is required"
        }), 400

    try:
        ticket_id = int(ticket_id)
    except (TypeError, ValueError):
        return jsonify({
            "error": "ticket_id must be a valid integer"
        }), 400

    ticket = get_ticket(ticket_id)

    if ticket is None:
        return jsonify({
            "error": "Ticket not found"
        }), 404

    description = (
        ticket.get("description") or ""
    ).strip()

    category = ticket.get("category") or "Unknown"
    confidence = ticket.get("confidence") or 0

    if not description:
        return jsonify({
            "error": "Ticket description is empty"
        }), 400

    # --------------------------------------------------------
    # Reapply the existing application's safety rules.
    # --------------------------------------------------------

    escalation_reasons = set(
        get_escalation_reasons(
            description,
            ticket.get("priority"),
            confidence,
            ticket.get("severity"),
        )
    )

    try:
        stored_reasons = json.loads(
            ticket.get("escalation_reasons") or "[]"
        )

        if isinstance(stored_reasons, list):
            escalation_reasons.update(stored_reasons)

    except (TypeError, json.JSONDecodeError):
        app.logger.warning(
            "Ignoring invalid escalation reasons for ticket %s",
            ticket_id,
        )

    needs_human_review = (
        bool(escalation_reasons)
        or ticket.get("status") == "ESCALATE"
    )

    evidence = []
    context = ""
    resolution = ""
    workflow = {}
    agent_action = "ESCALATE"
    status = "ESCALATE"

    # --------------------------------------------------------
    # SAFETY PATH
    #
    # If the original application rules require human review,
    # do not run resolution generation.
    # --------------------------------------------------------

    if needs_human_review:
        rag_result = run_pipeline(
            ticket_text=description,
            category=category,
            top_k=3,
            generate_resolution=False,
        )

        evidence = rag_result.get("evidence", []) or []
        context = rag_result.get("context", "") or ""

        workflow = {
            "mode": "human_review",
            "diagnosis": {
                "category": category,
                "confidence": confidence,
            },
            "retrieval": {
                "success": bool(evidence),
                "evidence_count": len(evidence),
            },
            "resolution": {
                "success": False,
                "message": (
                    "Resolution generation skipped because "
                    "an application safety rule requires human review."
                ),
            },
            "validation": {
                "approved": False,
                "requires_escalation": True,
                "reasons": sorted(escalation_reasons),
            },
            "action": "ESCALATE",
        }

        resolution = (
            "Issue Summary\n"
            "This ticket requires review by a human support agent.\n\n"
            "Operational Area\n"
            f"{category}\n\n"
            "Recommended Troubleshooting Steps\n"
            "1. AI resolution generation was skipped for safety.\n"
            "2. Review the ticket details and supporting evidence.\n\n"
            "Knowledge Sources"
        )

    # --------------------------------------------------------
    # MULTI-AGENT PATH
    #
    # Diagnosis -> Retrieval -> Resolution -> Validation -> Action
    # --------------------------------------------------------

    else:
        try:
            agent_result = orchestrator.run(description)

            if not isinstance(agent_result, dict):
                raise TypeError(
                    "The orchestrator returned an unexpected result."
                )

            workflow = agent_result

            diagnosis = agent_result.get("diagnosis") or {}
            retrieval = agent_result.get("retrieval") or {}
            resolution_result = agent_result.get("resolution") or {}
            validation = agent_result.get("validation") or {}
            action_result = agent_result.get("action_result") or {}

            evidence = retrieval.get("evidence", []) or []
            context = retrieval.get("context", "") or ""
            resolution = get_resolution_text(resolution_result)

            # Treat failed retrieval or missing evidence as escalation.
            if (
                not agent_result.get("success", False)
                or not retrieval.get("success", False)
                or not evidence
            ):
                escalation_reasons.add("no_knowledge_evidence")

            # Translate validation reasons for dashboard tracking.
            validation_reasons = validation.get("reasons", []) or []

            escalation_reasons.update(
                map_agent_reasons_to_application_reasons(
                    validation_reasons
                )
            )

            approved = validation.get("approved", False)

            requested_action = (
                action_result.get("action")
                or agent_result.get("action")
                or "ESCALATE"
            )

            resolution_failed = (
                not resolution_result.get("success", False)
                or not resolution.strip()
                or resolution_result.get("requires_escalation", False)
            )

            # A ticket can be resolution-ready only if every gate passes.
            if (
                not approved
                or requested_action == "ESCALATE"
                or resolution_failed
                or not evidence
                or escalation_reasons
            ):
                status = "ESCALATE"
                agent_action = "ESCALATE"

                if not resolution.strip():
                    resolution = (
                        "This ticket requires human review. "
                        "The multi-agent workflow did not produce "
                        "an approved resolution."
                    )

            else:
                # This is a proposed resolution, not proof the issue is fixed.
                status = ticket.get("status") or "Open"
                agent_action = "AI_RESOLUTION_READY"

        except Exception:
            app.logger.exception(
                "Multi-agent processing failed for ticket %s",
                ticket_id,
            )

            # Fail safely if any agent crashes.
            status = "ESCALATE"
            agent_action = "ESCALATE"
            escalation_reasons.add("no_knowledge_evidence")

            workflow = {
                "mode": "error_fallback",
                "action": "ESCALATE",
                "message": (
                    "The multi-agent workflow failed. "
                    "Human review is required."
                ),
            }

            resolution = (
                "The multi-agent workflow could not safely complete "
                "this ticket. Please route it to a human support agent."
            )

    # --------------------------------------------------------
    # PERSIST THE FINAL STATUS
    # --------------------------------------------------------

    if status == "ESCALATE":
        update_ticket_status(ticket_id, "ESCALATE")
    elif ticket.get("status") != "ESCALATE":
        # Keep the existing non-escalated status.
        status = ticket.get("status") or "Open"

    update_ticket_escalation_reasons(
        ticket_id,
        escalation_reasons,
    )

    # Generating a suggested answer does NOT mean the issue is fixed.
    # Do not set ai_resolved=True here.
    update_ticket_ai_resolved(ticket_id, False)

    return jsonify({
        # Original ticket
        "ticket_id": ticket_id,
        "requester_name": ticket.get("requester_name"),
        "department": ticket.get("department"),
        "title": ticket.get("title"),
        "description": description,

        # Milestone 1
        "category": category,
        "severity": ticket.get("severity"),
        "priority": ticket.get("priority"),
        "confidence": confidence,

        # Final ticket status
        "status": status,
        "action": agent_action,
        "ai_resolved": False,
        "escalation_reasons": sorted(escalation_reasons),

        # Milestone 2 - RAG
        "evidence": safe_json(evidence),
        "context": context,
        "resolution": resolution,

        # Milestone 4 - Multi-agent results
        "workflow": safe_json(workflow),
    })


# ============================================================
# MILESTONE 4
# DIRECT MULTI-AGENT WORKFLOW ENDPOINT
# ============================================================

@app.route("/api/agents/process", methods=["POST"])
def process_with_agents():
    """
    Run the multi-agent workflow directly for a ticket description.

    This endpoint does not create a ticket or change the database.
    The existing /api/rag endpoint remains responsible for persistence.
    """

    data = request.get_json(silent=True) or {}

    description = (data.get("description") or "").strip()

    if not description:
        return jsonify({
            "error": "description is required"
        }), 400

    try:
        result = orchestrator.run(description)

        if not isinstance(result, dict):
            raise TypeError(
                "The orchestrator returned an unexpected result."
            )

        validation = result.get("validation") or {}
        retrieval = result.get("retrieval") or {}
        resolution_result = result.get("resolution") or {}
        action_result = result.get("action_result") or {}

        evidence = retrieval.get("evidence", []) or []
        resolution = get_resolution_text(resolution_result)

        approved = bool(validation.get("approved", False))

        safe_to_present_as_ready = (
            result.get("success", False)
            and approved
            and bool(evidence)
            and bool(resolution.strip())
            and resolution_result.get("success", False)
            and not resolution_result.get("requires_escalation", False)
            and action_result.get("action") != "ESCALATE"
        )

        # A proposed answer does not prove that the issue is fixed.
        result["ai_resolved"] = False

        if not safe_to_present_as_ready:
            result["action"] = "ESCALATE"
            result["status"] = "ESCALATE"
        else:
            result["action"] = "AI_RESOLUTION_READY"

        return jsonify(safe_json(result))

    except Exception:
        app.logger.exception("Direct multi-agent processing failed")

        return jsonify({
            "success": False,
            "action": "ESCALATE",
            "status": "ESCALATE",
            "ai_resolved": False,
            "message": (
                "The multi-agent workflow failed. "
                "Human review is required."
            ),
        }), 500


# ============================================================
# HEALTH CHECK
# ============================================================

@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({
        "status": "healthy",
        "service": "Healthcare Support Pilot",
        "milestone": "Milestone 4",
        "components": [
            "Ticket Classification",
            "Operational Severity",
            "Operational Priority",
            "SQLite Ticket Storage",
            "Knowledge Retrieval",
            "Context Augmentation",
            "Resolution Generation",
            "Diagnosis Agent",
            "Retrieval Agent",
            "Resolution Agent",
            "Validation Agent",
            "Action Agent",
            "Multi-Agent Orchestrator",
            "Human Escalation",
        ],
    })


# ============================================================
# APPLICATION START
# ============================================================

if __name__ == "__main__":
    app.run(debug=True)
