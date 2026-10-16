"""Minimal, isolated SQLite storage for Healthcare SupportPilot Milestone 1.

This module intentionally uses a NEW database file so the existing databases are
not modified during development. Set MILESTONE1_DB_PATH to override the default.
"""
from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Mapping
from contextlib import contextmanager

DEFAULT_DB_PATH = Path(__file__).resolve().parent / "healthcare_support_milestone1.db"
DB_PATH = Path(os.environ.get("MILESTONE1_DB_PATH", str(DEFAULT_DB_PATH)))


@contextmanager
def get_connection() -> Iterator[sqlite3.Connection]:
    """Yield a connection and always close it after the transaction."""
    conn = sqlite3.connect(str(DB_PATH), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def init_db() -> None:
    """Create the minimal Milestone 1 schema without altering existing databases."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS support_tickets (
                ticket_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                requester_name TEXT,
                department TEXT,
                title TEXT,
                description TEXT NOT NULL CHECK (length(trim(description)) > 0),
                category TEXT NOT NULL,
                severity TEXT NOT NULL,
                priority TEXT NOT NULL,
                confidence REAL NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
                status TEXT NOT NULL DEFAULT 'Open'
                    CHECK (status IN ('Open', 'In Progress', 'Closed')),
                created_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_m1_tickets_user_created
            ON support_tickets(user_id, created_at DESC)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_m1_tickets_category
            ON support_tickets(category)
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS ticket_classification_events (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket_id INTEGER NOT NULL,
                classified_at TEXT NOT NULL,
                category TEXT NOT NULL,
                confidence REAL NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
                FOREIGN KEY (ticket_id) REFERENCES support_tickets(ticket_id)
                    ON DELETE CASCADE
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_m1_classification_time
            ON ticket_classification_events(classified_at)
        """)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def save_ticket(data: Mapping[str, Any]) -> int:
    """Insert a ticket and return its unique integer ID."""
    description = data.get("description")
    if not isinstance(description, str) or not description.strip():
        raise ValueError("description must be a non-empty string")

    category = data.get("category")
    severity = data.get("severity")
    priority = data.get("priority")
    if not all(isinstance(v, str) and v.strip() for v in (category, severity, priority)):
        raise ValueError("category, severity, and priority are required")

    confidence = float(data.get("confidence", 0.0))
    if not 0.0 <= confidence <= 1.0:
        raise ValueError("confidence must be between 0 and 1")

    status = data.get("status", "Open")
    if status not in {"Open", "In Progress", "Closed"}:
        raise ValueError("invalid status")

    with get_connection() as conn:
        cursor = conn.execute("""
            INSERT INTO support_tickets (
                user_id, requester_name, department, title, description,
                category, severity, priority, confidence, status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            data.get("user_id"),
            data.get("requester_name"),
            data.get("department"),
            data.get("title"),
            description.strip(),
            category.strip(),
            severity.strip(),
            priority.strip(),
            confidence,
            status,
            _now_iso(),
        ))
        return int(cursor.lastrowid)


def get_ticket(ticket_id: int, user_id: int | None = None) -> dict[str, Any] | None:
    """Get a ticket, optionally restricting it to its owner."""
    with get_connection() as conn:
        if user_id is None:
            row = conn.execute(
                "SELECT * FROM support_tickets WHERE ticket_id = ?",
                (ticket_id,),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT * FROM support_tickets WHERE ticket_id = ? AND user_id = ?",
                (ticket_id, user_id),
            ).fetchone()
        return dict(row) if row else None


def list_tickets(user_id: int | None = None, limit: int = 500) -> list[dict[str, Any]]:
    """List recent tickets, optionally limited to one user."""
    if not isinstance(limit, int) or limit < 1 or limit > 5000:
        raise ValueError("limit must be an integer from 1 to 5000")
    with get_connection() as conn:
        if user_id is None:
            rows = conn.execute(
                "SELECT * FROM support_tickets ORDER BY created_at DESC, ticket_id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT * FROM support_tickets WHERE user_id = ?
                   ORDER BY created_at DESC, ticket_id DESC LIMIT ?""",
                (user_id, limit),
            ).fetchall()
        return [dict(row) for row in rows]


def record_ticket_classification(ticket_id: int, category: str, confidence: float) -> None:
    """Record a classification event for a ticket that already exists."""
    confidence = float(confidence)
    if not 0.0 <= confidence <= 1.0:
        raise ValueError("confidence must be between 0 and 1")
    if not isinstance(category, str) or not category.strip():
        raise ValueError("category is required")

    with get_connection() as conn:
        conn.execute("""
            INSERT INTO ticket_classification_events
                (ticket_id, classified_at, category, confidence)
            VALUES (?, ?, ?, ?)
        """, (ticket_id, _now_iso(), category.strip(), confidence))


def count_ticket_classifications_today() -> int:
    """Count classification events created on the current UTC date."""
    today = datetime.now(timezone.utc).date().isoformat()
    with get_connection() as conn:
        row = conn.execute("""
            SELECT COUNT(*) FROM ticket_classification_events
            WHERE substr(classified_at, 1, 10) = ?
        """, (today,)).fetchone()
        return int(row[0])
