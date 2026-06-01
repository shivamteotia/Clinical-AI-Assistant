import os
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from fastapi.testclient import TestClient

from app.audit import read_audit_events, write_audit_event
from app.main import app
from scripts.seed_data import main as seed_data


class AuditLoggingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        os.environ["VECTOR_STORE_PROVIDER"] = "sqlite"
        with redirect_stdout(StringIO()):
            seed_data()
        cls.client = TestClient(app)

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.audit_path = Path(self.temp_dir.name) / "audit_logs.jsonl"
        os.environ["CLINICAL_AI_AUDIT_LOG_PATH"] = str(self.audit_path)

    def tearDown(self) -> None:
        os.environ.pop("CLINICAL_AI_AUDIT_LOG_PATH", None)
        self.temp_dir.cleanup()

    def test_patient_record_and_journey_views_are_audited(self) -> None:
        record_response = self.client.get("/patients/P001/record", headers={"x-user-id": "doctor-1"})
        journey_response = self.client.get("/patients/P001/journey", headers={"x-user-id": "doctor-1"})
        audit_response = self.client.get("/audit/events?limit=10")

        self.assertEqual(record_response.status_code, 200)
        self.assertEqual(journey_response.status_code, 200)
        self.assertEqual(audit_response.status_code, 200)

        events = audit_response.json()
        event_types = [event["event_type"] for event in events]
        self.assertIn("patient_record_viewed", event_types)
        self.assertIn("patient_journey_viewed", event_types)

        journey_event = next(event for event in events if event["event_type"] == "patient_journey_viewed")
        self.assertEqual(journey_event["actor"], "doctor-1")
        self.assertEqual(journey_event["patient_id"], "P001")
        self.assertIn("is_stale", journey_event["metadata"])
        self.assertNotIn("summary", journey_event["metadata"])

    def test_audit_metadata_redacts_sensitive_fields(self) -> None:
        write_audit_event(
            "test_event",
            actor="tester",
            patient_id="P001",
            metadata={
                "api_key": "secret-key",
                "system_prompt": "hidden prompt",
                "note_text": "clinical note text",
                "safe_count": 3,
            },
        )

        events = read_audit_events(limit=1)

        self.assertEqual(events[0]["metadata"]["api_key"], "[redacted]")
        self.assertEqual(events[0]["metadata"]["system_prompt"], "[redacted]")
        self.assertEqual(events[0]["metadata"]["note_text"], "[redacted]")
        self.assertEqual(events[0]["metadata"]["safe_count"], 3)


if __name__ == "__main__":
    unittest.main()
