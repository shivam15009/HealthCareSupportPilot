
from rag.generator import generate_support_response


class ResolutionAgent:
    """Generate an operational support response grounded in evidence."""

    def run(self, ticket_text, evidence, category=None):
        ticket_text = (ticket_text or "").strip()
        evidence = evidence or []

        if not ticket_text:
            return {
                "success": False,
                "context": "",
                "resolution": "",
                "requires_escalation": True,
                "agent": "Resolution Agent",
                "error": "Ticket description cannot be empty.",
            }

        if not evidence:
            return {
                "success": False,
                "context": "",
                "resolution": (
                    "No relevant knowledge-base evidence was found. "
                    "Human support review is required."
                ),
                "requires_escalation": True,
                "agent": "Resolution Agent",
                "error": "No evidence available.",
            }

        try:
            result = generate_support_response(
                ticket_text=ticket_text,
                evidence=evidence,
                category=category,
            )

            if not isinstance(result, dict):
                raise ValueError(
                    "The response generator must return a dictionary."
                )

            context = result.get("context", "")
            resolution = str(result.get("resolution", "")).strip()

            insufficient_evidence = (
                "No sufficiently relevant knowledge-base evidence"
                in resolution
            )

            success = bool(resolution) and not insufficient_evidence

            return {
                "success": success,
                "context": context,
                "resolution": resolution,
                "requires_escalation": not success,
                "agent": "Resolution Agent",
                "message": (
                    "Operational response generated from retrieved evidence."
                    if success
                    else "Evidence was insufficient to generate a response."
                ),
            }

        except Exception:
            return {
                "success": False,
                "context": "",
                "resolution": (
                    "Resolution generation failed. "
                    "Please refer this ticket for human support review."
                ),
                "requires_escalation": True,
                "agent": "Resolution Agent",
                "error": "The generator could not process the evidence.",
            }


if __name__ == "__main__":
    from rag.pipeline import run_pipeline

    ticket_text = (
        "Hospital staff cannot connect to the internal network."
    )
    category = "Hospital Network"

    retrieval = run_pipeline(
        ticket_text=ticket_text,
        category=category,
        top_k=3,
        generate_resolution=False,
    )

    agent = ResolutionAgent()
    result = agent.run(
        ticket_text=ticket_text,
        evidence=retrieval.get("evidence", []),
        category=category,
    )

    print("\n--- Resolution Agent Result ---")
    print("Success:", result["success"])
    print("Requires escalation:", result["requires_escalation"])
    print("Agent:", result["agent"])
    print("\nResolution:\n")
    print(result["resolution"])
