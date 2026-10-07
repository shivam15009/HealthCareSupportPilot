from flask import Flask, request, jsonify, render_template

from classifier import classify_query

from priority import (
    operational_severity,
    operational_priority
)

from database import (
    init_db,
    save_ticket,
    get_ticket
)

from rag.pipeline import run_pipeline


app = Flask(__name__)

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

    ticket = {
        "requester_name": data.get("requester_name"),
        "department": data.get("department"),
        "title": data.get("title"),
        "description": description,
        "category": category,
        "severity": severity,
        "priority": priority,
        "confidence": confidence,
        "status": "Open"
    }

    ticket_id = save_ticket(ticket)
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
        top_k=3
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
        "status": ticket.get("status"),

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
