
class ValidationAgent:
    """
    Validate diagnosis, retrieved knowledge, and proposed resolution.

    Composite confidence:
        Diagnosis:    40%
        Retrieval:    30%
        Completeness: 30%

    Diagnosis confidence: 0-100
    Retrieval relevance: 0-1
    Completeness: 0-1

    The final confidence threshold does not override mandatory
    validation or escalation checks.
    """

    DIAGNOSIS_WEIGHT = 0.40
    RETRIEVAL_WEIGHT = 0.30
    COMPLETENESS_WEIGHT = 0.30
    MAX_RESOLUTION_STEPS = 6

    def __init__(
        self,
        minimum_confidence=70.0,
        minimum_relevance=0.30,
    ):
        self.minimum_confidence = float(minimum_confidence)
        self.minimum_relevance = float(minimum_relevance)

    def run(
        self,
        diagnosis,
        retrieval,
        resolution,
        existing_escalation=False,
    ):
        diagnosis = diagnosis if isinstance(diagnosis, dict) else {}
        retrieval = retrieval if isinstance(retrieval, dict) else {}
        resolution = resolution if isinstance(resolution, dict) else {}

        reasons = []

        # 1. Diagnosis validation
        category = diagnosis.get("category")
        raw_confidence = diagnosis.get("confidence")

        try:
            diagnosis_confidence = float(raw_confidence)
        except (TypeError, ValueError):
            diagnosis_confidence = None

        diagnosis_valid = (
            diagnosis.get("success") is True
            and isinstance(category, str)
            and bool(category.strip())
            and diagnosis_confidence is not None
            and 0 <= diagnosis_confidence <= 100
        )

        if not diagnosis_valid:
            reasons.append("Diagnosis result is missing or invalid.")

        # 2. Retrieval validation
        evidence = retrieval.get("evidence", [])
        if not isinstance(evidence, list):
            evidence = []

        valid_scores = []

        for item in evidence:
            if not isinstance(item, dict):
                continue

            try:
                score = float(item.get("score"))
            except (TypeError, ValueError):
                continue

            if 0 <= score <= 1:
                valid_scores.append(score)

        best_relevance = max(valid_scores, default=0.0)

        retrieval_valid = (
            retrieval.get("success") is True
            and bool(evidence)
            and bool(valid_scores)
        )

        if retrieval.get("success") is not True:
            reasons.append("Knowledge retrieval failed.")

        if not evidence:
            reasons.append("No knowledge-base evidence was retrieved.")
        elif not valid_scores:
            reasons.append(
                "Evidence relevance scores are missing or invalid."
            )

        if valid_scores and best_relevance < self.minimum_relevance:
            reasons.append(
                f"Best evidence relevance is below the "
                f"{self.minimum_relevance:.2f} minimum."
            )

        # 3. Resolution validation
        resolution_text = resolution.get("resolution", "")
        if not isinstance(resolution_text, str):
            resolution_text = ""

        resolution_text = resolution_text.strip()

        resolution_valid = (
            resolution.get("success") is True
            and bool(resolution_text)
        )

        if resolution.get("success") is not True:
            reasons.append("Resolution generation failed.")

        if not resolution_text:
            reasons.append("No resolution text was generated.")
        elif (
            "no sufficiently relevant knowledge-base evidence"
            in resolution_text.lower()
        ):
            resolution_valid = False
            reasons.append(
                "The generated response indicates insufficient "
                "knowledge-base evidence."
            )


        # 4. Completeness: count actual troubleshooting steps.
        # Do not count numbered knowledge-source entries.
        raw_steps = resolution.get("steps", [])

        if isinstance(raw_steps, list):
            steps = [
                step.strip()
                for step in raw_steps
                if isinstance(step, str) and step.strip()
            ]
        else:
            steps = []

        # The current Resolution Agent returns formatted text.
        # Extract only lines under the troubleshooting heading.
        if not steps and resolution_text:
            in_troubleshooting_section = False

            for line in resolution_text.splitlines():
                line = line.strip()
                lower_line = line.lower()

                if lower_line == "recommended troubleshooting steps":
                    in_troubleshooting_section = True
                    continue

                if lower_line in {
                    "knowledge sources",
                    "issue summary",
                    "operational area",
                }:
                    in_troubleshooting_section = False

                if in_troubleshooting_section:
                    if (
                        len(line) > 2
                        and line[0].isdigit()
                        and line[1] == "."
                    ):
                        step = line[2:].strip()
                        if step:
                            steps.append(step)

        # Six valid troubleshooting steps represent 100% completeness.
        steps = steps[:self.MAX_RESOLUTION_STEPS]
        completeness = min(
            len(steps) / self.MAX_RESOLUTION_STEPS,
            1.0,
        )


        # 5. Composite confidence
        diagnosis_score = (
            diagnosis_confidence
            if diagnosis_confidence is not None
            and 0 <= diagnosis_confidence <= 100
            else 0.0
        )

        retrieval_score = best_relevance * 100.0

        final_confidence = (
            diagnosis_score * self.DIAGNOSIS_WEIGHT
            + retrieval_score * self.RETRIEVAL_WEIGHT
            + completeness * 100.0 * self.COMPLETENESS_WEIGHT
        )

        final_confidence = round(final_confidence, 2)
        import logging

        logging.warning(
            "Validation confidence: diagnosis=%.2f, retrieval=%.2f, "
            "completeness=%.2f, steps=%d, final=%.2f, reasons=%s",
            diagnosis_score,
            retrieval_score,
            completeness * 100.0,
            len(steps),
            final_confidence,
            reasons,
        )

        if final_confidence < self.minimum_confidence:
            reasons.append(
                f"Final confidence is below the "
                f"{self.minimum_confidence:.1f}% minimum."
            )

        # 6. Respect all escalation requests
        if existing_escalation:
            reasons.append(
                "An earlier workflow stage requires human escalation."
            )

        if retrieval.get("requires_escalation") is True:
            reasons.append(
                "The retrieval agent requires human escalation."
            )

        if resolution.get("requires_escalation") is True:
            reasons.append(
                "The resolution agent requires human escalation."
            )

        # Remove duplicate reasons without changing their order.
        reasons = list(dict.fromkeys(reasons))

        approved = (
            diagnosis_valid
            and retrieval_valid
            and best_relevance >= self.minimum_relevance
            and resolution_valid
            and final_confidence >= self.minimum_confidence
            and existing_escalation is not True
            and retrieval.get("requires_escalation") is not True
            and resolution.get("requires_escalation") is not True
            and not reasons
        )
        logging.warning(
            "FINAL VALIDATION DETAILS: approved=%r "
            "confidence=%.2f minimum_confidence=%.2f "
            "best_relevance=%.4f minimum_relevance=%.2f "
            "diagnosis_valid=%r retrieval_valid=%r "
            "resolution_valid=%r completeness=%.2f "
            "step_count=%d existing_escalation=%r reasons=%r",
            approved,
            final_confidence,
            self.minimum_confidence,
            best_relevance,
            self.minimum_relevance,
            diagnosis_valid,
            retrieval_valid,
            resolution_valid,
            completeness * 100.0,
            len(steps),
            existing_escalation,
            reasons,
        )

        return {
            "success": True,
            "approved": approved,
            "requires_escalation": not approved,
            "category": category,
            "confidence": final_confidence,
            "final_confidence": final_confidence,
            "diagnosis_confidence": round(diagnosis_score, 2),
            "retrieval_relevance": round(retrieval_score, 2),
            "completeness": round(completeness * 100, 2),
            "resolution_step_count": len(steps),
            "evidence_count": len(evidence),
            "best_relevance": round(best_relevance, 4),
            "weights": {
                "diagnosis": self.DIAGNOSIS_WEIGHT,
                "retrieval": self.RETRIEVAL_WEIGHT,
                "completeness": self.COMPLETENESS_WEIGHT,
            },
            "reasons": reasons,
            "agent": "Validation Agent",
            "message": (
                "Validation passed. The proposed resolution is ready "
                "for the next workflow action, subject to action-agent "
                "safety checks."
                if approved
                else
                "Validation failed. Human review is required before "
                "the proposed resolution can proceed."
            ),
        }
