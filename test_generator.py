
import unittest

from rag.generator import (
    MIN_RELEVANCE,
    _valid_evidence,
    extract_steps,
    generate_resolution,
    generate_support_response,
)


class TestGenerator(unittest.TestCase):

    def test_low_relevance_evidence_is_filtered(self):
        evidence = [
            {
                "title": "Unrelated printing issue",
                "score": 0.20,
                "resolution": "Restart the printer service.",
            }
        ]

        self.assertEqual(_valid_evidence(evidence), [])

        result = generate_resolution(
            ticket_text="Pharmacy service is unavailable",
            evidence=evidence,
            category="Pharmacy",
        )

        self.assertIn(
            "No sufficiently relevant knowledge-base evidence",
            result,
        )
        self.assertNotIn("Restart the printer service", result)

    def test_evidence_at_threshold_is_accepted(self):
        evidence = [
            {
                "title": "Service unavailable",
                "category": "Pharmacy",
                "score": MIN_RELEVANCE,
                "resolution": "Check the service status.",
            }
        ]

        self.assertEqual(len(_valid_evidence(evidence)), 1)

    def test_relevant_evidence_generates_resolution(self):
        evidence = [
            {
                "title": "Pharmacy service unavailable",
                "category": "Pharmacy",
                "score": 0.82,
                "resolution": "Check the service status.",
                "source_title": "Support Knowledge Base",
            }
        ]

        result = generate_resolution(
            ticket_text="The pharmacy service is unavailable",
            evidence=evidence,
            category="Pharmacy",
        )

        self.assertIn("Issue Summary", result)
        self.assertIn("Operational Area", result)
        self.assertIn("Recommended Troubleshooting Steps", result)
        self.assertIn("Check the service status.", result)
        self.assertIn("Support Knowledge Base", result)

    def test_low_relevance_steps_do_not_enter_resolution(self):
        evidence = [
            {
                "title": "Relevant service issue",
                "score": 0.80,
                "resolution": "Check the application service.",
            },
            {
                "title": "Unrelated printing issue",
                "score": 0.10,
                "resolution": "Replace the printer cartridge.",
            },
        ]

        result = generate_resolution(
            ticket_text="Application service unavailable",
            evidence=evidence,
            category="Pharmacy",
        )

        self.assertIn("Check the application service.", result)
        self.assertNotIn("Replace the printer cartridge.", result)

    def test_duplicate_steps_are_removed(self):
        evidence = [
            {
                "score": 0.80,
                "resolution": [
                    "Check the service status.",
                    "Restart the application.",
                ],
            },
            {
                "score": 0.70,
                "resolution": [
                    "Check the service status.",
                    "Review the service logs.",
                ],
            },
        ]

        steps = extract_steps(evidence)

        self.assertEqual(
            steps.count("Check the service status."),
            1,
        )
        self.assertIn("Restart the application.", steps)
        self.assertIn("Review the service logs.", steps)

    def test_empty_ticket_is_rejected(self):
        result = generate_resolution(
            ticket_text="   ",
            evidence=[
                {
                    "score": 0.90,
                    "resolution": "Check the service status.",
                }
            ],
        )

        self.assertEqual(
            result,
            "No support ticket description was provided.",
        )

    def test_support_response_returns_context_and_resolution(self):
        evidence = [
            {
                "title": "Service issue",
                "category": "Pharmacy",
                "score": 0.80,
                "issue": "Service is unavailable",
                "resolution": "Check the service status.",
            }
        ]

        result = generate_support_response(
            ticket_text="Pharmacy service is unavailable",
            evidence=evidence,
            category="Pharmacy",
        )

        self.assertIn("context", result)
        self.assertIn("resolution", result)
        self.assertIn("SUPPORT TICKET", result["context"])
        self.assertIn("Check the service status.", result["resolution"])


if __name__ == "__main__":
    unittest.main()
