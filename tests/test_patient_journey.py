import unittest
import json
from contextlib import redirect_stdout
from io import StringIO

from app.rag import patient_journey
from app.rag.patient_journey import (
    JourneySummaryResult,
    PATIENT_JOURNEY_SYSTEM_PROMPT,
    build_all_patient_journeys,
    build_groq_journey_payload,
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
        patient_journey._try_llm_summary = lambda record, model=None, provider=None: JourneySummaryResult(
            summary="LLM generated journey.",
            provider="groq",
            model="llama-test",
        )
        try:
            journey = build_patient_journey(
                record,
                use_llm=True,
                provider="groq",
                model="llama-test",
            )
        finally:
            patient_journey._try_llm_summary = original

        self.assertEqual(journey["summary"], "LLM generated journey.")
        self.assertEqual(journey["generated_by"], "groq:llama-test")
        self.assertEqual(journey["journey_model"], "llama-test")
        self.assertEqual(journey["system_prompt"], PATIENT_JOURNEY_SYSTEM_PROMPT)

    def test_require_llm_raises_when_provider_fails(self) -> None:
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
        patient_journey._try_llm_summary = lambda record, model=None, provider=None: JourneySummaryResult(
            summary=None,
            provider="groq",
            model="llama-test",
            error="missing key",
        )
        try:
            with self.assertRaises(RuntimeError):
                build_patient_journey(record, use_llm=True, require_llm=True)
        finally:
            patient_journey._try_llm_summary = original

    def test_groq_summary_uses_chat_completions_payload(self) -> None:
        captured = {}

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return False

            def read(self) -> bytes:
                return json.dumps({
                    "choices": [
                        {"message": {"content": "Hosted LLM holistic view."}}
                    ]
                }).encode("utf-8")

        def fake_urlopen(request, timeout):
            captured["url"] = request.full_url
            captured["timeout"] = timeout
            captured["body"] = json.loads(request.data.decode("utf-8"))
            captured["authorization"] = request.headers["Authorization"]
            return FakeResponse()

        original_urlopen = patient_journey.urlopen
        patient_journey.urlopen = fake_urlopen
        try:
            result = patient_journey._try_groq_summary(
                {"patient": {"patient_id": "P001"}},
                "llama-test",
                "secret",
                "https://api.groq.com/openai/v1/chat/completions",
            )
        finally:
            patient_journey.urlopen = original_urlopen

        self.assertEqual(result.summary, "Hosted LLM holistic view.")
        self.assertEqual(result.provider, "groq")
        self.assertEqual(captured["authorization"], "Bearer secret")
        self.assertEqual(captured["body"]["model"], "llama-test")
        self.assertEqual(captured["body"]["messages"][0]["role"], "system")

    def test_groq_payload_can_be_inspected_without_calling_provider(self) -> None:
        record = {
            "patient": {"patient_id": "PX01", "name": "Test Patient"},
            "encounters": [],
            "labs": [],
            "medications": [],
            "clinical_notes": [],
        }

        payload = build_groq_journey_payload(record, "llama-test")

        self.assertEqual(payload["model"], "llama-test")
        self.assertEqual(payload["temperature"], 0.2)
        self.assertEqual(payload["max_tokens"], 550)
        self.assertEqual(payload["messages"][0]["content"], PATIENT_JOURNEY_SYSTEM_PROMPT)
        self.assertIn('"patient_id": "PX01"', payload["messages"][1]["content"])


if __name__ == "__main__":
    unittest.main()
