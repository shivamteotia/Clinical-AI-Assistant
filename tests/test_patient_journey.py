import unittest
from contextlib import redirect_stdout
from io import StringIO

from app.rag.patient_journey import build_all_patient_journeys, get_patient_journey
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


if __name__ == "__main__":
    unittest.main()
