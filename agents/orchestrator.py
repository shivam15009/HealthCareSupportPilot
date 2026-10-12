
from agents.diagnosis_agent import DiagnosisAgent
from agents.retrieval_agent import RetrievalAgent
from agents.resolution_agent import ResolutionAgent
from agents.validation_agent import ValidationAgent
from agents.action_agent import ActionAgent


class MultiAgentOrchestrator:

    def __init__(self):
        self.diagnosis_agent = DiagnosisAgent()
        self.retrieval_agent = RetrievalAgent()
        self.resolution_agent = ResolutionAgent()
        self.validation_agent = ValidationAgent()
        self.action_agent = ActionAgent()

    def run(self, ticket_text):

        if not ticket_text or not ticket_text.strip():
            return self._safe_escalation("empty_ticket")

        # 1. Diagnose
        diagnosis = self.diagnosis_agent.run(ticket_text)

        if not diagnosis.get("success", False):
            return self._safe_escalation("diagnosis_failed")

        category = diagnosis.get("category")
        confidence = diagnosis.get("confidence", 0)

        # 2. Retrieve evidence
        retrieval = self.retrieval_agent.run(
            ticket_text=ticket_text,
            category=category,
            top_k=3
        )

        evidence = retrieval.get("evidence", [])

        
        # 3. Generate a resolution when knowledge evidence exists.
        # Low confidence will still trigger human review in validation.
        if retrieval.get("success", False) and evidence:
            resolution = self.resolution_agent.run(
                ticket_text=ticket_text,
                evidence=evidence,
                category=category
            )
        else:
            resolution = {
                "success": False,
                "resolution": "",
                "requires_escalation": True,
                "message": "Resolution generation skipped because evidence is unavailable."
            }

        # 4. Validate the complete workflow.
        validation = self.validation_agent.run(
            diagnosis=diagnosis,
            retrieval=retrieval,
            resolution=resolution,
            existing_escalation=(
                not retrieval.get("success", False)
                or not evidence
                or confidence < 60
            )
        )


        # 5. Choose the action
        action = self.action_agent.run(validation)

        return {
            "success": True,
            "diagnosis": diagnosis,
            "retrieval": retrieval,
            "resolution": resolution,
            "validation": validation,
            "action_result": action,
            "action": action.get("action", "ESCALATE"),
            "status": action.get("status", "ESCALATE"),
            "ai_resolved": False
        }

    @staticmethod
    def _safe_escalation(reason):
        return {
            "success": False,
            "action": "ESCALATE",
            "status": "ESCALATE",
            "ai_resolved": False,
            "reason": reason,
            "message": "Human support review is required."
        }


if __name__ == "__main__":

    orchestrator = MultiAgentOrchestrator()

    ticket = "Hospital staff cannot connect to the internal network."
    result = orchestrator.run(ticket)

    print("\n===== MULTI-AGENT WORKFLOW =====")

    if result.get("diagnosis"):
        print("Diagnosis:", result["diagnosis"].get("category"))
        print("Confidence:", result["diagnosis"].get("confidence"), "%")

    if result.get("retrieval"):
        print(
            "Evidence found:",
            len(result["retrieval"].get("evidence", []))
        )

    if result.get("validation"):
        print("Approved:", result["validation"].get("approved"))
        print("Validation reasons:", result["validation"].get("reasons"))

    print("Final action:", result.get("action"))
    print("AI resolved:", result.get("ai_resolved"))
    print("===============================")