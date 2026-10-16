
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent
load_dotenv(PROJECT_ROOT / ".env")

os.environ.setdefault("FLASK_SECRET_KEY", "test-only-flask-secret")
os.environ.setdefault("JWT_SECRET_KEY", "test-only-jwt-secret")

import database

TEMP_DIR = tempfile.TemporaryDirectory(
    prefix="healthcare_route_test_",
    ignore_cleanup_errors=True,
)
database.DB_PATH = Path(TEMP_DIR.name) / "test_healthcare_support.db"

import app as flask_app


class TicketClassificationRouteTest(unittest.TestCase):
    def setUp(self):
        database.init_db()
        self.client = flask_app.app.test_client()

        with self.client.session_transaction() as session:
            session["user_id"] = 123
            session["requester_name"] = "Route Test User"

    @patch("app.send_support_ticket_notification")
    @patch("app.create_jira_issue")
    def test_ticket_submission_classifies_and_saves_without_jira(
        self, mock_jira, mock_email
    ):
        with (
            patch("app.classify_query", return_value={
                "success": True,
                "category": "Access",
                "confidence": 0.99,
            }),
            patch("app.operational_severity", return_value="High"),
            patch("app.operational_priority", return_value="High"),
        ):
            response = self.client.post(
                "/api/ticket",
                json={
                    "title": "Route classification test",
                    "description": "Test-only ticket; no real user information.",
                    "department": "IT",
                },
            )

        self.assertEqual(
            response.status_code, 201, response.get_data(as_text=True)
        )

        body = response.get_json()
        self.assertTrue(body.get("ticket_id"))
        self.assertEqual(body["category"], "Access")
        self.assertEqual(body["severity"], "High")
        self.assertEqual(body["priority"], "High")
        self.assertAlmostEqual(body["confidence"], 99.0)

        stored = database.get_ticket(
            body["ticket_id"], user_id=123
        )
        self.assertIsNotNone(stored)

        mock_jira.assert_not_called()
        mock_email.assert_not_called()

    @patch("app.send_support_ticket_notification")
    @patch("app.create_jira_issue")
    def test_classification_failure_does_not_create_ticket_or_call_integrations(
        self, mock_jira, mock_email
    ):
        with patch("app.classify_query", return_value={
            "success": False,
            "category": None,
            "confidence": 0,
            "message": "Simulated classification failure",
        }):
            response = self.client.post(
                "/api/ticket",
                json={
                    "title": "Classification failure test",
                    "description": "Test-only ticket description.",
                    "department": "IT",
                },
            )

        self.assertEqual(response.status_code, 503)
        self.assertIn("error", response.get_json())

        mock_jira.assert_not_called()
        mock_email.assert_not_called()


if __name__ == "__main__":
    try:
        unittest.main(verbosity=2)
    finally:
        TEMP_DIR.cleanup()
