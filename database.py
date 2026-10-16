import json
import sqlite3
from pathlib import Path
from datetime import datetime


# ==========================================================
# DATABASE PATH
# ==========================================================

DB_PATH = (
    Path(__file__).resolve().parent
    / "healthcare_support.db"
)


# ==========================================================
# DATABASE CONNECTION
# ==========================================================

def get_connection():

    return sqlite3.connect(
        DB_PATH
    )


# ==========================================================
# INITIALIZE DATABASE
# ==========================================================

def init_db():

    with get_connection() as conn:

        conn.execute("""
            CREATE TABLE IF NOT EXISTS support_tickets (

                ticket_id INTEGER
                PRIMARY KEY AUTOINCREMENT,

                requester_name TEXT,

                department TEXT,

                title TEXT,

                description TEXT NOT NULL,

                category TEXT,

                severity TEXT,

                priority TEXT,

                confidence REAL,
                final_confidence REAL,

                status TEXT,

                escalation_reasons TEXT NOT NULL DEFAULT '[]',

                ai_resolved INTEGER NOT NULL DEFAULT 0,

                created_at TEXT
            )
        """)

        columns = {
            row[1]
            for row in conn.execute(
                "PRAGMA table_info(support_tickets)"
            ).fetchall()
        }
        if "escalation_reasons" not in columns:
            conn.execute(
                "ALTER TABLE support_tickets "
                "ADD COLUMN escalation_reasons TEXT NOT NULL DEFAULT '[]'"
            )
        if "ai_resolved" not in columns:
            conn.execute(
                "ALTER TABLE support_tickets "
                "ADD COLUMN ai_resolved INTEGER NOT NULL DEFAULT 0"
            )

        if "generation_time_ms" not in columns:
            conn.execute(
                "ALTER TABLE support_tickets "
                "ADD COLUMN generation_time_ms REAL"
            )
        if "pipeline_response_time_ms" not in columns:
            conn.execute(
                "ALTER TABLE support_tickets "
                "ADD COLUMN pipeline_response_time_ms REAL"
            )
        if "knowledge_base_covered" not in columns:
            conn.execute(
                "ALTER TABLE support_tickets "
                "ADD COLUMN knowledge_base_covered INTEGER"
            )
        if "verified_category" not in columns:
            conn.execute(
                "ALTER TABLE support_tickets "
                "ADD COLUMN verified_category TEXT"
            )

        if "category_verified_at" not in columns:
            conn.execute(
                "ALTER TABLE support_tickets "
                "ADD COLUMN category_verified_at TEXT"
            )
        if "resolution_confirmed" not in columns:
            conn.execute(
        "ALTER TABLE support_tickets "
        "ADD COLUMN resolution_confirmed INTEGER NOT NULL DEFAULT 0"
    )
        # Record when resolution is explicitly confirmed.
        if "resolved_at" not in columns:
            conn.execute(
                "ALTER TABLE support_tickets "
                "ADD COLUMN resolved_at TEXT"
            )

        if "agent_attempt_count" not in columns:
            conn.execute(
                "ALTER TABLE support_tickets "
                "ADD COLUMN agent_attempt_count INTEGER NOT NULL DEFAULT 0"
            )
        if "user_id" not in columns:
            conn.execute(
                "ALTER TABLE support_tickets "
                "ADD COLUMN user_id INTEGER"
            )
        # Add final AI validation confidence to existing databases.
        if "final_confidence" not in columns:
            conn.execute(
                "ALTER TABLE support_tickets "
                "ADD COLUMN final_confidence REAL"
            )

        # Jira integration tracking columns
        if "jira_issue_key" not in columns:
            conn.execute(
                "ALTER TABLE support_tickets "
                "ADD COLUMN jira_issue_key TEXT"
            )

        if "jira_issue_url" not in columns:
            conn.execute(
                "ALTER TABLE support_tickets "
                "ADD COLUMN jira_issue_url TEXT"
            )

        if "jira_sync_status" not in columns:
            conn.execute(
                "ALTER TABLE support_tickets "
                "ADD COLUMN jira_sync_status TEXT NOT NULL DEFAULT 'NOT_CONFIGURED'"
            )
          # SMTP notification tracking columns
        if "email_notification_status" not in columns:
            conn.execute(
                "ALTER TABLE support_tickets "
                "ADD COLUMN email_notification_status "
                "TEXT NOT NULL DEFAULT 'NOT_CONFIGURED'"
            )

        if "email_notification_sent_at" not in columns:
            conn.execute(
                "ALTER TABLE support_tickets "
                "ADD COLUMN email_notification_sent_at TEXT"
            )
                # Customer satisfaction tracking
        if "customer_satisfaction_rating" not in columns:
            conn.execute(
                "ALTER TABLE support_tickets "
                "ADD COLUMN customer_satisfaction_rating INTEGER"
            )

        if "customer_satisfaction_at" not in columns:
            conn.execute(
                "ALTER TABLE support_tickets "
                "ADD COLUMN customer_satisfaction_at TEXT"
            )


        conn.execute("""
            CREATE TABLE IF NOT EXISTS ai_resolution_attempts (
                attempt_id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket_id INTEGER NOT NULL,
                attempted_at TEXT NOT NULL,
                outcome TEXT NOT NULL DEFAULT 'STARTED',
                FOREIGN KEY (ticket_id)
                    REFERENCES support_tickets(ticket_id)
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS ticket_classification_events (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket_id INTEGER NOT NULL,
                classified_at TEXT NOT NULL,
                category TEXT,
                confidence REAL,
                FOREIGN KEY (ticket_id)
                    REFERENCES support_tickets(ticket_id)
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS ticket_validation_events (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket_id INTEGER NOT NULL,
                started_at TEXT NOT NULL,
                completed_at TEXT,
                status TEXT NOT NULL DEFAULT 'PENDING',
                approved INTEGER,
                FOREIGN KEY (ticket_id)
                    REFERENCES support_tickets(ticket_id)
            )
        """)

        conn.execute("""
                CREATE TABLE IF NOT EXISTS ticket_multiagent_runs (
                    ticket_id INTEGER PRIMARY KEY,
                    started_at TEXT NOT NULL,
                    FOREIGN KEY (ticket_id)
                        REFERENCES support_tickets(ticket_id)
                )
            """)
                # Store periodic application health-check results.
        conn.execute("""
            CREATE TABLE IF NOT EXISTS system_health_checks (
                check_id INTEGER PRIMARY KEY AUTOINCREMENT,
                checked_at TEXT NOT NULL,
                is_healthy INTEGER NOT NULL
                    CHECK (is_healthy IN (0, 1)),
                response_time_ms REAL,
                status_code INTEGER,
                error_message TEXT
            )
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_health_checks_checked_at
            ON system_health_checks(checked_at)
        """)
        conn.commit()

