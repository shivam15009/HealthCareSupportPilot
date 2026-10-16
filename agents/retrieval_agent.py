
from rag.pipeline import run_pipeline


class RetrievalAgent:
    """Retrieve relevant operational support knowledge."""

    def run(self, ticket_text, category=None, top_k=3):
        ticket_text = (ticket_text or "").strip()

        if not ticket_text:
            return {
                "success": False,
                "evidence": [],
                "context": "",
                "resolution": "",
                "requires_escalation": True,
                "agent": "Retrieval Agent",
                "error": "Ticket description cannot be empty.",
            }

        try:
            result = run_pipeline(
                ticket_text=ticket_text,
                category=category,
                top_k=top_k,
                generate_resolution=False,
            )

            evidence = result.get("evidence", []) or []
            context = result.get("context", "")

            return {
                "success": bool(evidence),
                "evidence": evidence,
                "context": context,
                "resolution": "",
                "requires_escalation": not bool(evidence),
                "agent": "Retrieval Agent",
                "message": (
                    f"Retrieved {len(evidence)} knowledge records."
                    if evidence
                    else "No relevant knowledge evidence found."
                ),
            }

        except Exception:
            return {
                "success": False,
                "evidence": [],
                "context": "",
                "resolution": "",
                "requires_escalation": True,
                "agent": "Retrieval Agent",
                "error": (
                    "Knowledge retrieval failed. "
                    "Human support review may be required."
                ),
            }


if __name__ == "__main__":
    agent = RetrievalAgent()

    result = agent.run(
        ticket_text=(
            "Hospital staff cannot connect to the internal network."
        ),
        category="Hospital Network",
        top_k=3,
    )

    print("\n--- Retrieval Agent Result ---")
    print("Success:", result["success"])
    print("Evidence found:", len(result["evidence"]))
    print("Requires escalation:", result["requires_escalation"])
    print("Agent:", result["agent"])
    print("Message:", result.get("message", result.get("error", "")))

    for index, item in enumerate(result["evidence"], start=1):
        print(f"\nEvidence {index}:")
        print("Title:", item.get("title"))
        print("Category:", item.get("category"))
        print("Relevance:", item.get("score"))
