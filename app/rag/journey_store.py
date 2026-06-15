from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Callable, Protocol

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_JSON_PATH = PROJECT_ROOT / "data" / "patient_journeys.json"
DEFAULT_POSTGRES_URL = "postgresql://clinical_ai:clinical_ai@postgres:5432/clinical_ai"


class JourneyStore(Protocol):
    provider: str

    def load_all(self) -> list[dict[str, Any]]: ...

    def upsert(self, journey: dict[str, Any]) -> None: ...

    def replace_all(self, journeys: list[dict[str, Any]]) -> None: ...


class JsonJourneyStore:
    provider = "json"

    def __init__(self, path: Path):
        self.path = path

    def load_all(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        with self.path.open("r", encoding="utf-8") as file:
            payload = json.load(file)
        if not isinstance(payload, list):
            raise ValueError("Patient journey JSON store must contain a list.")
        return payload

    def upsert(self, journey: dict[str, Any]) -> None:
        journeys = {
            item["patient_id"]: item
            for item in self.load_all()
        }
        journeys[journey["patient_id"]] = journey
        self.replace_all(sorted(journeys.values(), key=lambda item: item["patient_id"]))

    def replace_all(self, journeys: list[dict[str, Any]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w", encoding="utf-8") as file:
            json.dump(journeys, file, indent=2)
            file.write("\n")


class PostgresJourneyStore:
    provider = "postgres"

    def __init__(
        self,
        database_url: str,
        *,
        connect_factory: Callable[[str], Any] | None = None,
        json_adapter: Callable[[dict[str, Any]], Any] | None = None,
    ):
        self.database_url = database_url
        self._connect_factory = connect_factory
        self._json_adapter = json_adapter

    def initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS patient_journeys (
                    patient_id TEXT PRIMARY KEY,
                    journey_schema_version TEXT NOT NULL,
                    source_record_version TEXT,
                    source_record_hash TEXT,
                    generated_at TIMESTAMPTZ NOT NULL,
                    generated_by TEXT NOT NULL,
                    journey_json JSONB NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_patient_journeys_source_record_version
                ON patient_journeys (source_record_version)
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_patient_journeys_generated_at
                ON patient_journeys (generated_at DESC)
                """
            )

    def load_all(self) -> list[dict[str, Any]]:
        self.initialize()
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT journey_json FROM patient_journeys ORDER BY patient_id"
            ).fetchall()
        return [self._decode_json(row[0]) for row in rows]

    def upsert(self, journey: dict[str, Any]) -> None:
        self.initialize()
        with self._connect() as connection:
            self._upsert_with_connection(connection, journey)

    def replace_all(self, journeys: list[dict[str, Any]]) -> None:
        self.initialize()
        with self._connect() as connection:
            connection.execute("DELETE FROM patient_journeys")
            for journey in journeys:
                self._upsert_with_connection(connection, journey)

    def _upsert_with_connection(self, connection: Any, journey: dict[str, Any]) -> None:
        connection.execute(
            """
            INSERT INTO patient_journeys (
                patient_id,
                journey_schema_version,
                source_record_version,
                source_record_hash,
                generated_at,
                generated_by,
                journey_json,
                updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
            ON CONFLICT (patient_id) DO UPDATE SET
                journey_schema_version = EXCLUDED.journey_schema_version,
                source_record_version = EXCLUDED.source_record_version,
                source_record_hash = EXCLUDED.source_record_hash,
                generated_at = EXCLUDED.generated_at,
                generated_by = EXCLUDED.generated_by,
                journey_json = EXCLUDED.journey_json,
                updated_at = NOW()
            """,
            (
                journey["patient_id"],
                journey["journey_schema_version"],
                journey.get("source_record_version"),
                journey.get("source_record_hash"),
                journey["generated_at"],
                journey["generated_by"],
                self._adapt_json(journey),
            ),
        )

    def _connect(self):
        if self._connect_factory is not None:
            return self._connect_factory(self.database_url)
        try:
            import psycopg
        except ImportError as error:
            raise RuntimeError(
                "PostgreSQL journey storage requires psycopg. Install project requirements."
            ) from error
        return psycopg.connect(self.database_url)

    def _adapt_json(self, payload: dict[str, Any]):
        if self._json_adapter is not None:
            return self._json_adapter(payload)
        from psycopg.types.json import Jsonb

        return Jsonb(payload)

    @staticmethod
    def _decode_json(payload: Any) -> dict[str, Any]:
        if isinstance(payload, dict):
            return payload
        if isinstance(payload, str):
            decoded = json.loads(payload)
            if isinstance(decoded, dict):
                return decoded
        raise ValueError("PostgreSQL journey_json must contain a JSON object.")


def get_json_journey_path() -> Path:
    configured_path = os.getenv("CLINICAL_AI_JOURNEY_PATH")
    return Path(configured_path) if configured_path else DEFAULT_JSON_PATH


def get_journey_store_provider() -> str:
    return os.getenv("JOURNEY_STORE_PROVIDER", "json").strip().lower()


def get_journey_store() -> JourneyStore:
    provider = get_journey_store_provider()
    if provider == "json":
        return JsonJourneyStore(get_json_journey_path())
    if provider == "postgres":
        database_url = os.getenv("DATABASE_URL", DEFAULT_POSTGRES_URL).strip()
        if not database_url:
            raise RuntimeError("DATABASE_URL is required for PostgreSQL journey storage.")
        return PostgresJourneyStore(database_url)
    raise RuntimeError(f"Unsupported journey store provider: {provider}")


def journey_store_status() -> dict[str, Any]:
    provider = get_journey_store_provider()
    return {
        "provider": provider,
        "json_path": str(get_json_journey_path()) if provider == "json" else None,
        "database_url_configured": bool(os.getenv("DATABASE_URL")) if provider == "postgres" else False,
    }
