
"""
Healthcare Support Pilot
Milestone 3 - Multi-Agent Orchestrator

Workflow:
Diagnosis -> Retrieval -> Resolution -> Validation -> Action

Safety rules:
- Validation must explicitly approve the proposed resolution.
- The Action Agent must explicitly permit integrations.
- Failed or unapproved workflows cannot trigger integrations.
- AI-generated guidance does not mean the issue is resolved.
"""

from agents.diagnosis_agent import DiagnosisAgent
from agents.retrieval_agent import RetrievalAgent
from agents.resolution_agent import ResolutionAgent
from agents.validation_agent import ValidationAgent
from agents.action_agent import ActionAgent

from database import (
    record_ticket_validation_start,
    complete_ticket_validation,
    cancel_pending_ticket_validation,
)

class MultiAgentOrchestrator:
    """Coordinate agents and determine integration eligibility."""

    MINIMUM_CONFIDENCE = 70.0
    TOP_K = 3

    def __init__(self):
        self.diagnosis_agent = DiagnosisAgent()
        self.retrieval_agent = RetrievalAgent()
        self.resolution_agent = ResolutionAgent()

        self.validation_agent = ValidationAgent(
            minimum_confidence=self.MINIMUM_CONFIDENCE,
            minimum_relevance=0.30,
        )

        self.action_agent = ActionAgent()

    def run(self, ticket_text, ticket_id=None):
        """Execute the workflow and return a consistent result."""

        original_ticket = (
            ticket_text.strip()
            if isinstance(ticket_text, str)
            else ""
        )

        validation_event_id = None

        if ticket_id is not None and original_ticket:
            validation_event_id = record_ticket_validation_start(
                ticket_id
            )

        def close_pending_validation():
            if validation_event_id is not None:
                cancel_pending_ticket_validation(
                    validation_event_id
                )

        if not original_ticket:
            return self._safe_failure(
                ticket_text=original_ticket,
                reason="Ticket description cannot be empty.",
                error_code="empty_ticket",
            )




        # 1. Diagnosis
        diagnosis = self._run_agent(
            self.diagnosis_agent,
            ticket_text=original_ticket,
        )

        if diagnosis.get("success") is not True:
            close_pending_validation()
            return self._safe_failure(
                ticket_text=original_ticket,
                reason="Diagnosis failed.",
                error_code="diagnosis_failed",
                diagnosis=diagnosis,
            )

        category = diagnosis.get("category")
        confidence = self._to_float(diagnosis.get("confidence"))

        if not isinstance(category, str) or not category.strip():
            close_pending_validation()
            return self._safe_failure(
                ticket_text=original_ticket,
                reason="Diagnosis category is missing or invalid.",
                error_code="invalid_category",
                diagnosis=diagnosis,
            )

        if confidence is None or not 0 <= confidence <= 100:
            close_pending_validation()
            return self._safe_failure(
                ticket_text=original_ticket,
                reason="Diagnosis confidence is invalid.",
                error_code="invalid_confidence",
                diagnosis=diagnosis,
            )

        # 2. Retrieval
        retrieval = self._run_agent(
            self.retrieval_agent,
            ticket_text=original_ticket,
            category=category,
            top_k=self.TOP_K,
        )

        evidence = retrieval.get("evidence", [])
        if not isinstance(evidence, list):
            evidence = []

        # 3. Resolution
        if retrieval.get("success") is True and evidence:
            resolution = self._run_agent(
                self.resolution_agent,
                ticket_text=original_ticket,
                evidence=evidence,
                category=category,
            )
        else:
            resolution = {
                "success": False,
                "resolution": "",
                "requires_escalation": True,
                "agent": "Resolution Agent",
                "error": (
                    "Resolution could not be generated because "
                    "retrieval failed or returned no evidence."
                ),
            }

        # 4. Check whether any stage already requires human review.
        existing_escalation = (
            retrieval.get("success") is not True
            or not evidence
            or retrieval.get("requires_escalation", False) is True
            or resolution.get("success") is not True
            or resolution.get("requires_escalation", False) is True
        )



        # 5. Validation
        try:
            validation = self._run_agent(
                self.validation_agent,
                diagnosis=diagnosis,
                retrieval=retrieval,
                resolution=resolution,
                existing_escalation=existing_escalation,
            )

            if validation_event_id is not None:
                validation_approved = (
                    validation.get("success") is True
                    and validation.get("approved") is True
                    and validation.get("requires_escalation") is False
                )
                complete_ticket_validation(
                    validation_event_id,
                    validation_approved,
                )

        except Exception:
            if validation_event_id is not None:
                cancel_pending_ticket_validation(
                    validation_event_id
                )
            raise



        # Fail closed unless validation explicitly approves.
        validation_passed = (
            validation.get("success") is True
            and validation.get("approved") is True
            and validation.get("requires_escalation", True) is False
            and not existing_escalation
        )

        if not validation_passed:
            validation["approved"] = False
            validation["requires_escalation"] = True

        # 6. Action
        action_result = self._run_agent(
            self.action_agent,
            validation=validation,
        )

        # 7. Integrations require approval from BOTH gates.
        integration_eligible = (
            validation_passed
            and action_result.get("success") is True
            and action_result.get("action") == "AUTO_RESOLVE"
            and action_result.get("requires_escalation", True) is False
            and action_result.get("integration_eligible") is True
        )

        if integration_eligible:
            action = "AUTO_RESOLVE"
            status = "AUTO_RESOLVE"
            message = (
                "The resolution passed validation and the ticket is marked AI-resolved."
            )
            requires_escalation = False
        else:
            action = "ESCALATE"
            status = "HUMAN_REVIEW_REQUIRED"
            message = (
                "The workflow did not qualify for automated integrations."
            )
            requires_escalation = True

        # success means the workflow completed; ai_resolved reflects the approved action.
        return {
            "success": True,
            "workflow_completed": True,
            "ticket_text": original_ticket,
            "diagnosis": diagnosis,
            "retrieval": retrieval,
            "resolution": resolution,
            "validation": validation,
            "action_result": action_result,
            "action": action,
            "status": status,
            "ai_resolved": action == "AUTO_RESOLVE",
            "requires_escalation": requires_escalation,
            "integration_eligible": integration_eligible,
            "message": message,
        }

    @staticmethod
    def _run_agent(agent, **kwargs):
        """Convert unexpected agent exceptions into safe failures."""

        try:
            result = agent.run(**kwargs)

            if not isinstance(result, dict):
                return {
                    "success": False,
                    "requires_escalation": True,
                    "error": "Agent returned an invalid result.",
                }

            return result

        except Exception as exc:
            return {
                "success": False,
                "requires_escalation": True,
                "error": (
                    f"{agent.__class__.__name__} failed: "
                    f"{type(exc).__name__}"
                ),
            }

    @staticmethod
    def _to_float(value):
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _safe_failure(
        ticket_text,
        reason,
        error_code,
        diagnosis=None,
    ):
        """Return a safe result when an early stage fails."""

        return {
            "success": False,
            "workflow_completed": False,
            "ticket_text": ticket_text,
            "diagnosis": diagnosis or {
                "success": False,
                "error": reason,
            },
            "retrieval": {
                "success": False,
                "evidence": [],
                "context": "",
                "requires_escalation": True,
                "error": reason,
            },
            "resolution": {
                "success": False,
                "resolution": "",
                "requires_escalation": True,
                "error": reason,
            },
            "validation": {
                "success": False,
                "approved": False,
                "requires_escalation": True,
                "reasons": [reason],
            },
            "action_result": {
                "success": False,
                "action": "ESCALATE",
                "requires_escalation": True,
                "integration_eligible": False,
                "message": "Workflow failed before approval.",
            },
            "action": "ESCALATE",
            "status": "HUMAN_REVIEW_REQUIRED",
            "ai_resolved": False,
            "requires_escalation": True,
            "integration_eligible": False,
            "error_code": error_code,
            "message": reason,
        }


if __name__ == "__main__":
    orchestrator = MultiAgentOrchestrator()

    sample_ticket = (
        "The hospital network workstation cannot connect "
        "to the internal application."
    )

    result = orchestrator.run(sample_ticket)

    print("\n--- Multi-Agent Workflow Result ---")
    print("Workflow completed:", result.get("workflow_completed"))
    print("Execution successful:", result.get("success"))
    print("Action:", result.get("action"))
    print("Status:", result.get("status"))
    print("AI resolved:", result.get("ai_resolved"))
    print("Integration eligible:", result.get("integration_eligible"))
    print("Message:", result.get("message"))

    print("\n--- Validation Details ---")
    print("Validation result:", result.get("validation"))
    print("Diagnosis result:", result.get("diagnosis"))
    print("Retrieval result:", result.get("retrieval"))
    print("Resolution result:", result.get("resolution"))
    print("Action result:", result.get("action_result"))
