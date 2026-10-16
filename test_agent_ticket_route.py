import json
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
    prefix="healthcare_agent_route_test_",
    ignore_cleanup_errors=True,
)
database.DB_PATH = Path(TEMP_DIR.name) / "test_healthcare_support.db"

import app as flask_app


def approved_workflow():
    return {
        "success": True,
        "workflow_completed": True,
        "diagnosis": {
            "success": True,
            "category": "Access",
            "confidence": 90.0,
        },
        "retrieval": {
            "success": True,
            "evidence": [{"score": 0.95, "content": "Test evidence"}],
        },
        "resolution": {
            "success": True,
            "text": "Recommended troubleshooting guidance.",
        },
        "validation": {
            "success": True,
            "approved": True,
            "requires_escalation": False,
            "final_confidence": 90.0,
        },
        "action_result": {
            "success": True,
            "action": "AUTO_RESOLVE",
            "requires_escalation": False,
            "integration_eligible": True,
        },
    }


class AgentTicketRouteTest(unittest.TestCase):
    def setUp(self):
        database.init_db()
        self.client = flask_app.app.test_client()

        with self.client.session_transaction() as session:
            session["user_id"] = 123
            session["requester_name"] = "Agent Route Test User"

        with database.get_connection() as conn:
            conn.execute("DELETE FROM support_tickets")
            conn.commit()

        self.ticket_id = database.save_ticket({
            "requester_name": "Agent Route Test User",
            "department": "IT",
            "title": "Agent route test ticket",
            "description": "Test-only network connectivity issue affecting one workstation.",
            "category": "Access",
            "severity": "High",
            "priority": "P3",
            "confidence": 90.0,
            "status": "OPEN",
            "user_id": 123,
            "escalation_reasons": "[]",
        })

    def post_workflow(self, ticket_id=None):
        return self.client.post(
            "/api/agents/run-ticket",
            json={"ticket_id": ticket_id or self.ticket_id},
        )

    def test_unauthenticated_request_is_rejected(self):
        with self.client.session_transaction() as session:
            session.clear()

        response = self.post_workflow()

        self.assertEqual(response.status_code, 401)

    def test_ticket_owned_by_another_user_is_not_accessible(self):
        with self.client.session_transaction() as session:
            session["user_id"] = 456

        with patch("app.MultiAgentOrchestrator.run") as mock_run:
            response = self.post_workflow()

        self.assertEqual(response.status_code, 404)
        mock_run.assert_not_called()

    def test_approved_workflow_marks_ticket_auto_resolved(self):
        with (
            patch(
                "app.MultiAgentOrchestrator.run",
                return_value=approved_workflow(),
            ),
            patch("app.create_jira_issue") as mock_jira,
        ):
            mock_jira.return_value = {
                "key": "HEAL-APPROVED-TEST",
                "url": "https://example.invalid/browse/HEAL-APPROVED-TEST",
            }
            response = self.post_workflow()

        self.assertEqual(response.status_code, 200, response.get_json())
        body = response.get_json()
        self.assertEqual(response.status_code, 200, response.get_json())
        body = response.get_json()

        self.assertEqual(body["status"], "AUTO_RESOLVE")
        self.assertTrue(body["ai_resolved"])
        self.assertFalse(body["requires_escalation"])
        self.assertEqual(body["jira_sync_status"], "NOT_CONFIGURED")
        mock_jira.assert_not_called()

        stored = database.get_ticket(self.ticket_id, user_id=123)
        self.assertEqual(stored["status"], "AUTO_RESOLVE")
        self.assertTrue(bool(stored["ai_resolved"]))
    def test_low_classification_confidence_alone_does_not_escalate(self):
        with database.get_connection() as conn:
            conn.execute(
                "UPDATE support_tickets SET confidence = ? WHERE ticket_id = ?",
                (60.0, self.ticket_id),
            )
            conn.commit()

        with (
            patch(
                "app.MultiAgentOrchestrator.run",
                return_value=approved_workflow(),
            ),
            patch("app.create_jira_issue") as mock_jira,
        ):
            response = self.post_workflow()

        self.assertEqual(response.status_code, 200, response.get_json())
        body = response.get_json()

        self.assertEqual(body["resolution_confidence"], 90.0)
        self.assertEqual(body["status"], "AUTO_RESOLVE")
        self.assertTrue(body["ai_resolved"])
        self.assertFalse(body["requires_escalation"])
        self.assertNotIn("low_confidence", body["escalation_reasons"])
        mock_jira.assert_not_called()


    def test_existing_escalation_reason_requires_human_review(self):
        database.update_ticket_escalation_reasons(
            self.ticket_id,
            ["existing_test_escalation"],
        )

        with (
            patch(
                "app.MultiAgentOrchestrator.run",
                return_value=approved_workflow(),
            ),
            patch("app.create_jira_issue") as mock_jira,
        ):
            mock_jira.return_value = {
                "key": "HEAL-TEST",
                "url": "https://example.invalid/browse/HEAL-TEST",
            }
            response = self.post_workflow()

        self.assertEqual(response.status_code, 200, response.get_json())
        body = response.get_json()

        self.assertEqual(body["status"], "ESCALATE")
        self.assertTrue(body["requires_escalation"])
        self.assertFalse(body["ai_resolved"])
        self.assertIn(
            "existing_test_escalation",
            body["escalation_reasons"],
        )
        self.assertEqual(body["jira_sync_status"], "SYNCED")
        mock_jira.assert_called_once()

    def test_existing_jira_issue_is_reused(self):
        database.update_ticket_jira_result(
            self.ticket_id,
            "SYNCED",
            "HEAL-EXISTING",
            "https://example.invalid/browse/HEAL-EXISTING",
        )
        database.update_ticket_escalation_reasons(
            self.ticket_id,
            ["existing_test_escalation"],
        )

        with (
            patch(
                "app.MultiAgentOrchestrator.run",
                return_value=approved_workflow(),
            ),
            patch("app.create_jira_issue") as mock_jira,
        ):
            response = self.post_workflow()

        self.assertEqual(response.status_code, 200, response.get_json())
        body = response.get_json()

        self.assertEqual(body["jira_issue_key"], "HEAL-EXISTING")
        self.assertEqual(
            body["jira_issue_url"],
            "https://example.invalid/browse/HEAL-EXISTING",
        )
        self.assertEqual(body["jira_sync_status"], "SYNCED")
        mock_jira.assert_not_called()

    def test_third_attempt_requires_escalation(self):
        database.increment_agent_attempt_count(self.ticket_id)
        database.increment_agent_attempt_count(self.ticket_id)

        with (
            patch(
                "app.MultiAgentOrchestrator.run",
                return_value=approved_workflow(),
            ),
            patch("app.create_jira_issue") as mock_jira,
        ):
            mock_jira.return_value = {
                "key": "HEAL-REPEAT-TEST",
                "url": "https://example.invalid/browse/HEAL-REPEAT-TEST",
            }
            response = self.post_workflow()

        self.assertEqual(response.status_code, 200, response.get_json())
        body = response.get_json()

        self.assertEqual(body["attempt_count"], 3)
        self.assertEqual(body["status"], "ESCALATE")
        self.assertTrue(body["requires_escalation"])
        self.assertIn("repeated_agent_attempts", body["escalation_reasons"])
        mock_jira.assert_called_once()


if __name__ == "__main__":
    try:
        unittest.main(verbosity=2)
    finally:
        TEMP_DIR.cleanup()
