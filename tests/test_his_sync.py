import os
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from fastapi.testclient import TestClient

from app.his_sync import queue_or_process_his_journey_work, scan_his_journey_work
from app.main import app
from scripts.seed_data import main as seed_data


class HisSyncTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        os.environ["VECTOR_STORE_PROVIDER"] = "sqlite"
        with redirect_stdout(StringIO()):
            seed_data()
        cls.client = TestClient(app)

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        temp_path = Path(self.temp_dir.name)
        os.environ["CLINICAL_AI_HIS_SYNC_STATE_PATH"] = str(temp_path / "his_sync_state.json")
        os.environ["CLINICAL_AI_JOURNEY_PATH"] = str(temp_path / "patient_journeys.json")
        os.environ["CLINICAL_AI_JOURNEY_REFRESH_QUEUE_PATH"] = str(temp_path / "journey_refresh_queue.jsonl")
        os.environ["CLINICAL_AI_AUDIT_LOG_PATH"] = str(temp_path / "audit.jsonl")

    def tearDown(self) -> None:
        os.environ.pop("CLINICAL_AI_HIS_SYNC_STATE_PATH", None)
        os.environ.pop("CLINICAL_AI_JOURNEY_PATH", None)
        os.environ.pop("CLINICAL_AI_JOURNEY_REFRESH_QUEUE_PATH", None)
        os.environ.pop("CLINICAL_AI_AUDIT_LOG_PATH", None)
        self.temp_dir.cleanup()

    def test_scan_detects_patients_without_stored_journeys(self) -> None:
        result = scan_his_journey_work()

        self.assertEqual(result["patient_count"], 20)
        self.assertEqual(result["action_required_count"], 20)
        self.assertEqual(result["new_patient_count"], 20)
        self.assertTrue(all(item["change_type"] == "new_patient" for item in result["items"]))

    def test_queue_only_adds_actionable_patients_without_generating_all_journeys(self) -> None:
        result = queue_or_process_his_journey_work(actor="test", use_llm=False, process=False)

        self.assertEqual(result["queued_count"], 20)
        self.assertEqual(result["processed_count"], 0)
        queue_path = Path(os.environ["CLINICAL_AI_JOURNEY_REFRESH_QUEUE_PATH"])
        self.assertTrue(queue_path.exists())
        self.assertEqual(len(queue_path.read_text(encoding="utf-8").splitlines()), 20)

    def test_api_exposes_his_sync_status_and_queue(self) -> None:
        status_response = self.client.get("/his/sync/status")
        queue_response = self.client.post("/his/sync", json={"use_llm": False, "process": False})

        self.assertEqual(status_response.status_code, 200)
        self.assertEqual(status_response.json()["action_required_count"], 20)
        self.assertEqual(queue_response.status_code, 200)
        self.assertEqual(queue_response.json()["queued_count"], 20)


if __name__ == "__main__":
    unittest.main()
