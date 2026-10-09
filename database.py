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
                created_at
            )

            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,

            (
                data.get(
                    "requester_name"
                ),

                data.get(
                    "department"
                ),

                data.get(
                    "title"
                ),

                data["description"],

                data.get(
                    "category"
                ),

                data.get(
                    "severity"
                ),

                data.get(
                    "priority"
                ),

                data.get(
                    "confidence"
                ),

                data.get(
                    "status",
                    "Open"
                ),

                data.get(
                    "escalation_reasons",
                    "[]"
                ),

                int(data.get("ai_resolved", False)),

                datetime.now().isoformat(
                    timespec="seconds"
                )
            )
        )

        conn.commit()

        return cursor.lastrowid


# ==========================================================
# GET TICKET
# ==========================================================

def get_ticket(ticket_id):
    """
    Retrieve one support ticket by ticket ID.
    """

    with get_connection() as conn:

        conn.row_factory = sqlite3.Row

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
                created_at
            FROM support_tickets
            WHERE ticket_id = ?
            """,
            (ticket_id,)
        ).fetchone()

        if row is None:

            return None

        return dict(row)


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