
class ActionAgent:
    """Choose the next safe operational workflow action."""

    def run(self, validation):
        validation = validation if isinstance(validation, dict) else {}

        # Default: integrations must not run.
        if not validation.get("success", False):
            return self._escalate(
                reason="validation_failed",
                message="Validation failed. Human support review is required.",
                success=False,
            )

        if validation.get("approved") is not True:
            return self._escalate(
                reason=validation.get("reasons")
                or ["validation_not_approved"],
                message=(
                    "The resolution was not approved. "
                    "Human support review is required."
                ),
            )

        if validation.get("requires_escalation", True):
            return self._escalate(
                reason=validation.get("reasons")
                or ["human_escalation_required"],
                message="Ticket requires review by a human support agent.",
            )

        # Validation passed. The issue is not confirmed fixed.
        return {
            "success": True,
            "action": "AUTO_RESOLVE",
            "status": "AUTO_RESOLVE",
            "ai_resolved": True,
            "requires_escalation": False,
            "integration_eligible": True,
            "reason": [],
            "agent": "Action Agent",
            "message": (
                "Resolution passed validation. The ticket is marked AI-resolved."
            ),
        }

    @staticmethod
    def _escalate(reason, message, success=True):
        """Return a consistent result that blocks integrations."""
        return {
            "success": success,
            "action": "ESCALATE",
            "status": "ESCALATE",
            "ai_resolved": False,
            "requires_escalation": True,
            "integration_eligible": False,
            "reason": reason,
            "agent": "Action Agent",
            "message": message,
        }


if __name__ == "__main__":
    agent = ActionAgent()

    test_cases = [
        {
            "name": "Approved resolution",
            "validation": {
                "success": True,
                "approved": True,
                "requires_escalation": False,
                "reasons": [],
            },
        },
        {
            "name": "Validation not approved",
            "validation": {
                "success": True,
                "approved": False,
                "requires_escalation": True,
                "reasons": ["validation_not_approved"],
            },
        },
        {
            "name": "Approval missing",
            "validation": {
                "success": True,
                "requires_escalation": False,
                "reasons": [],
            },
        },
        {
            "name": "Validation failed",
            "validation": {
                "success": False,
                "approved": False,
                "requires_escalation": True,
                "reasons": ["validation_failed"],
            },
        },
    ]

    for test_case in test_cases:
        result = agent.run(test_case["validation"])

        print(f"\n--- {test_case['name']} ---")
        print("Success:", result["success"])
        print("Action:", result["action"])
        print("Status:", result["status"])
        print("AI resolved:", result["ai_resolved"])
        print("Integration eligible:", result["integration_eligible"])
        print("Requires escalation:", result["requires_escalation"])
        print("Reason:", result["reason"])
        print("Message:", result["message"])