# ==========================================================
# SAVE TICKET
# ==========================================================

def save_ticket(data):

    with get_connection() as conn:

        cursor = conn.execute(
            """
            INSERT INTO support_tickets
            (
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
                user_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                data.get("requester_name"),
                data.get("department"),
                data.get("title"),
                data["description"],
                data.get("category"),
                data.get("severity"),
                data.get("priority"),
                data.get("confidence"),
                data.get("status", "Open"),
                data.get("escalation_reasons", "[]"),
                int(data.get("ai_resolved", False)),
                datetime.now().isoformat(timespec="seconds"),
                data.get("user_id"),
            )
        )

        conn.commit()

        return cursor.lastrowid


# ==========================================================
# GET TICKET
# ==========================================================

def get_ticket(ticket_id, user_id=None):
    """
    Retrieve one support ticket by ticket ID.
    When user_id is supplied, return only tickets owned by that user.
    """
    with get_connection() as conn:
        conn.row_factory = sqlite3.Row

        if user_id is None:
            row = conn.execute(
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
                    user_id,
                    resolution_confirmed
                FROM support_tickets
                WHERE ticket_id = ?
                """,
                (ticket_id,)
            ).fetchone()
        else:
            row = conn.execute(
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
                    user_id,
                    resolution_confirmed
                FROM support_tickets
                WHERE ticket_id = ? AND user_id = ?
                """,
                (ticket_id, user_id)
            ).fetchone()

        if row is None:
            return None

        return dict(row)

def update_ticket_final_confidence(ticket_id, confidence):
    """Store the final Multi-Agent validation confidence (0-100)."""

    with get_connection() as conn:
        cursor = conn.execute(
            """
            UPDATE support_tickets
            SET final_confidence = ?
            WHERE ticket_id = ?
            """,
            (confidence, ticket_id),
        )

        if cursor.rowcount != 1:
            raise LookupError(
                f"Ticket {ticket_id} was not found."
            )

        conn.commit()


# ==========================================================
# UPDATE TICKET STATUS
# ==========================================================

def update_ticket_status(ticket_id, status):
    """Update a ticket's workflow status."""

    with get_connection() as conn:

        cursor = conn.execute(
            """
            UPDATE support_tickets
            SET status = ?
            WHERE ticket_id = ?
            """,
            (status, ticket_id)
        )

        if cursor.rowcount != 1:
            raise LookupError(
                f"Ticket {ticket_id} was not found while updating status"
            )

        conn.commit()


def update_ticket_escalation_reasons(ticket_id, reasons):
    """Persist the safety rules that triggered escalation for a ticket."""

    with get_connection() as conn:
        cursor = conn.execute(
            """
            UPDATE support_tickets
            SET escalation_reasons = ?
            WHERE ticket_id = ?
            """,
            (json.dumps(sorted(set(reasons))), ticket_id)
        )

        if cursor.rowcount != 1:
            raise LookupError(
                f"Ticket {ticket_id} was not found while updating escalation reasons"
            )

        conn.commit()


def update_ticket_ai_resolved(ticket_id, resolved):
    """Record whether the RAG flow generated an AI resolution."""

    with get_connection() as conn:
        cursor = conn.execute(
            """
            UPDATE support_tickets
            SET ai_resolved = ?
            WHERE ticket_id = ?
            """,
            (int(resolved), ticket_id)
        )

        if cursor.rowcount != 1:
            raise LookupError(
                f"Ticket {ticket_id} was not found while updating AI resolution"
            )

        conn.commit()
def update_ticket_resolution_confirmed(ticket_id, confirmed):
    """Record resolution confirmation and its timestamp."""

    if confirmed not in (True, False, 0, 1):
        raise ValueError("confirmed must be True, False, 0, or 1")

    from datetime import datetime

    confirmation_value = int(confirmed)
    confirmed_at = datetime.now().isoformat(timespec="seconds")

    with get_connection() as conn:
        cursor = conn.execute(
            """
            UPDATE support_tickets
            SET resolved_at = CASE
                    WHEN ? = 1 AND resolution_confirmed = 0
                        THEN ?
                    WHEN ? = 0
                        THEN NULL
                    ELSE resolved_at
                END,
                resolution_confirmed = ?
            WHERE ticket_id = ?
            """,
            (
                confirmation_value,
                confirmed_at,
                confirmation_value,
                confirmation_value,
                ticket_id,
            ),
        )

        if cursor.rowcount != 1:
            raise LookupError(
                f"Ticket {ticket_id} was not found."
            )

        conn.commit()


def update_ticket_generation_time(ticket_id, generation_time_ms):
    """Save measured AI response-generation time in milliseconds."""
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE support_tickets
            SET generation_time_ms = ?
            WHERE ticket_id = ?
            """,
            (generation_time_ms, ticket_id),
        )


def update_ticket_pipeline_response_time(ticket_id, response_time_ms):
    """Store elapsed time for the complete RAG pipeline call."""
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE support_tickets
            SET pipeline_response_time_ms = ?
            WHERE ticket_id = ?
            """,
            (response_time_ms, ticket_id),
        )
