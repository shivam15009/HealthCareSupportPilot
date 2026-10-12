
class ActionAgent:
    """Choose the next safe workflow action."""

    def run(self, validation):
        validation = validation or {}

        if not validation.get("success", False):
            return {
                "success": False,
                "action": "ESCALATE",
                "status": "ESCALATE",
                "ai_resolved": False,
                "reason": "validation_failed",
                "agent": "Action Agent",
            }

        if validation.get("requires_escalation", True):
            reasons = validation.get("reasons", [])

            return {
                "success": True,
                "action": "ESCALATE",
                "status": "ESCALATE",
                "ai_resolved": False,
                "reason": reasons,
                "agent": "Action Agent",
                "message": (
                    "Ticket requires review by a human support agent."
                ),
            }

        return {
            "success": True,
            "action": "AI_RESOLUTION_READY",
            "status": "AI_RESOLUTION_READY",
            "ai_resolved": False,
            "reason": [],
            "agent": "Action Agent",
            "message": (
                "Resolution passed the configured checks. "
                "The ticket is ready for the next workflow step; "
                "the issue is not confirmed as fixed."
            ),
        }


if __name__ == "__main__":
    agent = ActionAgent()

    test_validation = {
        "success": True,
        "approved": False,
        "requires_escalation": True,
        "reasons": ["low_classification_confidence"],
    }

    result = agent.run(test_validation)

    print("\n--- Action Agent Result ---")
    print("Success:", result["success"])
    print("Action:", result["action"])
    print("Status:", result["status"])
    print("AI resolved:", result["ai_resolved"])
    print("Reason:", result["reason"])
    print("Message:", result["message"])
