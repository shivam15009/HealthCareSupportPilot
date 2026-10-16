import unittest

from rag.retriever import KnowledgeRetriever, build_duplicate_signature


class DuplicateSignatureTests(unittest.TestCase):
    def test_workstation_variants_with_same_resolution_match(self):
        resolution = [
            "Confirm whether the message is limited to one workstation or multiple users.",
            "Check the approved service status or local support channel.",
            "Retry the operation after confirming connectivity.",
        ]

        base = {
            "category": "Pharmacy",
            "issue": "Pharmacy workstation: Service unavailable.",
            "resolution": resolution,
        }

        variant = {
            "category": "Pharmacy",
            "issue": "Shared pharmacy workstation: Service unavailable.",
            "resolution": resolution,
        }

        self.assertEqual(
            build_duplicate_signature(base),
            build_duplicate_signature(variant),
        )

    def test_different_resolutions_remain_distinct(self):
        first = {
            "category": "Pharmacy",
            "issue": "Service unavailable.",
            "resolution": ["Check the approved service status."],
        }

        second = {
            "category": "Pharmacy",
            "issue": "Service unavailable.",
            "resolution": ["Check the workstation network connection."],
        }

        self.assertNotEqual(
            build_duplicate_signature(first),
            build_duplicate_signature(second),
        )


class RetrievalRankingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retriever = KnowledgeRetriever()

    def search(self, query, top_k=5):
        return self.retriever.search(
            query=query,
            category="Pharmacy",
            top_k=top_k,
        )

    def test_service_unavailable_ranks_above_printing_issue(self):
        results = self.search(
            "Pharmacy application shows a service unavailable message",
            top_k=10,
        )

        self.assertTrue(results)

        titles = [item.get("title", "").lower() for item in results]

        service_indices = [
            i for i, title in enumerate(titles)
            if "service unavailable" in title
        ]

        printing_indices = [
            i for i, title in enumerate(titles)
            if "print" in title
        ]

        self.assertTrue(
            service_indices,
            "Expected a service-unavailable result.",
        )

        if printing_indices:
            self.assertLess(service_indices[0], printing_indices[0])

    def test_connectivity_query_ranks_exact_issue_first(self):
        results = self.search(
            "Pharmacy application cannot connect to the prescription service"
        )

        self.assertTrue(results)
        self.assertIn("cannot connect", results[0].get("title", "").lower())

    def test_printing_query_ranks_exact_issue_first(self):
        results = self.search(
            "Pharmacy application cannot print a transaction document"
        )

        self.assertTrue(results)
        self.assertIn("cannot print", results[0].get("title", "").lower())

    def test_authentication_query_ranks_exact_issue_first(self):
        results = self.search(
            "Pharmacy workstation cannot authenticate"
        )

        self.assertTrue(results)
        self.assertIn("cannot authenticate", results[0].get("title", "").lower())


    
    def test_timeout_query_ranks_timeout_guidance_first(self):
        results = self.search(
            "Pharmacy application request timed out",
            top_k=10,
        )

        self.assertTrue(results)

        first = results[0]
        first_text = " ".join([
            first.get("title", ""),
            first.get("issue", ""),
            " ".join(first.get("keywords", [])),
        ]).lower()

        self.assertTrue(
            any(
                phrase in first_text
                for phrase in ("timeout", "timed out", "times out")
            ),
            "Expected timeout-specific guidance to rank first, "
            f"but got: {first.get('title')}",
        )




if __name__ == "__main__":
    unittest.main()