def update_ticket_knowledge_base_coverage(ticket_id, covered):
    """Record whether relevant knowledge-base evidence was retrieved."""
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE support_tickets
            SET knowledge_base_covered = ?
            WHERE ticket_id = ?
            """,
            (1 if covered else 0, ticket_id),
        )
        # ==========================================================
# JIRA INTEGRATION TRACKING
# ==========================================================

def update_ticket_jira_result(
    ticket_id,
    sync_status,
    issue_key=None,
    issue_url=None,
):
    """Persist the Jira synchronization result for a ticket."""

    allowed_statuses = {
        "NOT_CONFIGURED",
        "PENDING",
        "SYNCED",
        "FAILED",
    }

    if sync_status not in allowed_statuses:
        raise ValueError("Invalid Jira synchronization status")

    with get_connection() as conn:
        cursor = conn.execute(
            """
            UPDATE support_tickets
            SET jira_sync_status = ?,
                jira_issue_key = ?,
                jira_issue_url = ?
            WHERE ticket_id = ?
            """,
            (
                sync_status,
                issue_key,
                issue_url,
                ticket_id,
            ),
        )

        if cursor.rowcount != 1:
            raise LookupError(
                f"Ticket {ticket_id} was not found while updating Jira status"
            )

        conn.commit()


def get_ticket_jira_result(ticket_id):
    """Return Jira tracking fields for a saved ticket."""

    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT
                ticket_id,
                jira_issue_key,
                jira_issue_url,
                jira_sync_status
            FROM support_tickets
            WHERE ticket_id = ?
            """,
            (ticket_id,),
        ).fetchone()

        if row is None:
            return None

        return {
            "ticket_id": row[0],
            "jira_issue_key": row[1],
            "jira_issue_url": row[2],
            "jira_sync_status": row[3],
        }

        # ==========================================================
