
from classifier import classify_query


class DiagnosisAgent:
    """Analyze a ticket using the existing classifier."""

    def run(self, ticket_text):
        """
        Return the predicted category and confidence.
        """

        ticket_text = (ticket_text or "").strip()

        if not ticket_text:
            return {
                "success": False,
                "category": "Unknown",
                "confidence": 0.0,
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

            return {
                "success": True,
                "category": category,
                "confidence": round(confidence, 2),
                "agent": "Diagnosis Agent",
                "message": (
                    "Operational category identified."
                ),
            }

        except (ValueError, TypeError, KeyError) as error:
            return {
                "success": False,
                "category": "Unknown",
                "confidence": 0.0,
                "agent": "Diagnosis Agent",
                "error": str(error),
            }

        except Exception:
            return {
                "success": False,
                "category": "Unknown",
                "confidence": 0.0,
                "agent": "Diagnosis Agent",
                "error": (
                    "The classifier could not process this ticket."
                ),
            }


if __name__ == "__main__":
    agent = DiagnosisAgent()

    sample_ticket = (
        "Hospital staff cannot connect to the internal network."
    )

    result = agent.run(sample_ticket)

    print("\n--- Diagnosis Agent Result ---")
    print("Success:", result["success"])
    print("Category:", result["category"])
    print("Confidence:", result["confidence"], "%")
    print("Agent:", result.get("agent", "Diagnosis Agent"))
