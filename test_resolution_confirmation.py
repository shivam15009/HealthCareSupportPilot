
import os
import tempfile
import unittest
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent
load_dotenv(PROJECT_ROOT / ".env")

os.environ.setdefault("FLASK_SECRET_KEY", "test-only-flask-secret")
os.environ.setdefault("JWT_SECRET_KEY", "test-only-jwt-secret")

import database

TEMP_DIR = tempfile.TemporaryDirectory(
    prefix="resolution_confirmation_test_",
    ignore_cleanup_errors=True,
)
database.DB_PATH = Path(TEMP_DIR.name) / "test_support.db"

import app as flask_app


class ResolutionConfirmationTest(unittest.TestCase):
    def setUp(self):
        database.init_db()
        self.client = flask_app.app.test_client()

        with self.client.session_transaction() as session:
            session["user_id"] = 123

        self.ticket_id = database.save_ticket({
            "requester_name": "Resolution Test User",
            "department": "IT",
            "title": "Resolution confirmation test",
            "description": "Test-only operational support issue.",
            "category": "Access",
            "severity": "Medium",
            "priority": "P3",
            "confidence": 90.0,
            "status": "OPEN",
            "user_id": 123,
            "escalation_reasons": "[]",
        })

    def tearDown(self):
        with database.get_connection() as conn:
            conn.execute(
                "DELETE FROM support_tickets WHERE ticket_id = ?",
                (self.ticket_id,),
            )
            conn.commit()

    def test_unauthenticated_confirmation_is_rejected(self):
        with self.client.session_transaction() as session:
            session.clear()

        response = self.client.post(
            f"/api/tickets/{self.ticket_id}/resolution-confirmation",
            json={"confirmed": True},
        )

        self.assertEqual(response.status_code, 401)

    def test_confirmation_updates_database(self):
        response = self.client.post(
            f"/api/tickets/{self.ticket_id}/resolution-confirmation",
            json={"confirmed": True},
        )

        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertTrue(response.get_json()["resolution_confirmed"])

        ticket = database.get_ticket(self.ticket_id, user_id=123)
        self.assertEqual(ticket["resolution_confirmed"], 1)

    def test_unresolved_confirmation_clears_flag(self):
        database.update_ticket_resolution_confirmed(self.ticket_id, True)

        response = self.client.post(
            f"/api/tickets/{self.ticket_id}/resolution-confirmation",
            json={"confirmed": False},
        )

        self.assertEqual(response.status_code, 200, response.get_json())

        ticket = database.get_ticket(self.ticket_id, user_id=123)
        self.assertEqual(ticket["resolution_confirmed"], 0)

    def test_other_users_cannot_confirm_ticket(self):
        with self.client.session_transaction() as session:
            session["user_id"] = 456

        response = self.client.post(
            f"/api/tickets/{self.ticket_id}/resolution-confirmation",
            json={"confirmed": True},
        )

        self.assertEqual(response.status_code, 404)

        ticket = database.get_ticket(self.ticket_id)
        self.assertEqual(ticket["resolution_confirmed"], 0)

    def test_invalid_confirmation_value_is_rejected(self):
        response = self.client.post(
            f"/api/tickets/{self.ticket_id}/resolution-confirmation",
            json={"confirmed": "yes"},
        )

        self.assertEqual(response.status_code, 400)

        ticket = database.get_ticket(self.ticket_id, user_id=123)
        self.assertEqual(ticket["resolution_confirmed"], 0)


if __name__ == "__main__":
    unittest.main()
