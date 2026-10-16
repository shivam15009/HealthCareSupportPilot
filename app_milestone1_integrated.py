import json

import math

import os

import re

import secrets

import webbrowser



from collections import Counter

from datetime import timedelta

from threading import Timer



from flask import (

    Flask,

    request,

    jsonify,

    render_template,

    redirect,

    url_for,

    session,

)

from flask_jwt_extended import (

    JWTManager,

    jwt_required,

    get_jwt_identity,

)



from classifier import classify_query

from priority import operational_severity, operational_priority



import database_milestone1 as milestone1_db

from database import (

    init_db,

    save_ticket,

    get_ticket,
    record_ticket_multiagent_start,
    increment_agent_attempt_count,
    record_ai_resolution_attempt,
    update_ai_resolution_attempt,
    count_ai_resolution_attempts_today,
    record_ticket_classification,
    count_ticket_classifications_today,
    count_pending_ticket_validations,
    update_ticket_status,

    get_connection,

    update_ticket_escalation_reasons,

    update_ticket_ai_resolved,
    update_ticket_generation_time,
    update_ticket_resolution_confirmed,
    update_ticket_email_result,

    update_ticket_jira_result,
    get_ticket_jira_result,

)

from integrations.jira_service import (
    create_jira_issue,
    JiraConfigurationError,
    JiraIntegrationError,
)

from integrations.email_service import (
    send_support_ticket_notification,
    EmailConfigurationError,
    EmailDeliveryError,
)

from rag.pipeline import run_pipeline

from auth import auth, bcrypt, init_auth_db



# Milestone 3: Multi-agent workflow

from agents.orchestrator import MultiAgentOrchestrator





# ============================================================

# APPLICATION AND AUTHENTICATION CONFIGURATION

# ============================================================



app = Flask(__name__)



app.config["SECRET_KEY"] = os.environ.get("FLASK_SECRET_KEY")

app.config["JWT_SECRET_KEY"] = os.environ.get("JWT_SECRET_KEY")



if not app.config["SECRET_KEY"]:

    app.config["SECRET_KEY"] = secrets.token_hex(32)

    app.logger.warning(

        "FLASK_SECRET_KEY is not set. Browser sessions will be "

        "invalidated when the app restarts."

    )



if not app.config["JWT_SECRET_KEY"]:

    raise RuntimeError(

        "Set JWT_SECRET_KEY in your terminal before starting the app."

    )



app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(minutes=30)

app.config["SESSION_COOKIE_HTTPONLY"] = True

app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

app.config["SESSION_COOKIE_SECURE"] = (

    os.environ.get("COOKIE_SECURE", "false").lower() == "true"

)



jwt = JWTManager(app)



bcrypt.init_app(app)

app.register_blueprint(auth)



with app.app_context():

    init_auth_db()



init_db()  # Legacy database retained for legacy-only routes.
milestone1_db.init_db()





# ============================================================

# ESCALATION RULES

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



    "human_intent": "Escalated due to Human-Routing Intent",

    "no_knowledge_evidence": "Escalated due to No Relevant Knowledge Evidence",

}





def get_escalation_reasons(

    description,

    priority,

    confidence,

    severity=None,

):

    """Return operational escalation reasons for a support ticket."""



    reasons = []

    normalized_priority = str(priority or "").strip().casefold()



    if "p1" in normalized_priority or "critical" in normalized_priority:

        reasons.append("critical_priority")



    if str(severity or "").strip().casefold() == "critical":

        reasons.append("critical_priority")



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

    return bool(

        get_escalation_reasons(

            description,

            priority,

            confidence,

            severity,

        )

    )





def get_stored_escalation_reasons(ticket):

    """Safely read escalation reasons stored for a ticket."""



    try:

        stored = json.loads(ticket.get("escalation_reasons") or "[]")

        if isinstance(stored, list):

            return set(stored)

    except (TypeError, json.JSONDecodeError):

        app.logger.warning(

            "Invalid escalation reasons for ticket %s",

            ticket.get("ticket_id"),

        )



    return set()





# ============================================================

# HTML PAGE ROUTES

# ============================================================



@app.route("/")

def home():

    """Start at login unless a browser session already exists."""



    if session.get("user_id"):

        return redirect(url_for("dashboard_page"))



    return redirect(url_for("login_page"))





@app.route("/login")