# EMAIL NOTIFICATION TRACKING
# ==========================================================
def get_ticket_email_result(ticket_id):
    """Return the stored email notification status for a ticket."""
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT email_notification_status,
                   email_notification_sent_at
            FROM support_tickets
            WHERE ticket_id = ?
            """,
            (ticket_id,),
        ).fetchone()

    if row is None:
        return None

    return {
        "email_notification_status": row[0],
        "email_notification_sent_at": row[1],
    }

def update_ticket_email_result(ticket_id, status):
    """Persist the delivery status of a support notification."""

    allowed_statuses = {
        "NOT_CONFIGURED",
        "PENDING",
        "SENT",
        "FAILED",
    }

    if status not in allowed_statuses:
        raise ValueError("Invalid email notification status")

    with get_connection() as conn:
        cursor = conn.execute(
            """
            UPDATE support_tickets
            SET email_notification_status = ?,
                email_notification_sent_at = CASE
                    WHEN ? = 'SENT'
                    THEN COALESCE(
                        email_notification_sent_at,
                        ?
                    )
                    ELSE email_notification_sent_at
                END
            WHERE ticket_id = ?
            """,
            (
                status,
                status,
                datetime.now().isoformat(timespec="seconds"),
                ticket_id,
            ),
        )

        if cursor.rowcount != 1:
            raise LookupError(
                f"Ticket {ticket_id} was not found while updating email status"
            )

        conn.commit()

def increment_agent_attempt_count(ticket_id):
    """Increment and return the multi-agent run count for a ticket."""

    with get_connection() as conn:
        cursor = conn.execute(
            """
            UPDATE support_tickets
            SET agent_attempt_count = COALESCE(agent_attempt_count, 0) + 1
            WHERE ticket_id = ?
            """,
            (ticket_id,),
        )

        if cursor.rowcount != 1:
            raise LookupError(
                f"Ticket {ticket_id} was not found while updating agent attempts"
            )

        row = conn.execute(
            """
            SELECT agent_attempt_count
            FROM support_tickets
            WHERE ticket_id = ?
            """,
            (ticket_id,),
        ).fetchone()

        return row[0]

def record_ai_resolution_attempt(ticket_id):
    """Record a timestamped AI resolution attempt and return its ID."""

    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO ai_resolution_attempts
                (ticket_id, attempted_at, outcome)
            VALUES (?, ?, 'STARTED')
            """,
            (
                ticket_id,
                datetime.now().isoformat(timespec="seconds"),
            ),
        )
        conn.commit()
        return cursor.lastrowid


def update_ai_resolution_attempt(attempt_id, outcome):
    """Update the outcome of a recorded AI resolution attempt."""

    allowed_outcomes = {
        "SUCCEEDED",
        "FAILED",
        "ESCALATED",
    }

    if outcome not in allowed_outcomes:
        raise ValueError("Invalid AI resolution attempt outcome.")

    with get_connection() as conn:
        cursor = conn.execute(
            """
            UPDATE ai_resolution_attempts
            SET outcome = ?
            WHERE attempt_id = ?
            """,
            (outcome, attempt_id),
        )

        if cursor.rowcount != 1:
            raise LookupError(
                f"AI resolution attempt {attempt_id} was not found"
            )

        conn.commit()


def count_ai_resolution_attempts_today():
    """Count AI resolution attempts recorded on the server's local date."""

    from datetime import date, timedelta

    today = date.today()
    start = today.isoformat() + "T00:00:00"
    end = (today + timedelta(days=1)).isoformat() + "T00:00:00"

    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT COUNT(*)
            FROM ai_resolution_attempts
            WHERE attempted_at >= ?
              AND attempted_at < ?
            """,
            (start, end),
        ).fetchone()

        return row[0]


def record_ticket_classification(ticket_id, category, confidence):
    """Record a successful ticket classification event."""
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO ticket_classification_events
                (ticket_id, classified_at, category, confidence)
            VALUES (?, ?, ?, ?)
            """,
            (
                ticket_id,
                datetime.now().isoformat(timespec="seconds"),
                category,
                confidence,
            ),
        )
        conn.commit()


