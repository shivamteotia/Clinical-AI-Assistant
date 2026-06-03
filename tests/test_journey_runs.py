import os
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.rag import patient_journey
from app.rag.journey_runs import read_journey_runs
from app.rag.patient_journey import JourneySummaryResult, generate_and_store_patient_journey
from scripts.seed_data import main as seed_data


class JourneyRunTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        os.environ["VECTOR_STORE_PROVIDER"] = "sqlite"
        with redirect_stdout(StringIO()):
            seed_data()
        cls.client = TestClient(app)

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        os.environ["CLINICAL_AI_JOURNEY_PATH"] = str(Path(self.temp_dir.name) / "patient_journeys.json")
        os.environ["CLINICAL_AI_JOURNEY_RUN_LOG_PATH"] = str(Path(self.temp_dir.name) / "journey_runs.jsonl")

    def tearDown(self) -> None:
        os.environ.pop("CLINICAL_AI_JOURNEY_PATH", None)
        os.environ.pop("CLINICAL_AI_JOURNEY_RUN_LOG_PATH", None)
        self.temp_dir.cleanup()

    def test_successful_generation_writes_completed_run(self) -> None:
        journey = generate_and_store_patient_journey("P001", use_llm=False, require_llm=False)
        runs = read_journey_runs(patient_id="P001")

        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0]["status"], "completed")
        self.assertEqual(runs[0]["patient_id"], "P001")
        self.assertEqual(runs[0]["provider"], "local")
        self.assertEqual(runs[0]["context_strategy"], "episodic_patient_context.v1")
        self.assertGreater(runs[0]["estimated_input_tokens"], 0)
        self.assertEqual(journey["latest_run"]["run_id"], runs[0]["run_id"])

    def test_failed_required_llm_generation_writes_failed_run(self) -> None:
        original = patient_journey._try_llm_summary
        patient_journey._try_llm_summary = lambda record, model=None, provider=None: JourneySummaryResult(
            summary=None,
            provider="groq",
            model="llama-test",
            error="provider unavailable",
        )
        try:
            with self.assertRaises(RuntimeError):
                generate_and_store_patient_journey(
                    "P001",
                    use_llm=True,
                    provider="groq",
                    model="llama-test",
                    require_llm=True,
                )
        finally:
            patient_journey._try_llm_summary = original

        runs = read_journey_runs(patient_id="P001")

        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0]["status"], "failed")
        self.assertEqual(runs[0]["provider"], "groq")
        self.assertEqual(runs[0]["model"], "llama-test")
        self.assertEqual(runs[0]["error_type"], "RuntimeError")

    def test_run_endpoints_return_recent_and_patient_filtered_runs(self) -> None:
        generate_and_store_patient_journey("P001", use_llm=False)
        generate_and_store_patient_journey("P002", use_llm=False)

        all_response = self.client.get("/journeys/runs?limit=10")
        patient_response = self.client.get("/patients/P001/journey/runs")

        self.assertEqual(all_response.status_code, 200)
        self.assertEqual(patient_response.status_code, 200)
        self.assertGreaterEqual(len(all_response.json()), 2)
        self.assertEqual([run["patient_id"] for run in patient_response.json()], ["P001"])


if __name__ == "__main__":
    unittest.main()
