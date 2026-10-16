
from classifier import classify_query


class DiagnosisAgent:
    """Classify an operational support ticket."""

    def run(self, ticket_text):
        ticket_text = (ticket_text or "").strip()

        if not ticket_text:
            return {
                "success": False,
                "category": "Unknown",
                "confidence": 0.0,
                "agent": "Diagnosis Agent",
                "error": "Ticket description cannot be empty.",
            }

        try:
            result = classify_query(ticket_text)

            if not isinstance(result, dict):
                raise ValueError(
                    "Classifier must return a dictionary."
                )

            category = result.get("category", "Unknown")
            confidence = float(result.get("confidence", 0.0))

            if not 0.0 <= confidence <= 100.0:
                raise ValueError(
                    "Confidence must be between 0 and 100."
                )

            if not category or category == "Unknown":
                return {
                    "success": False,
                    "category": "Unknown",
                    "confidence": confidence,
                    "agent": "Diagnosis Agent",
                    "error": "The ticket category could not be identified.",
                }

            return {
                "success": True,
                "category": category,
                "confidence": round(confidence, 2),
                "agent": "Diagnosis Agent",
                "message": "Operational category identified.",
            }

        except Exception:
            return {
                "success": False,
                "category": "Unknown",
                "confidence": 0.0,
                "agent": "Diagnosis Agent",
                "error": "The classifier could not process this ticket.",
            }


if __name__ == "__main__":
    agent = DiagnosisAgent()

    result = agent.run(
        "Hospital staff cannot connect to the internal network."
    )

    print("\n--- Diagnosis Agent Result ---")
    print("Success:", result["success"])
    print("Category:", result["category"])
    print("Confidence:", result["confidence"], "%")
    print("Agent:", result["agent"])
