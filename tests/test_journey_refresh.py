import os
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.rag.journey_refresh import list_stale_patient_journeys
from app.rag.patient_journey import JOURNEY_PATH, load_patient_journeys, save_patient_journeys
from scripts.seed_data import main as seed_data


class JourneyRefreshTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        os.environ["VECTOR_STORE_PROVIDER"] = "sqlite"
        with redirect_stdout(StringIO()):
            seed_data()
        cls.client = TestClient(app)

    def setUp(self) -> None:
        self.original_journeys = JOURNEY_PATH.read_bytes() if JOURNEY_PATH.exists() else None
        self.temp_dir = tempfile.TemporaryDirectory()
        os.environ["CLINICAL_AI_AUDIT_LOG_PATH"] = str(Path(self.temp_dir.name) / "audit.jsonl")

    def tearDown(self) -> None:
        if self.original_journeys is None:
            JOURNEY_PATH.unlink(missing_ok=True)
        else:
            JOURNEY_PATH.write_bytes(self.original_journeys)
        os.environ.pop("CLINICAL_AI_AUDIT_LOG_PATH", None)
        self.temp_dir.cleanup()

    def test_stale_listing_and_refresh_endpoint_updates_patient_journey(self) -> None:
        journeys = list(load_patient_journeys().values())
        target = next(journey for journey in journeys if journey["patient_id"] == "P001")
        target["source_record_hash"] = "old-hash"
        target["source_record_version"] = "old-version"
        save_patient_journeys(journeys)

        stale = list_stale_patient_journeys()
        self.assertEqual([item["patient_id"] for item in stale], ["P001"])

        response = self.client.post(
            "/patients/P001/journey/refresh",
            json={"use_llm": False, "require_llm": False},
            headers={"x-user-id": "doctor-1"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "completed")
        self.assertEqual(payload["patient_id"], "P001")
        self.assertFalse(payload["journey"]["is_stale"])
        self.assertEqual(payload["journey"]["generated_by"], "local_fallback")
        self.assertEqual(list_stale_patient_journeys(), [])

    def test_refresh_stale_endpoint_refreshes_only_stale_records(self) -> None:
        journeys = list(load_patient_journeys().values())
        for journey in journeys:
            if journey["patient_id"] in {"P001", "P002"}:
                journey["source_record_hash"] = f"old-{journey['patient_id']}"
                journey["source_record_version"] = "old-version"
        save_patient_journeys(journeys)

        response = self.client.post(
            "/journeys/refresh-stale",
            json={"use_llm": False, "require_llm": False},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["stale_count"], 2)
        self.assertEqual(payload["refreshed_count"], 2)
        self.assertEqual(payload["failed_count"], 0)
        self.assertEqual(list_stale_patient_journeys(), [])

    def test_background_refresh_endpoint_queues_request(self) -> None:
        response = self.client.post(
            "/patients/P001/journey/refresh",
            json={"use_llm": False, "background": True},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "queued")
        self.assertEqual(payload["patient_id"], "P001")
        self.assertIn("refresh_id", payload)


if __name__ == "__main__":
    unittest.main()
