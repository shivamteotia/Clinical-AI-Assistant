import unittest

from app.rag.safety import (
    SAFETY_NOTICE,
    attach_safety_metadata,
    classify_query_intent,
    safety_level_for_intent,
    source_confidence,
)


class SafetyTests(unittest.TestCase):
    def test_confidence_thresholds(self) -> None:
        self.assertEqual(source_confidence([]), "none")
        self.assertEqual(source_confidence([{"score": 0.2}]), "low")
        self.assertEqual(source_confidence([{"score": 0.5}]), "medium")
        self.assertEqual(source_confidence([{"score": 0.8}]), "high")

    def test_safety_metadata_always_includes_notice(self) -> None:
        result = attach_safety_metadata({"answer": "No sources.", "sources": []})

        self.assertEqual(result["confidence"], "none")
        self.assertEqual(result["intent"], "record_lookup")
        self.assertEqual(result["safety_level"], "standard")
        self.assertIn(SAFETY_NOTICE, result["safety_warnings"])
        self.assertTrue(result["limitations"])
        self.assertGreaterEqual(len(result["safety_warnings"]), 2)

    def test_classifies_treatment_and_emergency_intents(self) -> None:
        self.assertEqual(
            classify_query_intent("Should P001 increase metformin dose?"),
            "treatment_request",
        )
        self.assertEqual(
            safety_level_for_intent("treatment_request"),
            "restricted",
        )
        self.assertEqual(
            classify_query_intent("Is chest pain an emergency?"),
            "emergency",
        )
        self.assertEqual(safety_level_for_intent("emergency"), "urgent")

    def test_restricted_metadata_adds_guidance_warning(self) -> None:
        result = attach_safety_metadata(
            {"answer": "No advice.", "sources": [{"score": 0.8}]},
            "Should P001 stop medication?",
        )

        self.assertEqual(result["intent"], "treatment_request")
        self.assertEqual(result["safety_level"], "restricted")
        self.assertTrue(
            any("diagnosis or treatment guidance" in warning for warning in result["safety_warnings"])
        )


if __name__ == "__main__":
    unittest.main()
