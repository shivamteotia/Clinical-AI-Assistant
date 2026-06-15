import os
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.rag.journey_refresh import (
    list_pending_journey_refreshes,
    list_stale_patient_journeys,
    process_pending_journey_refreshes,
    queue_patient_journey_refresh,
)
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
        self.temp_dir = tempfile.TemporaryDirectory()
        temp_journey_path = Path(self.temp_dir.name) / "patient_journeys.json"
        if JOURNEY_PATH.exists():
            temp_journey_path.write_bytes(JOURNEY_PATH.read_bytes())
        os.environ["CLINICAL_AI_JOURNEY_PATH"] = str(temp_journey_path)
        os.environ["CLINICAL_AI_AUDIT_LOG_PATH"] = str(Path(self.temp_dir.name) / "audit.jsonl")
        os.environ["CLINICAL_AI_JOURNEY_REFRESH_QUEUE_PATH"] = str(Path(self.temp_dir.name) / "journey_refresh_queue.jsonl")

    def tearDown(self) -> None:
        os.environ.pop("CLINICAL_AI_JOURNEY_PATH", None)
        os.environ.pop("CLINICAL_AI_AUDIT_LOG_PATH", None)
        os.environ.pop("CLINICAL_AI_JOURNEY_REFRESH_QUEUE_PATH", None)
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

    def test_process_pending_queue_refreshes_queued_patient(self) -> None:
        queued = queue_patient_journey_refresh("P001", actor="test", metadata={"use_llm": False})
        self.assertIsNotNone(queued)
        self.assertEqual(len(list_pending_journey_refreshes()), 1)

        result = process_pending_journey_refreshes(actor="test", use_llm=False, limit=10)

        self.assertEqual(result["processed_count"], 1)
        self.assertEqual(result["failed_count"], 0)
        self.assertEqual(list_pending_journey_refreshes(), [])

    def test_queue_endpoints_list_and_process_pending_jobs(self) -> None:
        queued = queue_patient_journey_refresh("P001", actor="test", metadata={"use_llm": False})
        self.assertIsNotNone(queued)

        list_response = self.client.get("/journeys/queue")
        process_response = self.client.post(
            "/journeys/process-queue",
            json={"use_llm": False, "limit": 10},
        )

        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(list_response.json()["pending_count"], 1)
        self.assertEqual(process_response.status_code, 200)
        self.assertEqual(process_response.json()["processed_count"], 1)

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
