import unittest
from contextlib import redirect_stdout
from io import StringIO

from app.rag import patient_journey
from app.rag.patient_journey import (
    PATIENT_JOURNEY_SYSTEM_PROMPT,
    build_all_patient_journeys,
    build_patient_journey,
    get_patient_journey,
)
from scripts.seed_data import main as seed_data


class PatientJourneyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        with redirect_stdout(StringIO()):
            seed_data()

    def test_build_all_patient_journeys_creates_one_summary_per_patient(self) -> None:
        journeys = build_all_patient_journeys()

        self.assertEqual(len(journeys), 20)
        self.assertEqual(journeys[0]["patient_id"], "P001")
        self.assertIn("summary", journeys[0])
        self.assertTrue(journeys[0]["timeline"])

    def test_get_patient_journey_returns_stored_or_fallback_summary(self) -> None:
        journey = get_patient_journey("P001")

        self.assertIsNotNone(journey)
        self.assertEqual(journey["patient_id"], "P001")
        self.assertIn("Aarav Sharma", journey["summary"])
        self.assertTrue(journey["key_labs"])

    def test_llm_journey_uses_system_prompt_and_model_metadata(self) -> None:
        record = {
            "patient": {
                "patient_id": "PX01",
                "name": "Test Patient",
                "age": 50,
                "gender": "Female",
            },
            "encounters": [],
            "labs": [],
            "medications": [],
            "clinical_notes": [],
        }
        original = patient_journey._try_llm_summary
        patient_journey._try_llm_summary = lambda record, model: "LLM generated journey."
        try:
            journey = build_patient_journey(record, use_llm=True, model="phi3")
        finally:
            patient_journey._try_llm_summary = original

        self.assertEqual(journey["summary"], "LLM generated journey.")
        self.assertEqual(journey["generated_by"], "ollama:phi3")
        self.assertEqual(journey["journey_model"], "phi3")
        self.assertEqual(journey["system_prompt"], PATIENT_JOURNEY_SYSTEM_PROMPT)


if __name__ == "__main__":
    unittest.main()
