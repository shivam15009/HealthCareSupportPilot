
class ValidationAgent:
    """Validate operational resolutions before taking action."""

    def __init__(
        self,
        minimum_confidence=60.0,
        minimum_relevance=0.35,
    ):
        self.minimum_confidence = minimum_confidence
        self.minimum_relevance = minimum_relevance

    def run(
        self,
        diagnosis,
        retrieval,
        resolution,
        existing_escalation=False,
    ):
        reasons = []

        diagnosis = diagnosis or {}
        retrieval = retrieval or {}
        resolution = resolution or {}

        # 1. Check the diagnosis.
        try:
            confidence = float(
                diagnosis.get("confidence", 0.0)
            )
        except (TypeError, ValueError):
            confidence = 0.0

        category = diagnosis.get("category", "Unknown")

        if not diagnosis.get("success", False):
            reasons.append("diagnosis_failed")

        if not category or category == "Unknown":
            reasons.append("unknown_category")

        if confidence < self.minimum_confidence:
            reasons.append("low_classification_confidence")

        # 2. Check the retrieved evidence.
        evidence = retrieval.get("evidence", [])

        if not retrieval.get("success", False) or not evidence:
            reasons.append("no_knowledge_evidence")
        else:
            try:
                best_score = max(
                    float(item.get("score", 0.0))
                    for item in evidence
                )
            except (TypeError, ValueError):
                best_score = 0.0

            if best_score < self.minimum_relevance:
                reasons.append("low_knowledge_relevance")

        # 3. Check the generated response.
        response_text = str(
            resolution.get("resolution", "")
        ).strip()

        if not resolution.get("success", False):
            reasons.append("resolution_generation_failed")

        if not response_text:
            reasons.append("empty_resolution")
        elif (
            "No sufficiently relevant knowledge-base evidence"
            in response_text
        ):
            reasons.append("insufficient_resolution_evidence")

        # 4. Preserve existing human-review requirements.
        if existing_escalation:
            reasons.append("existing_human_review_requirement")

        # 5. Determine the workflow decision.
        reasons = sorted(set(reasons))
        approved = len(reasons) == 0

        return {
            "success": True,
            "approved": approved,
            "requires_escalation": not approved,
            "category": category,
            "confidence": confidence,
            "evidence_count": len(evidence),
            "reasons": reasons,
            "agent": "Validation Agent",
            "message": (
                "Validation checks passed."
                if approved
                else "Human review is required."
            ),
        }


if __name__ == "__main__":
    agent = ValidationAgent()

    # Deliberately low confidence to test escalation.
    result = agent.run(
        diagnosis={
            "success": True,
            "category": "Hospital Network",
            "confidence": 36.05,
        },
        retrieval={
            "success": True,
            "evidence": [
                {"score": 0.4361},
                {"score": 0.4215},
                {"score": 0.4140},
            ],
        },
        resolution={
            "success": True,
            "resolution": (
                "AI Operational Resolution\n"
                "Recommended Troubleshooting Steps\n"
                "1. Check local network connectivity."
            ),
        },
    )

    print("\n--- Validation Agent Result ---")
    print("Approved:", result["approved"])
    print("Requires escalation:", result["requires_escalation"])
    print("Reasons:", result["reasons"])
    print("Message:", result["message"])