def login_page():

    if session.get("user_id"):

        return redirect(url_for("dashboard_page"))



    return render_template("login.html")





@app.route("/register")

def register_page():

    if session.get("user_id"):

        return redirect(url_for("dashboard_page"))



    return render_template("register.html")





@app.route("/auth/session", methods=["POST"])

@jwt_required()

def establish_browser_session():

    """Exchange a valid bearer JWT for a Flask browser session."""



    session["user_id"] = str(get_jwt_identity())



    return jsonify({

        "message": "Browser session established",

    }), 200





@app.route("/logout", methods=["POST", "GET"])

def logout_page():

    session.clear()

    return redirect(url_for("login_page"))





@app.route("/ticket", methods=["GET"])

def ticket_page():

    """Display ticket creation after browser login."""



    if not session.get("user_id"):

        return redirect(url_for("login_page"))



    return render_template("tickets.html")





@app.route("/rag")
def rag_page():
    if not session.get("user_id"):
        return redirect(url_for("login_page"))

    raw_ticket_id = request.args.get("ticket_id")
    selected_ticket_id = None

    if raw_ticket_id:
        try:
            candidate_id = int(raw_ticket_id)
            if candidate_id > 0:
                ticket = milestone1_db.get_ticket(
                    candidate_id,
                    user_id=int(session["user_id"]),
                )
                if ticket is not None:
                    selected_ticket_id = candidate_id
        except (TypeError, ValueError):
            selected_ticket_id = None

    return render_template(
        "rag.html",
        selected_ticket_id=selected_ticket_id,
    )





# ============================================================

# MILESTONE 3: MULTI-AGENT PAGE

# ============================================================



@app.route("/agents", methods=["GET"])

def agents_page():

    """Display the agent workflow inspection page."""



    if not session.get("user_id"):

        return redirect(url_for("login_page"))



    return render_template("agents.html")





# ============================================================

# DASHBOARD AND ANALYTICS

# ============================================================




@app.route("/dashboard")
@app.route("/analytics")
def dashboard_page():
    """Render Milestone 1 ticket and classification metrics."""
    if not session.get("user_id"):
        return redirect(url_for("login_page"))

    from datetime import datetime, timezone

    rows = milestone1_db.list_tickets(limit=5000)
    categories = Counter(row.get("category") or "Unknown" for row in rows)
    priorities = Counter(row.get("priority") or "Unspecified" for row in rows)
    today = datetime.now(timezone.utc).date()
    chart_dates = [today - timedelta(days=offset) for offset in range(6, -1, -1)]
    daily_counts = {day: 0 for day in chart_dates}
    tickets_today = 0
    for ticket in rows:
        created_at = ticket.get("created_at")
        if not created_at:
            continue
        try:
            created_date = datetime.fromisoformat(str(created_at).replace("Z", "+00:00")).date()
        except (ValueError, TypeError):
            continue
        if created_date == today:
            tickets_today += 1
        if created_date in daily_counts:
            daily_counts[created_date] += 1

    total_tickets = len(rows)
    template_name = "analytics.html" if request.path == "/analytics" else "dashboard.html"
    return render_template(
        template_name,
        active_tab="analytics" if request.path == "/analytics" else "dashboard",
        total_tickets=total_tickets,
        verified_resolved_count=0,
        tickets_today=tickets_today,
        classifications_today=milestone1_db.count_ticket_classifications_today(),
        resolved_count=0,
        escalated_today=0,
        escalated_count=0,
        ai_resolution_rate=0,
        ai_resolved_today=0,
        ai_resolution_attempts_today=0,
        pending_validation=0,
        avg_resolution_time="Not tracked",
        resolution_time_change="Not tracked",
        user_satisfaction="No ratings",
        user_satisfaction_score="No ratings",
        satisfaction_change="Not tracked",
        classification_accuracy="Not measured yet",
        resolution_success_rate=0,
        knowledge_base_coverage="Not tracked",
        system_uptime="Not tracked",
        avg_response_generation_time="Not tracked",
        ticket_change="Not tracked",
        ai_rate_change="Not tracked",
        all_tickets=rows,
        category_labels=list(categories.keys()),
        category_values=list(categories.values()),
        priority_labels=list(priorities.keys()),
        priority_values=list(priorities.values()),
        chart_labels=[day.strftime("%d %b") for day in chart_dates],
        chart_values=[daily_counts[day] for day in chart_dates],
        chart_resolved_values=[0 for _ in chart_dates],
        escalation_labels={},
        escalation_counts={},
    )
