import unittest

from agents.validation_agent import ValidationAgent


class TestValidationAgent(unittest.TestCase):
    def setUp(self):
        self.agent = ValidationAgent(minimum_confidence=70.0)

    def make_inputs(
        self,
        diagnosis_confidence=80.0,
        retrieval_score=0.8,
        step_count=6,
        retrieval_success=True,
        resolution_success=True,
    ):
        diagnosis = {
            "success": True,
            "category": "Hospital Network",
            "confidence": diagnosis_confidence,
        }

        evidence = [{
            "title": "Network connectivity issue",
            "score": retrieval_score,
        }]

        retrieval = {
            "success": retrieval_success,
            "evidence": evidence,
            "requires_escalation": not retrieval_success,
        }

        steps = [
            f"Troubleshooting step {number}"
            for number in range(1, step_count + 1)
        ]

        resolution = {
            "success": resolution_success,
            "resolution": (
                "Recommended Troubleshooting Steps\n"
                + "\n".join(
                    f"{number}. {step}"
                    for number, step in enumerate(steps, start=1)
                )
            ),
            "requires_escalation": not resolution_success,
        }

        return diagnosis, retrieval, resolution

    def test_composite_confidence_uses_exact_formula(self):
        diagnosis, retrieval, resolution = self.make_inputs(
            diagnosis_confidence=80.0,
            retrieval_score=0.8,
            step_count=3,
        )

        result = self.agent.run(diagnosis, retrieval, resolution)

        # 80 * .40 + 80 * .40 + (3 / 6 * 100) * .20 = 76
        self.assertEqual(result["final_confidence"], 74.0)
        self.assertEqual(result["confidence"], 74.0)
        self.assertTrue(result["approved"])
        self.assertFalse(result["requires_escalation"])

    def test_low_ai_confidence_requires_escalation(self):
        diagnosis, retrieval, resolution = self.make_inputs(
            diagnosis_confidence=50.0,
            retrieval_score=0.5,
            step_count=3,
        )

        result = self.agent.run(diagnosis, retrieval, resolution)

        # 50 * .40 + 50 * .40 + 50 * .20 = 50
        self.assertEqual(result["final_confidence"], 50.0)
        self.assertFalse(result["approved"])
        self.assertTrue(result["requires_escalation"])

    def test_classification_confidence_alone_does_not_override_ai_score(self):
        diagnosis, retrieval, resolution = self.make_inputs(
            diagnosis_confidence=100.0,
            retrieval_score=0.0,
            step_count=0,
        )

        # A valid diagnosis can still have a low composite AI confidence.
        # With no useful evidence, mandatory escalation also applies.
        result = self.agent.run(diagnosis, retrieval, resolution)

        self.assertEqual(result["final_confidence"], 40.0)
        self.assertFalse(result["approved"])
        self.assertTrue(result["requires_escalation"])

    def test_missing_evidence_requires_escalation(self):
        diagnosis, retrieval, resolution = self.make_inputs()
        retrieval["success"] = False
        retrieval["evidence"] = []
        retrieval["requires_escalation"] = True

        result = self.agent.run(diagnosis, retrieval, resolution)

        self.assertFalse(result["approved"])
        self.assertTrue(result["requires_escalation"])
        self.assertTrue(
            any("No knowledge-base evidence" in reason
                for reason in result["reasons"])
        )

    def test_failed_resolution_requires_escalation(self):
        diagnosis, retrieval, resolution = self.make_inputs()
        resolution["success"] = False
        resolution["resolution"] = ""
        resolution["requires_escalation"] = True

        result = self.agent.run(diagnosis, retrieval, resolution)

        self.assertFalse(result["approved"])
        self.assertTrue(result["requires_escalation"])

    def test_existing_escalation_is_preserved(self):
        diagnosis, retrieval, resolution = self.make_inputs(
            diagnosis_confidence=100.0,
            retrieval_score=1.0,
            step_count=6,
        )

        result = self.agent.run(
            diagnosis,
            retrieval,
            resolution,
            existing_escalation=True,
        )

        self.assertEqual(result["final_confidence"], 100.0)
        self.assertFalse(result["approved"])
        self.assertTrue(result["requires_escalation"])


if __name__ == "__main__":
    unittest.main()
