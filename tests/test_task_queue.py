import os
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.queue_backend import get_task_queue_settings, task_queue_status
from app.rag.journey_refresh import (
    dispatch_pending_journey_refreshes,
    queue_and_dispatch_patient_journey_refresh,
    queue_patient_journey_refresh,
)
from scripts.seed_data import main as seed_data


class TaskQueueTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        with redirect_stdout(StringIO()):
            seed_data()
        cls.client = TestClient(app)

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        base = Path(self.temp_dir.name)
        os.environ["CLINICAL_AI_JOURNEY_REFRESH_QUEUE_PATH"] = str(base / "queue.jsonl")
        os.environ["CLINICAL_AI_AUDIT_LOG_PATH"] = str(base / "audit.jsonl")
        os.environ["TASK_QUEUE_PROVIDER"] = "local"
        os.environ.pop("CELERY_BROKER_URL", None)
        os.environ.pop("CELERY_RESULT_BACKEND", None)

    def tearDown(self) -> None:
        os.environ.pop("CLINICAL_AI_JOURNEY_REFRESH_QUEUE_PATH", None)
        os.environ.pop("CLINICAL_AI_AUDIT_LOG_PATH", None)
        os.environ.pop("TASK_QUEUE_PROVIDER", None)
        os.environ.pop("CELERY_BROKER_URL", None)
        os.environ.pop("CELERY_RESULT_BACKEND", None)
        self.temp_dir.cleanup()

    def test_local_queue_provider_does_not_dispatch(self) -> None:
        event = queue_and_dispatch_patient_journey_refresh("P001", actor="test")

        self.assertIsNotNone(event)
        self.assertNotIn("task_queue", event)
        self.assertFalse(get_task_queue_settings().enabled)

    def test_celery_queue_provider_dispatches_event(self) -> None:
        os.environ["TASK_QUEUE_PROVIDER"] = "celery"
        os.environ["CELERY_BROKER_URL"] = "redis://redis:6379/0"
        os.environ["CELERY_RESULT_BACKEND"] = "redis://redis:6379/1"

        with patch("app.rag.journey_refresh.enqueue_journey_refresh_task") as enqueue:
            enqueue.return_value = {"queued": True, "provider": "celery", "task_id": "task-1"}
            event = queue_and_dispatch_patient_journey_refresh("P001", actor="test")

        self.assertEqual(event["task_queue"]["task_id"], "task-1")
        enqueue.assert_called_once()

    def test_dispatch_pending_uses_celery_backend(self) -> None:
        queue_patient_journey_refresh("P001", actor="test")
        os.environ["TASK_QUEUE_PROVIDER"] = "celery"

        with patch("app.rag.journey_refresh.enqueue_journey_refresh_task") as enqueue:
            enqueue.return_value = {"queued": True, "provider": "celery", "task_id": "task-1"}
            result = dispatch_pending_journey_refreshes(actor="test", limit=10)

        self.assertEqual(result["status"], "dispatched")
        self.assertEqual(result["dispatched_count"], 1)
        self.assertEqual(result["dispatched"][0]["task_id"], "task-1")

    def test_admin_status_reports_task_queue_provider(self) -> None:
        os.environ["TASK_QUEUE_PROVIDER"] = "celery"
        os.environ["CELERY_BROKER_URL"] = "redis://redis:6379/0"

        response = self.client.get("/admin/status")

        self.assertEqual(response.status_code, 200)
        task_queue = response.json()["journeys"]["task_queue"]
        self.assertEqual(task_queue["provider"], "celery")
        self.assertTrue(task_queue["broker_url_configured"])
        self.assertNotIn("redis://", str(task_queue))

    def test_task_queue_status_does_not_expose_urls(self) -> None:
        os.environ["TASK_QUEUE_PROVIDER"] = "celery"
        os.environ["CELERY_BROKER_URL"] = "redis://redis:6379/0"

        status = task_queue_status()

        self.assertEqual(status["provider"], "celery")
        self.assertNotIn("broker_url", status)


if __name__ == "__main__":
    unittest.main()