# ============================================================

# TICKET CREATION AND CLASSIFICATION

# ============================================================




@app.route("/api/ticket", methods=["POST"])
def create_ticket():
    """Submit a support ticket and predict its category, severity, and priority."""
    if not session.get("user_id"):
        return jsonify({"error": "Authentication required"}), 401

    data = request.get_json(silent=True) or {}
    description = data.get("description")

    if not isinstance(description, str) or not description.strip():
        return jsonify({"error": "description is required"}), 400

    description = description.strip()

    try:
        result = classify_query(description)
        category = result.get("category", "Unknown")
        confidence = float(result.get("confidence", 0))

        if not math.isfinite(confidence):
            confidence = 0.0
        confidence = max(0.0, min(1.0, confidence))

        severity = operational_severity(category, description)
        priority = operational_priority(category, description)

        ticket = {
            "user_id": int(session["user_id"]),
            "requester_name": data.get("requester_name"),
            "department": data.get("department"),
            "title": data.get("title"),
            "description": description,
            "category": category,
            "severity": severity,
            "priority": priority,
            "confidence": confidence,
            "status": "Open",
        }

        ticket_id = milestone1_db.save_ticket(ticket)

        try:
            milestone1_db.record_ticket_classification(
                ticket_id,
                category,
                confidence,
            )
        except Exception:
            # The ticket is already saved. Log the metrics failure without
            # returning an error that could encourage duplicate submissions.
            app.logger.exception(
                "Could not record classification metrics for ticket %s",
                ticket_id,
            )

        response = dict(ticket)
        response["ticket_id"] = ticket_id

        return jsonify(response), 201

    except Exception:
        app.logger.exception("Ticket creation failed")
        return jsonify({
            "error": "Ticket could not be created. Please try again."
        }), 500





# ============================================================

# GET ONE TICKET

# ============================================================



@app.route("/api/ticket/<int:ticket_id>", methods=["GET"])
def get_ticket_details(ticket_id):
    if not session.get("user_id"):
        return jsonify({
            "error": "Authentication required"
        }), 401

    ticket = milestone1_db.get_ticket(ticket_id, user_id=int(session["user_id"]))


    if ticket is None:

        return jsonify({

            "error": "Ticket not found",

        }), 404



    return jsonify(ticket), 200





# ============================================================

# RAG AND OPERATIONAL RESOLUTION

# ============================================================