def count_ticket_classifications_today():
    """Count successful classification events recorded today."""
    from datetime import date, timedelta

    today = date.today()
    start = today.isoformat() + "T00:00:00"
    end = (today + timedelta(days=1)).isoformat() + "T00:00:00"

    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT COUNT(*)
            FROM ticket_classification_events
            WHERE classified_at >= ?
              AND classified_at < ?
            """,
            (start, end),
        ).fetchone()

        return row[0]


def record_ticket_validation_start(ticket_id):
    """Record that validation has started for a ticket."""
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO ticket_validation_events
                (ticket_id, started_at, status)
            VALUES (?, ?, 'PENDING')
            """,
            (
                ticket_id,
                datetime.now().isoformat(timespec="seconds"),
            ),
        )
        conn.commit()
        return cursor.lastrowid


def complete_ticket_validation(event_id, approved):
    """Record the final validation outcome."""
    if approved not in (True, False):
        raise ValueError("approved must be True or False.")

    status = "APPROVED" if approved else "REJECTED"

    with get_connection() as conn:
        cursor = conn.execute(
            """
            UPDATE ticket_validation_events
            SET completed_at = ?, status = ?, approved = ?
            WHERE event_id = ? AND status = 'PENDING'
            """,
            (
                datetime.now().isoformat(timespec="seconds"),
                status,
                int(approved),
                event_id,
            ),
        )

        if cursor.rowcount != 1:
            raise LookupError(
                f"Pending validation event {event_id} was not found"
            )

        conn.commit()

def cancel_pending_ticket_validation(event_id):
    """Close a validation queue entry when the workflow exits early."""
    with get_connection() as conn:
        cursor = conn.execute(
            """
            UPDATE ticket_validation_events
            SET completed_at = ?, status = 'CANCELLED', approved = 0
            WHERE event_id = ? AND status = 'PENDING'
            """,
            (
                datetime.now().isoformat(timespec="seconds"),
                event_id,
            ),
        )

        conn.commit()
        return cursor.rowcount == 1



def record_ticket_multiagent_start(ticket_id):
    """Record the first multi-agent run for a ticket."""
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT OR IGNORE INTO ticket_multiagent_runs
                (ticket_id, started_at)
            VALUES (?, ?)
            """,
            (
                ticket_id,
                datetime.now().isoformat(timespec="seconds"),
            ),
        )
        conn.commit()
        return cursor.rowcount == 1


def count_pending_ticket_validations():
    """Count submitted tickets not yet run through multi-agent."""
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT COUNT(*)
            FROM support_tickets AS t
            WHERE NOT EXISTS (
                SELECT 1
                FROM ticket_multiagent_runs AS r
                WHERE r.ticket_id = t.ticket_id
            )
            """
        ).fetchone()

        return row[0]

def count_unfinished_validation_events():
    """Count validation events that have not completed."""
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT COUNT(*)
            FROM ticket_validation_events
            WHERE status = 'PENDING'
            """
        ).fetchone()

        return row[0]
def save_ticket_satisfaction_rating(ticket_id, rating):
    """Save a customer's 1–5 satisfaction rating for a ticket."""

    if type(rating) is not int or rating not in (1, 2, 3, 4, 5):
        raise ValueError("Rating must be an integer between 1 and 5.")

    with get_connection() as conn:
        cursor = conn.execute(
            """
            UPDATE support_tickets
            SET customer_satisfaction_rating = ?,
                customer_satisfaction_at = ?
            WHERE ticket_id = ?
            """,
            (
                rating,
                datetime.now().isoformat(timespec="seconds"),
                ticket_id,
            ),
        )

        if cursor.rowcount != 1:
            raise LookupError(f"Ticket {ticket_id} was not found.")

        conn.commit()

def update_ticket_category_verification(ticket_id, verified_category):
    """Store the human-verified category and verification timestamp."""
    verified_category = str(verified_category or "").strip()

    if not verified_category:
        raise ValueError("Verified category cannot be empty.")

    with get_connection() as conn:
        cursor = conn.execute(
            """
            UPDATE support_tickets
            SET verified_category = ?,
                category_verified_at = ?
            WHERE ticket_id = ?
            """,
            (
                verified_category,
                datetime.now().isoformat(timespec="seconds"),
                ticket_id,
            ),
        )
        return cursor.rowcount > 0
