import unittest
from contextlib import redirect_stdout
from io import StringIO

from fastapi.testclient import TestClient

from app.main import app
from scripts.seed_data import main as seed_data


class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        with redirect_stdout(StringIO()):
            seed_data()
        cls.client = TestClient(app)

    def test_health_endpoint(self) -> None:
        response = self.client.get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_patient_list_contains_seeded_patients(self) -> None:
        response = self.client.get("/patients")

        self.assertEqual(response.status_code, 200)
        patients = response.json()
        self.assertGreaterEqual(len(patients), 20)
        self.assertEqual(patients[0]["patient_id"], "P001")

    def test_patient_record_contains_structured_sections(self) -> None:
        response = self.client.get("/patients/P001/record")

        self.assertEqual(response.status_code, 200)
        record = response.json()
        self.assertEqual(record["patient"]["patient_id"], "P001")
        self.assertTrue(record["encounters"])
        self.assertTrue(record["labs"])
        self.assertTrue(record["medications"])
        self.assertTrue(record["clinical_notes"])

    def test_missing_patient_returns_404(self) -> None:
        response = self.client.get("/patients/NOPE/record")

        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
