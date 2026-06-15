import json
import os
import tempfile
import unittest
from pathlib import Path

from app.rag.journey_store import (
    JsonJourneyStore,
    PostgresJourneyStore,
    get_journey_store,
    journey_store_status,
)


class FakeResult:
    def __init__(self, rows=None):
        self.rows = rows or []

    def fetchall(self):
        return self.rows


class FakePostgresState:
    def __init__(self):
        self.rows = {}
        self.statements = []


class FakeConnection:
    def __init__(self, state):
        self.state = state

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def execute(self, statement, parameters=None):
        normalized = " ".join(statement.split())
        self.state.statements.append((normalized, parameters))
        if normalized.startswith("DELETE FROM patient_journeys"):
            self.state.rows.clear()
        elif normalized.startswith("INSERT INTO patient_journeys"):
            self.state.rows[parameters[0]] = parameters[6]
        elif normalized.startswith("SELECT journey_json"):
            rows = [
                (self.state.rows[patient_id],)
                for patient_id in sorted(self.state.rows)
            ]
            return FakeResult(rows)
        return FakeResult()


class JourneyStoreTests(unittest.TestCase):
    def test_json_store_replaces_and_upserts_patient_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = JsonJourneyStore(Path(temp_dir) / "journeys.json")
            store.replace_all([
                {"patient_id": "P002", "summary": "second"},
                {"patient_id": "P001", "summary": "first"},
            ])
            store.upsert({"patient_id": "P001", "summary": "updated"})

            loaded = store.load_all()

        self.assertEqual([item["patient_id"] for item in loaded], ["P001", "P002"])
        self.assertEqual(loaded[0]["summary"], "updated")

    def test_postgres_store_initializes_upserts_and_reads_jsonb(self) -> None:
        state = FakePostgresState()
        store = PostgresJourneyStore(
            "postgresql://test",
            connect_factory=lambda _: FakeConnection(state),
            json_adapter=lambda payload: json.dumps(payload),
        )
        journey = {
            "patient_id": "P001",
            "journey_schema_version": "patient_journey.v1",
            "source_record_version": "version-1",
            "source_record_hash": "hash-1",
            "generated_at": "2026-06-15T00:00:00Z",
            "generated_by": "test",
        }

        store.upsert(journey)
        loaded = store.load_all()

        self.assertEqual(loaded, [journey])
        self.assertTrue(any("CREATE TABLE IF NOT EXISTS patient_journeys" in sql for sql, _ in state.statements))
        self.assertTrue(any("ON CONFLICT (patient_id) DO UPDATE" in sql for sql, _ in state.statements))

    def test_store_factory_defaults_to_json_and_reports_safe_status(self) -> None:
        old_provider = os.environ.pop("JOURNEY_STORE_PROVIDER", None)
        old_path = os.environ.get("CLINICAL_AI_JOURNEY_PATH")
        with tempfile.TemporaryDirectory() as temp_dir:
            os.environ["CLINICAL_AI_JOURNEY_PATH"] = str(Path(temp_dir) / "journeys.json")
            try:
                store = get_journey_store()
                status = journey_store_status()
            finally:
                if old_provider is not None:
                    os.environ["JOURNEY_STORE_PROVIDER"] = old_provider
                else:
                    os.environ.pop("JOURNEY_STORE_PROVIDER", None)
                if old_path is not None:
                    os.environ["CLINICAL_AI_JOURNEY_PATH"] = old_path
                else:
                    os.environ.pop("CLINICAL_AI_JOURNEY_PATH", None)

        self.assertIsInstance(store, JsonJourneyStore)
        self.assertEqual(status["provider"], "json")
        self.assertNotIn("database_url", status)


if __name__ == "__main__":
    unittest.main()
