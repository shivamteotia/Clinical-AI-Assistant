import os
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO

from fastapi.testclient import TestClient

from app.main import app
from scripts.seed_data import main as seed_data


class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        os.environ["VECTOR_STORE_PROVIDER"] = "sqlite"
        with redirect_stdout(StringIO()):
            seed_data()
        cls.client = TestClient(app)

    def test_admin_frontend_serves_html(self) -> None:
        response = self.client.get("/admin")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Admin Console", response.text)

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
        self.assertEqual(record["record_metadata"]["source_system"], "dummy_his")
        self.assertIn("record_hash", record["record_metadata"])

    def test_patient_journey_endpoint_returns_summary(self) -> None:
        response = self.client.get("/patients/P001/journey")

        self.assertEqual(response.status_code, 200)
        journey = response.json()
        self.assertEqual(journey["patient_id"], "P001")
        self.assertIn("summary", journey)
        self.assertIn("claims", journey)
        self.assertTrue(journey["claims"])
        self.assertFalse(journey["is_stale"])
        self.assertEqual(journey["source_record_hash"], journey["current_source_record_hash"])
        self.assertIn("generated_at", journey)
        self.assertTrue(journey["timeline"])

    def test_patient_journey_inspection_endpoint_returns_pipeline_stages(self) -> None:
        response = self.client.get("/patients/P001/journey/inspect")

        self.assertEqual(response.status_code, 200)
        inspection = response.json()
        self.assertEqual(inspection["patient_id"], "P001")
        self.assertTrue(inspection["dry_run"])
        self.assertGreaterEqual(len(inspection["stages"]), 8)
        self.assertEqual(inspection["stages"][0]["title"], "HIS Patient Row")
        self.assertEqual(inspection["stages"][1]["title"], "HIS Full Record")
        self.assertEqual(inspection["stages"][2]["title"], "Episode Builder Output")
        self.assertEqual(inspection["stages"][4]["title"], "Episode-Packed LLM Context")
        self.assertEqual(inspection["stages"][6]["title"], "LLM Request Payload")

    def test_patient_journey_generation_endpoint_stores_summary(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            os.environ["CLINICAL_AI_JOURNEY_PATH"] = os.path.join(temp_dir, "patient_journeys.json")
            try:
                response = self.client.post(
                    "/patients/P001/journey/generate",
                    json={"use_llm": False, "model": "phi3", "require_llm": False},
                )
            finally:
                os.environ.pop("CLINICAL_AI_JOURNEY_PATH", None)

        self.assertEqual(response.status_code, 200)
        journey = response.json()
        self.assertEqual(journey["patient_id"], "P001")
        self.assertEqual(journey["generated_by"], "local_fallback")
        self.assertIn("summary", journey)

    def test_patient_journey_feedback_endpoint_records_feedback(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            os.environ["CLINICAL_AI_JOURNEY_FEEDBACK_PATH"] = os.path.join(temp_dir, "journey_feedback.jsonl")
            os.environ["CLINICAL_AI_AUDIT_LOG_PATH"] = os.path.join(temp_dir, "audit.jsonl")
            try:
                response = self.client.post(
                    "/patients/P001/journey/feedback",
                    json={"feedback_type": "missing_info", "comment": "Please include latest labs."},
                    headers={"x-user-id": "doctor-1"},
                )
                feedback_file_exists = os.path.exists(os.environ["CLINICAL_AI_JOURNEY_FEEDBACK_PATH"])
            finally:
                os.environ.pop("CLINICAL_AI_JOURNEY_FEEDBACK_PATH", None)
                os.environ.pop("CLINICAL_AI_AUDIT_LOG_PATH", None)

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "recorded")
        self.assertEqual(payload["patient_id"], "P001")
        self.assertEqual(payload["feedback_type"], "missing_info")
        self.assertTrue(feedback_file_exists)

    def test_admin_can_list_journey_feedback(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            os.environ["CLINICAL_AI_JOURNEY_FEEDBACK_PATH"] = os.path.join(temp_dir, "journey_feedback.jsonl")
            os.environ["CLINICAL_AI_AUDIT_LOG_PATH"] = os.path.join(temp_dir, "audit.jsonl")
            try:
                self.client.post(
                    "/patients/P001/journey/feedback",
                    json={"feedback_type": "useful", "comment": "Helpful."},
                )
                response = self.client.get("/journey-feedback?patient_id=P001")
            finally:
                os.environ.pop("CLINICAL_AI_JOURNEY_FEEDBACK_PATH", None)
                os.environ.pop("CLINICAL_AI_AUDIT_LOG_PATH", None)

        self.assertEqual(response.status_code, 200)
        feedback = response.json()
        self.assertEqual(len(feedback), 1)
        self.assertEqual(feedback[0]["patient_id"], "P001")
        self.assertEqual(feedback[0]["feedback_type"], "useful")
    def test_patient_scoped_ask_returns_selected_patient_sources(self) -> None:
        response = self.client.post(
            "/patients/P001/ask",
            json={"query": "What medications is this patient taking?", "k": 3},
        )

        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertEqual(result["scoped_patient_id"], "P001")
        self.assertTrue(result["sources"])
        self.assertTrue(
            all(source["metadata"]["patient_id"] == "P001" for source in result["sources"])
        )

    def test_missing_patient_returns_404(self) -> None:
        response = self.client.get("/patients/NOPE/record")

        self.assertEqual(response.status_code, 404)

    def test_rag_status_reports_local_vector_store(self) -> None:
        response = self.client.get("/rag/status")

        self.assertEqual(response.status_code, 200)
        status = response.json()
        self.assertEqual(status["provider"], "sqlite")
        self.assertIn(status["status"], {"ready", "empty", "missing"})
        self.assertIn("chunk_count", status)


if __name__ == "__main__":
    unittest.main()