@app.route("/api/rag", methods=["POST"])
def rag_resolution():
    if not session.get("user_id"):
        return jsonify({
            "error": "Authentication required"
        }), 401

    data = request.get_json(silent=True) or {}

    ticket_id = data.get("ticket_id")



    if ticket_id is None:

        return jsonify({

            "error": "ticket_id is required",

        }), 400



    try:

        ticket_id = int(ticket_id)

    except (TypeError, ValueError):

        return jsonify({

            "error": "ticket_id must be a valid integer",

        }), 400



    ticket = milestone1_db.get_ticket(ticket_id, user_id=int(session["user_id"]))



    if ticket is None:

        return jsonify({

            "error": "Ticket not found",

        }), 404



    description = (ticket.get("description") or "").strip()

    category = ticket.get("category") or "Unknown"

    confidence = ticket.get("confidence") or 0



    if not description:

        return jsonify({

            "error": "Ticket description is empty",

        }), 400



    # RAG workflow only: retrieve evidence and generate operational guidance.
    # Escalation decisions are intentionally not part of this endpoint.
    try:
        rag_result = run_pipeline(
            ticket_text=description,
            category=category,
            top_k=3,
            generate_resolution=True,
        )
    except Exception:
        app.logger.exception(
            "RAG pipeline failed for ticket %s",
            ticket_id,
        )
        return jsonify({
            "error": "Knowledge retrieval or resolution generation failed.",
        }), 500


    evidence = rag_result.get("evidence", [])
    context = rag_result.get("context", "")
    resolution = rag_result.get("resolution", "")

    # Persist measured generation latency when available.
    generation_time_ms = rag_result.get("generation_time_ms")
    app.logger.warning(
    "RAG timing diagnostic: ticket_id=%s, evidence_count=%s, generation_time_ms=%r",
    ticket_id,
    len(evidence),
    generation_time_ms,
)
    # Generation timing is not part of the Milestone 1 schema.


    # Some pipeline versions return an escalation-based placeholder instead
    # of a resolution. The RAG view must show operational guidance only.
    resolution_text = str(resolution or "").strip()
    placeholder_markers = (
        "ai auto-resolution was skipped",
        "await human support",
        "escalat",
        "human-review",
        "human review",
    )
    if any(marker in resolution_text.casefold() for marker in placeholder_markers):
        resolution_text = ""

    if not evidence:
        resolution = (
            "Issue Summary\n"
            f"{description}\n\n"
            "Operational Area\n"
            f"{category}\n\n"
            "Recommended Troubleshooting Steps\n"
            "1. No relevant knowledge-base evidence was retrieved, so a "
            "source-grounded resolution cannot be provided yet. Confirm the "
            "reported symptoms and search the knowledge base for a matching "
            "procedure.\n"
            "2. Follow only approved procedures for this operational area; "
            "record any error messages and the result of each check.\n\n"
            "Knowledge Sources\n"
            "No sources were retrieved."
        )
    elif not resolution_text:
        source_names = []
        for item in evidence:
            if isinstance(item, dict):
                source = (item.get("source") or item.get("title") or
                          item.get("document") or item.get("url"))
                if source and str(source) not in source_names:
                    source_names.append(str(source))
        source_text = ", ".join(source_names) if source_names else (
            "See the retrieved evidence cards above."
        )
        resolution = (
            "Issue Summary\n"
            f"{description}\n\n"
            "Operational Area\n"
            f"{category}\n\n"
            "Recommended Troubleshooting Steps\n"
            "1. Compare the reported symptoms with the retrieved knowledge "
            "evidence and identify the matching approved procedure.\n"
            "2. Perform the applicable checks in that procedure and record "
            "the outcome of each step.\n"
            "3. If the issue persists, capture the exact error message and "
            "the checks already completed before continuing diagnosis.\n\n"
            "Knowledge Sources\n"
            f"{source_text}"
        )
    else:
        resolution = resolution_text

    # Generated guidance does not mean the issue has been fixed.
    # Generated guidance does not change the ticket status in Milestone 1.
    status = "OPEN"

    return jsonify({

        "ticket_id": ticket.get("ticket_id", ticket_id),

        "requester_name": ticket.get("requester_name"),

        "department": ticket.get("department"),

        "title": ticket.get("title"),

        "description": description,

        "category": category,

        "severity": ticket.get("severity"),

        "priority": ticket.get("priority"),

        "confidence": confidence,

        "status": status,

        "evidence": evidence,

        "context": context,

        "resolution": resolution,

    }), 200





# ============================================================

# MULTI-AGENT WORKFLOW API

# ============================================================



@app.route("/api/agents/run", methods=["POST"])

def run_agents_api():

    """

    Run the diagnosis, retrieval, resolution, validation,

    and action agents for a support request.



    This endpoint previews the workflow. It does not create a

    ticket or change an existing ticket's database status.

    """



    if not session.get("user_id"):

        return jsonify({

            "error": "Authentication required",

        }), 401



    data = request.get_json(silent=True)



    if not isinstance(data, dict):

        return jsonify({

            "error": "A JSON object is required",

        }), 400



    raw_ticket_text = data.get("ticket_text")



    if not isinstance(raw_ticket_text, str):

        return jsonify({

            "error": "ticket_text must be a string",

        }), 400



    ticket_text = raw_ticket_text.strip()



    if not ticket_text:

        return jsonify({

            "error": "ticket_text is required",

        }), 400



    if len(ticket_text) > 10000:

        return jsonify({

            "error": "ticket_text must be 10000 characters or fewer",

        }), 400



    try:

        orchestrator = MultiAgentOrchestrator()

        result = orchestrator.run(ticket_text)



        if not isinstance(result, dict):

            app.logger.error(

                "Orchestrator returned a non-dictionary result"

            )

            return jsonify({

                "error": "The workflow returned an invalid result.",

            }), 500



        return jsonify(result), 200



    except Exception:

        app.logger.exception("Multi-agent workflow failed")

        return jsonify({

            "error": "The multi-agent workflow failed.",

        }), 500

