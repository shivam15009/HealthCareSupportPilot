import json

import math

import os

import re

import secrets

import webbrowser

import time

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



from classifier import classify_query, get_classification_categories

from priority import operational_severity, operational_priority



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
    update_ticket_category_verification,
    update_ticket_pipeline_response_time,
    update_ticket_knowledge_base_coverage,
    get_connection,

    update_ticket_escalation_reasons,

    update_ticket_ai_resolved,
    update_ticket_final_confidence,
    update_ticket_generation_time,
    update_ticket_resolution_confirmed,
    save_ticket_satisfaction_rating,
    update_ticket_email_result,
    get_ticket_email_result,
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
    send_resolution_notification,
    EmailConfigurationError,
    EmailDeliveryError,
)

from rag.pipeline import run_pipeline

from auth import (
    auth,
    bcrypt,
    init_auth_db,
    get_user_email,
    get_user_username,
)



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



init_db()

@app.context_processor
def inject_sidebar_user():
    user_id = session.get("user_id")

    username = session.get("username")

    if not username and user_id:
        username = get_user_username(user_id)

    display_name = username or "Signed-in user"

    return {
        "sidebar_username": display_name,
        "sidebar_user_initial": display_name[:1].upper(),
    }



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

    app.logger.info(
    "Escalation inputs: priority=%r normalized_priority=%r severity=%r",
    priority,
    normalized_priority,
    severity,
)


    if (
        normalized_priority in {"p1", "priority 1", "critical"}
        or str(severity or "").strip().casefold() == "critical"
    ):
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


    session.clear()



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
    user_id = str(get_jwt_identity())
    username = get_user_username(user_id)

    session["user_id"] = user_id

    if username:
        session["username"] = username
    else:
        session.pop("username", None)

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
                ticket = get_ticket(
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

    """Render dashboard analytics across all users' tickets."""

    if not session.get("user_id"):
        return redirect(url_for("login_page"))

    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT
                ticket_id,
                requester_name,
                department,
                title,
                description,
                category,
                severity,
                priority,
                confidence,
                status,
                escalation_reasons,
                ai_resolved,
                created_at,
                resolution_confirmed,
                final_confidence
            FROM support_tickets

            ORDER BY created_at DESC
            """
        ).fetchall()

        latency_row = conn.execute(
            """
            SELECT AVG(pipeline_response_time_ms)
            FROM support_tickets
            WHERE pipeline_response_time_ms IS NOT NULL
              AND pipeline_response_time_ms >= 0
            """
        ).fetchone()
        resolution_time_row = conn.execute(
            """
            SELECT AVG(
                (julianday(resolved_at) - julianday(created_at))
                * 24 * 60
            )
            FROM support_tickets
            WHERE resolution_confirmed = 1
              AND created_at IS NOT NULL
              AND resolved_at IS NOT NULL
              AND julianday(resolved_at) >= julianday(created_at)
            """
        ).fetchone()
        satisfaction_row = conn.execute(
            """
            SELECT
                COUNT(customer_satisfaction_rating),
                SUM(
                    CASE
                        WHEN customer_satisfaction_rating >= 4 THEN 1
                        ELSE 0
                    END
                )
            FROM support_tickets
            WHERE customer_satisfaction_rating BETWEEN 1 AND 5
            """
        ).fetchone()

        uptime_row = conn.execute(
            """
            SELECT
                COUNT(*) AS total_checks,
                COALESCE(SUM(is_healthy), 0) AS healthy_checks
            FROM system_health_checks
            """
        ).fetchone()

        classification_accuracy_row = conn.execute(
            """
            SELECT
                COUNT(*) AS verified_count,
                COALESCE(
                    SUM(
                        CASE
                            WHEN LOWER(TRIM(COALESCE(category, ''))) =
                                 LOWER(TRIM(verified_category))
                            THEN 1
                            ELSE 0
                        END
                    ),
                    0
                ) AS correct_count
            FROM support_tickets
            WHERE verified_category IS NOT NULL
              AND TRIM(verified_category) <> ''
            """
        ).fetchone()

        verification_rows = conn.execute(
            """
            SELECT ticket_id, verified_category, category_verified_at
            FROM support_tickets
            WHERE verified_category IS NOT NULL
            """
        ).fetchall()

    average_pipeline_ms = (
        latency_row[0]
        if latency_row and latency_row[0] is not None
        else None
    )

    avg_response_generation_time = (
        f"{average_pipeline_ms / 1000:.2f} sec"
        if average_pipeline_ms is not None
        else "Not tracked"
    )
    average_resolution_minutes = (
        resolution_time_row[0]
        if resolution_time_row
        and resolution_time_row[0] is not None
        else None
    )

    avg_resolution_time = (
        f"{average_resolution_minutes:.1f} min"
        if average_resolution_minutes is not None
        else "Not tracked yet"
    )
    satisfaction_count = (
        satisfaction_row[0] if satisfaction_row else 0
    ) or 0

    satisfied_count = (
        satisfaction_row[1] if satisfaction_row else 0
    ) or 0

    satisfaction_percentage = (
        satisfied_count / satisfaction_count * 100
        if satisfaction_count > 0
        else None
    )

    user_satisfaction = (
        f"{satisfaction_percentage:.0f}%"
        if satisfaction_percentage is not None
        else "No ratings yet"
    )

    user_satisfaction_score = user_satisfaction

    satisfaction_change = (
        f"{satisfied_count} of {satisfaction_count} ratings were positive"
        if satisfaction_count > 0
        else "Awaiting customer ratings"
    )
    total_health_checks = uptime_row[0] or 0
    healthy_health_checks = uptime_row[1] or 0

    system_uptime = (
        f"{healthy_health_checks / total_health_checks * 100:.2f}%"
        if total_health_checks
        else "Not tracked"
    )
    classification_verified_count = (
        classification_accuracy_row[0] or 0
    )
    classification_correct_count = (
        classification_accuracy_row[1] or 0
    )

    classification_accuracy = (
        f"{classification_correct_count / classification_verified_count * 100:.1f}%"
        if classification_verified_count
        else "Not tracked"
    )

    verification_by_ticket_id = {
        item[0]: {
            "verified_category": item[1],
            "category_verified_at": item[2],
        }
        for item in verification_rows
    }

    # Build ticket dictionaries for the existing dashboard table.
    all_tickets = [
        {
            "ticket_id": row[0],
            "requester_name": row[1],
            "department": row[2],
            "title": row[3],
            "description": row[4],
            "category": row[5],
            "severity": row[6],
            "priority": row[7],
            "confidence": row[8],
            "status": row[9],
            "escalation_reasons": row[10],
            "ai_resolved": row[11],
            "created_at": row[12],
            "resolution_confirmed": row[13],
            "final_confidence": row[14],
                        "verified_category": verification_by_ticket_id.get(
                row[0], {}
            ).get("verified_category"),
            "category_verified_at": verification_by_ticket_id.get(
                row[0], {}
            ).get("category_verified_at"),

        }
        for row in rows
    ]

    categories = Counter(
        row[5] or "Unknown" for row in rows
    )
    priorities = Counter(
        row[7] or "Unspecified" for row in rows
    )

    escalation_counts = Counter()
    resolved_count = 0
    escalated_count = 0

    # Use the server's local date for the daily ticket count.
    from datetime import datetime


    today = datetime.now().date()
    tickets_today = 0
    escalated_today = 0

    # Prepare ticket-volume data for the last 7 calendar days.
    chart_dates = [
        today - timedelta(days=offset)
        for offset in range(6, -1, -1)
    ]
    daily_counts = {day: 0 for day in chart_dates}
    daily_resolved_counts = {day: 0 for day in chart_dates}




    for row in rows:
        (
            ticket_id,
            requester_name,
            department,
            title,
            description,
            category,
            severity,
            priority,
            confidence,
            status,
            stored,
            ai_resolved,
            created_at,
            resolution_confirmed,
            final_confidence,
        ) = row


        # Count tickets created today, when their timestamp is parseable.
        if created_at:
            try:
                created_date = datetime.fromisoformat(
                    str(created_at).replace("Z", "+00:00")
                ).date()

                if created_date == today:
                    tickets_today += 1

                    if str(status or "").strip().upper() in {
                        "ESCALATE",
                        "ESCALATE TO HUMAN SUPPORT",
                    }:
                        escalated_today += 1

                # Count tickets for every date in the chart's 7-day range.
                if created_date in daily_counts:
                    daily_counts[created_date] += 1

                    if ai_resolved:
                        daily_resolved_counts[created_date] += 1

            except (ValueError, TypeError):
                app.logger.warning(
                    "Could not parse created_at for ticket %s",
                    ticket_id,
                )

        reasons = set()

        try:
            stored_reasons = json.loads(stored or "[]")
            if isinstance(stored_reasons, list):
                reasons.update(stored_reasons)
        except (TypeError, json.JSONDecodeError):
            app.logger.warning(
                "Invalid escalation reasons for ticket %s",
                ticket_id,
            )

        reasons.update(
            get_escalation_reasons(
                description,
                priority,
                confidence,
                severity,
            )
        )

        if str(status or "").strip().upper() in {
            "ESCALATE",
            "ESCALATE TO HUMAN SUPPORT",
        }:
            escalated_count += 1

            for reason in reasons:
                if reason in ESCALATION_RULES:
                    escalation_counts[reason] += 1


        if ai_resolved:
            resolved_count += 1

    verified_resolved_count = sum(
        1 for row in rows if row[13]
    )
    coverage_row = conn.execute(
        """
        SELECT
            COUNT(*) AS measured_tickets,
            COALESCE(SUM(knowledge_base_covered), 0) AS covered_tickets
        FROM support_tickets
        WHERE knowledge_base_covered IS NOT NULL
        """
    ).fetchone()

    measured_coverage_tickets = coverage_row[0] or 0
    covered_coverage_tickets = coverage_row[1] or 0

    knowledge_base_coverage = (
        f"{covered_coverage_tickets / measured_coverage_tickets * 100:.1f}%"
        if measured_coverage_tickets
        else "Not tracked"
    )
    total_tickets = len(rows)



    resolution_rate = (
        round(resolved_count / total_tickets * 100, 1)
        if total_tickets
        else 0
    )

    resolution_success_rate = (
        round(verified_resolved_count / total_tickets * 100, 1)
        if total_tickets
        else 0
    )


    template_name = (
        "analytics.html"
        if request.path == "/analytics"
        else "dashboard.html"
    )

    return render_template(
    template_name,
    active_tab=(
        "analytics"
        if request.path == "/analytics"
        else "dashboard"
    ),

    # Ticket counts measured from the SQLite database.
    total_tickets=total_tickets,
    verified_resolved_count=verified_resolved_count,
    tickets_today=tickets_today,
    classifications_today=count_ticket_classifications_today(),
    resolved_count=resolved_count,
    escalated_today=escalated_today,
    escalated_count=escalated_count,

    # This measures the ai_resolved database flag, not verified
    # real-world issue resolution.
    ai_resolution_rate=resolution_rate,
    ai_resolved_today=daily_resolved_counts[today],
    ai_resolution_attempts_today=count_ai_resolution_attempts_today(),
    pending_validation=count_pending_ticket_validations(),

    # These measurements are not stored by the current schema.
    avg_resolution_time=avg_resolution_time,
    resolution_time_change="Not tracked",
    user_satisfaction=user_satisfaction,
    user_satisfaction_score=user_satisfaction_score,
    satisfaction_change=satisfaction_change,
    classification_accuracy=classification_accuracy,
    resolution_success_rate=resolution_success_rate,
    knowledge_base_coverage=knowledge_base_coverage,
    system_uptime=system_uptime,
    avg_response_generation_time=avg_response_generation_time,

    # Daily comparison metrics are not calculated yet.
    ticket_change="Not tracked",
    ai_rate_change="Not tracked",

    all_tickets=all_tickets,
    classification_categories=get_classification_categories(),
    category_labels=list(categories.keys()),
    category_values=list(categories.values()),
    priority_labels=list(priorities.keys()),
    priority_values=list(priorities.values()),
    chart_labels=[
        day.strftime("%d %b") for day in chart_dates
    ],
    chart_values=[
        daily_counts[day] for day in chart_dates
    ],
    chart_resolved_values=[
        daily_resolved_counts[day] for day in chart_dates
    ],
    escalation_labels=ESCALATION_RULES,
    escalation_counts={
        rule: escalation_counts[rule]
        for rule in ESCALATION_RULES
    },
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

        # Do not save a ticket when classification explicitly fails.
        if result.get("success") is False:
            app.logger.warning(
                "Ticket classification failed: %s",
                result.get("message", "Unknown classification error"),
            )
            return jsonify({
                "error": "Ticket classification failed. Please try again."
            }), 503

        category = result.get("category")
        if not isinstance(category, str) or not category.strip():
            return jsonify({
                "error": "A valid ticket category could not be identified."
            }), 503

        category = category.strip()

        try:
            confidence = float(result.get("confidence", 0))
        except (TypeError, ValueError):
            return jsonify({
                "error": "Ticket classification returned an invalid confidence score."
            }), 503

        if not math.isfinite(confidence):
            return jsonify({
                "error": "Ticket classification returned an invalid confidence score."
            }), 503

        # Support either a fractional score (0–1) or percentage (0–100).
        # Store and return confidence consistently as a percentage.
        if 0.0 <= confidence <= 1.0:
            confidence *= 100.0

        confidence = max(0.0, min(100.0, confidence))


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

        ticket_id = save_ticket(ticket)

        try:
            record_ticket_classification(
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




@app.route(
    "/api/tickets/<int:ticket_id>/verify-category",
    methods=["POST"],
)
def verify_ticket_category(ticket_id):
    """Save a human-reviewed category for a support ticket."""
    if not session.get("user_id"):
        return jsonify({"error": "Authentication required"}), 401

    data = request.get_json(silent=True) or {}
    verified_category = data.get("verified_category")

    if not isinstance(verified_category, str):
        return jsonify({
            "error": "verified_category must be a string."
        }), 400

    verified_category = verified_category.strip()

    if not verified_category or len(verified_category) > 100:
        return jsonify({
            "error": "Enter a verified category of 1–100 characters."
        }), 400

    try:
        updated = update_ticket_category_verification(
            ticket_id,
            verified_category,
        )

        if not updated:
            return jsonify({"error": "Ticket not found."}), 404

        return jsonify({
            "success": True,
            "ticket_id": ticket_id,
            "verified_category": verified_category,
        }), 200

    except Exception:
        app.logger.exception(
            "Could not verify category for ticket %s",
            ticket_id,
        )
        return jsonify({
            "error": "Could not save category verification."
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

    ticket = get_ticket(ticket_id, user_id=int(session["user_id"]))


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



    ticket = get_ticket(ticket_id, user_id=int(session["user_id"]))



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


    pipeline_started_at = time.perf_counter()
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

    pipeline_response_time_ms = round(
        (time.perf_counter() - pipeline_started_at) * 1000,
        2,
    )

    try:
        update_ticket_pipeline_response_time(
            ticket_id,
            pipeline_response_time_ms,
        )
        app.logger.info(
            "RAG pipeline response time: ticket_id=%s elapsed_ms=%.2f",
            ticket_id,
            pipeline_response_time_ms,
        )
    except Exception:
        app.logger.exception(
            "Could not record RAG pipeline response time for ticket %s",
            ticket_id,
        )
    evidence = rag_result.get("evidence", [])
    context = rag_result.get("context", "")
    resolution = rag_result.get("resolution", "")
    # Record whether the knowledge base returned evidence for this ticket.
    try:
        update_ticket_knowledge_base_coverage(
            ticket_id,
            bool(evidence),
        )
    except Exception:
        app.logger.exception(
            "Could not record knowledge-base coverage for ticket %s",
            ticket_id,
        )
    # Persist measured generation latency when available.
    generation_time_ms = rag_result.get("generation_time_ms")
    app.logger.warning(
    "RAG timing diagnostic: ticket_id=%s, evidence_count=%s, generation_time_ms=%r",
    ticket_id,
    len(evidence),
    generation_time_ms,
)
    if (
        isinstance(generation_time_ms, (int, float))
        and math.isfinite(generation_time_ms)
        and generation_time_ms >= 0
    ):
        update_ticket_generation_time(ticket_id, generation_time_ms)


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


        app.logger.warning(
            "AGENT RESULT STATUS: result_success=%r workflow_completed=%r "
            "diagnosis_success=%r retrieval_success=%r evidence_count=%d "
            "resolution_success=%r validation_approved=%r "
            "validation_escalation=%r action=%r",
            result.get("success"),
            result.get("workflow_completed"),
            diagnosis.get("success"),
            retrieval.get("success"),
            len(retrieval.get("evidence") or []),
            resolution.get("success"),
            validation.get("approved"),
            validation.get("requires_escalation"),
            action_result.get("action"),
        )






        # Use the Validation Agent's milestone confidence (0-100).
        try:
            resolution_confidence = float(
                validation.get(
                    "final_confidence",
                    validation.get("confidence"),
                )
            )
        except (TypeError, ValueError):
            resolution_confidence = 0.0

        if not math.isfinite(resolution_confidence):
            resolution_confidence = 0.0

        # Persist the final Multi-Agent validation confidence (0-100).
        update_ticket_final_confidence(
            ticket_id,
            round(resolution_confidence, 2),
        )

        app.logger.warning(
            "FINAL CONFIDENCE PERSISTENCE: ticket_id=%s score=%s",
            ticket_id,
            round(resolution_confidence, 2),
        )


        # Recalculate reasons from the current workflow run.
        # Historical reasons remain in ticket-validation/audit history;
        # they should not automatically determine the current run's outcome.
        reasons = set()

        app.logger.warning(
            "STORED ESCALATION REASONS: ticket_id=%r reasons=%r",
            ticket.get("ticket_id"),
            sorted(reasons),
        )


        # Apply existing ticket safety rules using the multi-agent score.
        reasons.update(
            get_escalation_reasons(
                ticket.get("description", ""),
                ticket.get("priority", ""),
                resolution_confidence,
                ticket.get("severity"),
            )
        )

        app.logger.warning(
            "REASONS AFTER SAFETY RULES: %r",
            sorted(reasons),
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
        app.logger.info(
            "Workflow gates: diagnosis=%s retrieval=%s evidence=%s "
            "resolution=%s validation_success=%s approved=%s "
            "validation_escalation=%s action=%s action_escalation=%s "
            "integration_eligible=%s reasons=%s",
            diagnosis.get("success"),
            retrieval.get("success"),
            bool(retrieval.get("evidence")),
            resolution.get("success"),
            validation.get("success"),
            validation.get("approved"),
            validation.get("requires_escalation"),
            action_result.get("action"),
            action_result.get("requires_escalation"),
            action_result.get("integration_eligible"),
            sorted(reasons),
        )

        app.logger.warning(
            "FINAL ESCALATION REASONS: %r | attempt_count=%r | "
            "retrieval_success=%r | evidence_count=%d | "
            "resolution_success=%r | validation_approved=%r | "
            "validation_escalation=%r",
            sorted(reasons),
            attempt_count,
            retrieval.get("success"),
            len(retrieval.get("evidence") or []),
            resolution.get("success"),
            validation.get("approved"),
            validation.get("requires_escalation"),
        )
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
            if jira_result.get("jira_issue_key"):
                jira_result["jira_sync_status"] = "SYNCED"
            else:
                jira_result["jira_sync_status"] = "NOT_REQUIRED"

                # Send one email per ticket after the final decision is known.
        email_result = get_ticket_email_result(ticket_id) or {}
        email_status = email_result.get("email_notification_status")

        if email_status != "SENT":
            try:
                if final_status == "AUTO_RESOLVE" and ai_resolved:
                    # Send approved resolution instructions to the requester.
                    recipient = get_user_email(ticket.get("user_id"))

                    if not recipient:
                        update_ticket_email_result(
                            ticket_id, "NOT_CONFIGURED"
                        )
                        app.logger.warning(
                            "Resolution email skipped: no requester email "
                            "for ticket %s.",
                            ticket_id,
                        )
                    else:
                        update_ticket_email_result(ticket_id, "PENDING")

                        send_resolution_notification(
                            ticket={
                                **ticket,
                                "ticket_id": ticket_id,
                                "status": final_status,
                            },
                            recipient=recipient,
                            resolution=resolution.get("resolution"),
                            jira_issue_key=jira_result.get("jira_issue_key"),
                            jira_url=jira_result.get("jira_issue_url"),
                        )

                        update_ticket_email_result(ticket_id, "SENT")
                        app.logger.info(
                            "Resolution email sent for ticket %s.",
                            ticket_id,
                        )

                elif final_status == "ESCALATE":
                    # Send escalation notification to the registered requester.
                    recipient = get_user_email(ticket.get("user_id"))

                    if not recipient:
                        update_ticket_email_result(
                            ticket_id, "NOT_CONFIGURED"
                        )
                        app.logger.warning(
                            "Escalation email skipped: no registered email "
                            "for ticket %s.",
                            ticket_id,
                        )
                    else:
                        update_ticket_email_result(ticket_id, "PENDING")

                        send_support_ticket_notification(
                            ticket={
                                **ticket,
                                "ticket_id": ticket_id,
                                "status": final_status,
                            },
                            recipient_email=recipient,
                            jira_issue_key=jira_result.get("jira_issue_key"),
                            jira_url=jira_result.get("jira_issue_url"),
                        )

                        update_ticket_email_result(ticket_id, "SENT")
                        app.logger.info(
                            "Escalation email sent to requester for ticket %s.",
                            ticket_id,
                        )

            except EmailConfigurationError:
                update_ticket_email_result(ticket_id, "NOT_CONFIGURED")
                app.logger.warning(
                    "Email notification not configured for ticket %s.",
                    ticket_id,
                )

            except (EmailDeliveryError, ValueError):
                update_ticket_email_result(ticket_id, "FAILED")
                app.logger.exception(
                    "Email notification failed for ticket %s.",
                    ticket_id,
                )

            except Exception:
                update_ticket_email_result(ticket_id, "FAILED")
                app.logger.exception(
                    "Unexpected email notification error for ticket %s.",
                    ticket_id,
                )
         # Load the final notification data for every workflow outcome.
        email_tracking = get_ticket_email_result(ticket_id) or {}
        email_recipient = get_user_email(ticket.get("user_id"))
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

            # Jira integration status
            "jira_issue_key": jira_result.get("jira_issue_key"),
            "jira_issue_url": jira_result.get("jira_issue_url"),
            "jira_sync_status": jira_result.get("jira_sync_status"),

            # Email notification status
            "email_notification_status": email_tracking.get(
                "email_notification_status", "UNKNOWN"
            ),
            "email_notification_sent_at": email_tracking.get(
                "email_notification_sent_at"
            ),
            "email_recipient": email_recipient,

            "message": (
                "Human review is required."
                if needs_escalation
                else (
                    "The ticket was automatically marked AI-resolved "
                    "after passing all approval gates."
                )
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

        "milestone": "Milestone 3",

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

@app.route(
    "/api/tickets/<int:ticket_id>/feedback",
    methods=["POST"],
)
def submit_ticket_feedback(ticket_id):
    """Save satisfaction feedback for a ticket owned by the logged-in user."""

    if not session.get("user_id"):
        return jsonify({
            "success": False,
            "message": "Please log in before rating a ticket.",
        }), 401

    try:
        user_id = int(session["user_id"])
    except (TypeError, ValueError):
        return jsonify({
            "success": False,
            "message": "Invalid user session. Please log in again.",
        }), 401

    # Ensure the logged-in user owns this ticket.
    ticket = get_ticket(ticket_id, user_id=user_id)

    if ticket is None:
        return jsonify({
            "success": False,
            "message": "Ticket not found or you do not have access.",
        }), 404

    payload = request.get_json(silent=True)

    if not isinstance(payload, dict):
        return jsonify({
            "success": False,
            "message": "A JSON rating is required.",
        }), 400

    rating = payload.get("rating")

    if type(rating) is not int or rating not in (1, 2, 3, 4, 5):
        return jsonify({
            "success": False,
            "message": "Rating must be an integer from 1 to 5.",
        }), 400

    try:
        save_ticket_satisfaction_rating(ticket_id, rating)
    except Exception:
        app.logger.exception(
            "Could not save satisfaction rating for ticket %s",
            ticket_id,
        )
        return jsonify({
            "success": False,
            "message": "Unable to save the rating. Please try again.",
        }), 500

    return jsonify({
        "success": True,
        "message": "Thank you! Your satisfaction rating has been saved.",
        "ticket_id": ticket_id,
        "rating": rating,
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
