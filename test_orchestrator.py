from pprint import pprint
from agents.orchestrator import MultiAgentOrchestrator

orchestrator = MultiAgentOrchestrator()

result = orchestrator.run(
    "Hospital staff cannot connect to the internal network."
)

pprint(result)

print("\n--- Workflow Summary ---")
print("Workflow success:", result.get("success"))
print("Diagnosis:", result.get("diagnosis", {}).get("category"))
print("Confidence:", result.get("diagnosis", {}).get("confidence"))
print("Evidence count:", len(result.get("retrieval", {}).get("evidence", [])))
print("Validation approved:", result.get("validation", {}).get("approved"))
print("Action:", result.get("action"))
print("Status:", result.get("status"))
print("AI resolved:", result.get("ai_resolved"))
print("Requires escalation:", result.get("requires_escalation"))