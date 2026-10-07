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

                created_at TEXT
            )
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
                created_at
            )

            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                created_at
            FROM support_tickets
            WHERE ticket_id = ?
            """,
            (ticket_id,)
        ).fetchone()

        if row is None:

            return None

        return dict(row)