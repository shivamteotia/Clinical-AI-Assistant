import unittest
from contextlib import redirect_stdout
from io import StringIO

from app.rag.answering import answer_question
from app.rag.vector_store import rebuild_vector_store, search_patient_chunks
from scripts.seed_data import main as seed_data


class RagTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        with redirect_stdout(StringIO()):
            seed_data()
        rebuild_vector_store()

    def test_search_returns_expected_diabetes_patient(self) -> None:
        matches = search_patient_chunks("Which patient has diabetes and high HbA1c?", k=3)

        self.assertTrue(matches)
        self.assertEqual(matches[0]["metadata"]["patient_id"], "P001")

    def test_search_returns_expected_ckd_patient(self) -> None:
        matches = search_patient_chunks(
            "Which patient has chronic kidney disease with reduced eGFR?",
            k=3,
        )

        self.assertTrue(matches)
        self.assertEqual(matches[0]["metadata"]["patient_id"], "P009")

    def test_answer_includes_sources_and_safety_metadata(self) -> None:
        result = answer_question("What medication is P001 taking?", k=3)

        self.assertIn("P001", result["answer"])
        self.assertTrue(result["sources"])
        self.assertIn(result["confidence"], {"low", "medium", "high"})
        self.assertTrue(result["safety_warnings"])


if __name__ == "__main__":
    unittest.main()