@app.route("/api/tickets/<int:ticket_id>/resolution-confirmation", methods=["POST"])
def confirm_ticket_resolution(ticket_id):
    """Record an explicit confirmation that a ticket issue is resolved."""

    if not session.get("user_id"):
        return jsonify({"error": "Authentication required"}), 401

    user_id = int(session["user_id"])
    ticket = get_ticket(ticket_id, user_id=user_id)

    if ticket is None:
        return jsonify({
            "error": "Ticket not found, or you do not have access to it."
        }), 404

    data = request.get_json(silent=True)
    if not isinstance(data, dict) or not isinstance(data.get("confirmed"), bool):
        return jsonify({
            "error": "Provide a JSON boolean field named 'confirmed'."
        }), 400

    try:
        update_ticket_resolution_confirmed(ticket_id, data["confirmed"])
    except LookupError:
        return jsonify({"error": "Ticket not found."}), 404

    return jsonify({
        "ticket_id": ticket_id,
        "resolution_confirmed": data["confirmed"],
    }), 200


# ============================================================
# MULTI-AGENT WORKFLOW FOR AN EXISTING TICKET
# ============================================================

@app.route("/api/agents/run-ticket", methods=["POST"])
def run_agents_for_ticket_api():
    """Run agents for an existing ticket owned by the signed-in user."""

    if not session.get("user_id"):
        return jsonify({"error": "Authentication required"}), 401

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "A JSON object is required"}), 400

    raw_ticket_id = data.get("ticket_id")
    try:
        ticket_id = int(raw_ticket_id)
        if isinstance(raw_ticket_id, bool) or ticket_id <= 0:
            raise ValueError
    except (TypeError, ValueError):
        return jsonify({"error": "A valid positive ticket_id is required"}), 400

    user_id = int(session["user_id"])
    ticket = get_ticket(ticket_id, user_id=user_id)

    if ticket is None:
        return jsonify({
            "error": "Ticket not found, or you do not have access to it."
        }), 404

    attempt_id = None

    try:
        attempt_count = increment_agent_attempt_count(ticket_id)

        attempt_id = record_ai_resolution_attempt(ticket_id)
        record_ticket_multiagent_start(ticket_id)

        result = MultiAgentOrchestrator().run(
            ticket["description"],
            ticket_id=ticket_id,
        )

        if not isinstance(result, dict):
            raise ValueError("The workflow returned an invalid result.")

        diagnosis = result.get("diagnosis") or {}
        retrieval = result.get("retrieval") or {}
        resolution = result.get("resolution") or {}
        validation = result.get("validation") or {}
        action_result = result.get("action_result") or {}




        # Use the Validation Agent's milestone confidence (0-100).
        try:
            resolution_confidence = float(
                validation.get("final_confidence",
                               validation.get("confidence"))
            )
        except (TypeError, ValueError):
            resolution_confidence = 0.0

        if not math.isfinite(resolution_confidence):
            resolution_confidence = 0.0

        reasons = get_stored_escalation_reasons(ticket)

        # Apply existing ticket safety rules using the multi-agent score.
        reasons.update(
            get_escalation_reasons(
                ticket.get("description", ""),
                ticket.get("priority", ""),
                resolution_confidence,
                ticket.get("severity"),
            )
        )

        if attempt_count >= 3:
            reasons.add("repeated_agent_attempts")

        if result.get("success") is not True:
            reasons.add("workflow_failed")

        if result.get("workflow_completed") is not True:
            reasons.add("workflow_incomplete")

        if diagnosis.get("success") is not True:
            reasons.add("diagnosis_failed")

        if retrieval.get("success") is not True or not retrieval.get("evidence"):
            reasons.add("retrieval_failed")

        if resolution.get("success") is not True:
            reasons.add("resolution_failed")

        if (
            validation.get("success") is not True
            or validation.get("approved") is not True
            or validation.get("requires_escalation") is not False
        ):
            reasons.add("validation_not_approved")

        if (
            action_result.get("success") is not True
            or action_result.get("action") != "AUTO_RESOLVE"
            or action_result.get("requires_escalation") is not False
            or action_result.get("integration_eligible") is not True
        ):
            reasons.add("action_not_approved")

        # Existing critical-priority and human-request rules remain mandatory.
        needs_escalation = bool(reasons)

        if needs_escalation:
            final_status = "ESCALATE"
            attempt_outcome = "ESCALATED"
        else:
            final_status = "AUTO_RESOLVE"
            attempt_outcome = "SUCCEEDED"

        update_ai_resolution_attempt(attempt_id, attempt_outcome)

        # Mark AI-resolved only after every existing approval/escalation gate passes.
        ai_resolved = not needs_escalation

        # Persist the multi-agent decision and its reasons.
        update_ticket_status(ticket_id, final_status)
        update_ticket_ai_resolved(ticket_id, ai_resolved)
        update_ticket_escalation_reasons(ticket_id, sorted(reasons))

        # Keep Jira creation idempotent: reuse an existing issue if present.
        jira_result = get_ticket_jira_result(ticket_id) or {}

        if needs_escalation:
            if jira_result.get("jira_issue_key"):
                jira_result["jira_sync_status"] = "SYNCED"
            else:
                try:
                    update_ticket_jira_result(ticket_id, "PENDING")
                    jira_payload = dict(ticket)
                    jira_payload["ticket_id"] = ticket_id
                    jira_payload["status"] = final_status
                    jira_payload["escalation_reasons"] = json.dumps(
                        sorted(reasons)
                    )
                    jira_result_created = create_jira_issue(jira_payload)

                    update_ticket_jira_result(
                        ticket_id,
                        "SYNCED",
                        jira_result_created["key"],
                        jira_result_created["url"],
                    )
                    jira_result = {
                        "jira_issue_key": jira_result_created["key"],
                        "jira_issue_url": jira_result_created["url"],
                        "jira_sync_status": "SYNCED",
                    }
                except JiraConfigurationError:
                    app.logger.warning(
                        "Jira is not configured for ticket %s.", ticket_id
                    )
                    update_ticket_jira_result(ticket_id, "NOT_CONFIGURED")
                    jira_result = {"jira_sync_status": "NOT_CONFIGURED"}
                except Exception:
                    app.logger.exception(
                        "Jira sync failed for ticket %s.", ticket_id
                    )
                    update_ticket_jira_result(ticket_id, "FAILED")
                    jira_result = {"jira_sync_status": "FAILED"}
        else:
            jira_result.setdefault("jira_sync_status", "NOT_REQUIRED")

        return jsonify({
            "success": True,
            "ticket_id": ticket_id,
            "attempt_count": attempt_count,
            "resolution_confidence": round(resolution_confidence, 2),
            "status": final_status,
            "ai_resolved": ai_resolved,
            "requires_escalation": needs_escalation,
            "escalation_reasons": sorted(reasons),
            "diagnosis": diagnosis,
            "retrieval": retrieval,
            "resolution": resolution,
            "validation": validation,
            "action_result": action_result,
            "jira_issue_key": jira_result.get("jira_issue_key"),
            "jira_issue_url": jira_result.get("jira_issue_url"),
            "jira_sync_status": jira_result.get("jira_sync_status"),
            "message": (
                "Human review is required."
                if needs_escalation
                else "The ticket was automatically marked AI-resolved after passing all approval gates."
            ),
        }), 200


    except Exception:

        if attempt_id is not None:
            try:
                update_ai_resolution_attempt(attempt_id, "FAILED")
            except Exception:
                app.logger.exception(
                    "Could not record failed AI attempt for ticket %s",
                    ticket_id,
                )

        app.logger.exception(
            "Multi-agent ticket workflow failed for ticket %s", ticket_id
        )
        return jsonify({
            "error": "The multi-agent ticket workflow failed."
        }), 500



# ============================================================

# HEALTH CHECK

# ============================================================



@app.route("/api/health", methods=["GET"])

def health():

    return jsonify({

        "status": "healthy",

        "service": "Healthcare Support Pilot",

        "milestone": "Milestone 1",

        "components": [

            "Ticket Classification",

            "Operational Severity",

            "Operational Priority",

            "SQLite Ticket Storage",

            "Knowledge Retrieval",

            "Context Augmentation",

            "Resolution Generation",

            "JWT Authentication",

            "Multi-Agent Orchestration",

            "Diagnosis Agent",

            "Retrieval Agent",

            "Resolution Agent",

            "Validation Agent",

            "Action Agent",

        ],

    }), 200





# ============================================================

# APPLICATION START

# ============================================================



if __name__ == "__main__":

    # Open the browser only in the main process.

    Timer(

        1.2,

        lambda: webbrowser.open("http://127.0.0.1:5000/"),

    ).start()



    app.run(debug=True, use_reloader=False)
