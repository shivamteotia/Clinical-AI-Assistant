import unittest

from pydantic import ValidationError

from app.api.canonical_his import get_canonical_patient_record
from app.rag.journey_schema import (
    JOURNEY_SCHEMA_VERSION,
    validate_llm_journey_response,
    validate_patient_journey,
)
from app.rag.patient_journey import build_patient_journey
from scripts.seed_data import main as seed_data


class JourneySchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        seed_data()

    def test_generated_journey_uses_versioned_schema(self) -> None:
        record = get_canonical_patient_record("P001")

        journey = build_patient_journey(record, use_llm=False)

        self.assertEqual(journey["journey_schema_version"], JOURNEY_SCHEMA_VERSION)
        self.assertEqual(journey["patient_id"], "P001")

    def test_legacy_journey_is_upgraded_to_current_schema(self) -> None:
        record = get_canonical_patient_record("P001")
        journey = build_patient_journey(record, use_llm=False)
        journey.pop("journey_schema_version")

        validated = validate_patient_journey(journey, record=record, require_current_source=True)

        self.assertEqual(validated["journey_schema_version"], JOURNEY_SCHEMA_VERSION)

    def test_unknown_artifact_fields_are_rejected(self) -> None:
        record = get_canonical_patient_record("P001")
        journey = build_patient_journey(record, use_llm=False)
        journey["unexpected"] = "not allowed"

        with self.assertRaises(ValidationError):
            validate_patient_journey(journey)

    def test_llm_claim_sources_must_exist_in_canonical_record(self) -> None:
        payload = {
            "summary": "The patient has a recorded diagnosis.",
            "claims": [
                {
                    "sentence": "The patient has a recorded diagnosis.",
                    "sources": ["encounter:DOES_NOT_EXIST"],
                }
            ],
        }

        with self.assertRaisesRegex(ValueError, "unknown source IDs"):
            validate_llm_journey_response(payload, {"patient:P001"})

    def test_llm_claim_sentence_must_appear_in_summary(self) -> None:
        payload = {
            "summary": "The patient has a recorded diagnosis.",
            "claims": [
                {
                    "sentence": "The patient is taking an invented medication.",
                    "sources": ["patient:P001"],
                }
            ],
        }

        with self.assertRaises(ValidationError):
            validate_llm_journey_response(payload, {"patient:P001"})


if __name__ == "__main__":
    unittest.main()
