import unittest

from app.rag.safety import SAFETY_NOTICE, attach_safety_metadata, source_confidence


class SafetyTests(unittest.TestCase):
    def test_confidence_thresholds(self) -> None:
        self.assertEqual(source_confidence([]), "none")
        self.assertEqual(source_confidence([{"score": 0.2}]), "low")
        self.assertEqual(source_confidence([{"score": 0.5}]), "medium")
        self.assertEqual(source_confidence([{"score": 0.8}]), "high")

    def test_safety_metadata_always_includes_notice(self) -> None:
        result = attach_safety_metadata({"answer": "No sources.", "sources": []})

        self.assertEqual(result["confidence"], "none")
        self.assertIn(SAFETY_NOTICE, result["safety_warnings"])
        self.assertGreaterEqual(len(result["safety_warnings"]), 2)


if __name__ == "__main__":
    unittest.main()
