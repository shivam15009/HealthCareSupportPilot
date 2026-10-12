
from rag.generator import generate_support_response


class ResolutionAgent:
    """Generate a response grounded in retrieved evidence."""

    def run(self, ticket_text, evidence, category=None):
        ticket_text = (ticket_text or "").strip()
        evidence = evidence or []

        if not ticket_text:
            return {
                "success": False,
                "context": "",
                "resolution": "",
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
                "error": "No evidence available.",
            }

        try:
            result = generate_support_response(
                ticket_text=ticket_text,
                evidence=evidence,
                category=category,
            )

            context = result.get("context", "")
            resolution = result.get("resolution", "")

            # The generator may return a message explaining that
            # evidence is insufficient instead of actual steps.
            insufficient_evidence = (
                "No sufficiently relevant knowledge-base evidence"
                in resolution
            )

            success = bool(
                resolution.strip()
                and not insufficient_evidence
            )

            return {
                "success": success,
                "context": context,
                "resolution": resolution,
                "agent": "Resolution Agent",
                "requires_escalation": not success,
            }

        except Exception:
            return {
                "success": False,
                "context": "",
                "resolution": (
                    "Resolution generation failed. "
                    "Please refer this ticket for human review."
                ),
                "agent": "Resolution Agent",
                "requires_escalation": True,
                "error": "The generator could not process the evidence.",
            }


if __name__ == "__main__":
    from rag.pipeline import run_pipeline

    ticket_text = (
        "Hospital staff cannot connect to the internal network."
    )
    category = "Hospital Network"

    # Retrieve evidence without generating a resolution yet.
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
    print("Requires escalation:", result.get("requires_escalation"))
    print("Agent:", result["agent"])
    print("\nResolution:\n")
    print(result["resolution"])
