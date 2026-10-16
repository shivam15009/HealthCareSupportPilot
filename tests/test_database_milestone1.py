"""Standard-library tests for database_milestone1.py.

Run from the project directory:
    python -m unittest discover -s tests -p "test_database_milestone1.py" -v
The test uses a temporary database and never touches production/local databases.
"""
import os
import tempfile
import unittest
import sqlite3
from pathlib import Path

import database_milestone1 as db


class Milestone1DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        db.DB_PATH = Path(self.temp_dir.name) / "test.db"
        db.init_db()

    def tearDown(self):
        self.temp_dir.cleanup()

    def sample_ticket(self, **overrides):
        data = {
            "user_id": 7,
            "requester_name": "Test User",
            "department": "Registration",
            "title": "Cannot register a patient",
            "description": "The patient registration form fails to submit.",
            "category": "Patient Registration",
            "severity": "Medium",
            "priority": "P2",
            "confidence": 0.92,
            "status": "Open",
        }
        data.update(overrides)
        return data

    def test_save_and_get_ticket(self):
        ticket_id = db.save_ticket(self.sample_ticket())
        ticket = db.get_ticket(ticket_id)
        self.assertIsNotNone(ticket)
        self.assertEqual(ticket["ticket_id"], ticket_id)
        self.assertEqual(ticket["status"], "Open")
        self.assertEqual(ticket["category"], "Patient Registration")

    def test_ticket_ids_are_unique(self):
        first = db.save_ticket(self.sample_ticket())
        second = db.save_ticket(self.sample_ticket(title="Second ticket"))
        self.assertNotEqual(first, second)

    def test_owner_filter_prevents_cross_user_read(self):
        ticket_id = db.save_ticket(self.sample_ticket(user_id=7))
        self.assertIsNone(db.get_ticket(ticket_id, user_id=8))
        self.assertIsNotNone(db.get_ticket(ticket_id, user_id=7))

    def test_empty_description_rejected(self):
        with self.assertRaises(ValueError):
            db.save_ticket(self.sample_ticket(description="  "))

    def test_confidence_out_of_range_rejected(self):
        with self.assertRaises(ValueError):
            db.save_ticket(self.sample_ticket(confidence=1.5))

    def test_classification_event_is_recorded(self):
        ticket_id = db.save_ticket(self.sample_ticket())
        db.record_ticket_classification(ticket_id, "Patient Registration", 0.92)
        with db.get_connection() as conn:
            count = conn.execute(
                "SELECT COUNT(*) FROM ticket_classification_events WHERE ticket_id = ?",
                (ticket_id,),
            ).fetchone()[0]
        self.assertEqual(count, 1)

    def test_missing_ticket_classification_rejected_by_foreign_key(self):
        with self.assertRaises(sqlite3.IntegrityError):
            db.record_ticket_classification(99999, "Billing", 0.8)

    def test_list_tickets_can_filter_by_user(self):
        db.save_ticket(self.sample_ticket(user_id=7))
        db.save_ticket(self.sample_ticket(user_id=8, title="Other user ticket"))
        self.assertEqual(len(db.list_tickets(user_id=7)), 1)
        self.assertEqual(len(db.list_tickets()), 2)


if __name__ == "__main__":
    unittest.main()
