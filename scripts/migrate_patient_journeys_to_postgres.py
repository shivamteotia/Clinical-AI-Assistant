import argparse
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.rag.journey_schema import validate_patient_journey
from app.rag.journey_store import (
    DEFAULT_POSTGRES_URL,
    JsonJourneyStore,
    PostgresJourneyStore,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Migrate validated patient journey artifacts from JSON to PostgreSQL."
    )
    parser.add_argument(
        "--source",
        default=str(PROJECT_ROOT / "data" / "patient_journeys.json"),
        help="Source patient journey JSON file.",
    )
    parser.add_argument(
        "--database-url",
        default=os.getenv("DATABASE_URL", DEFAULT_POSTGRES_URL),
        help="Target PostgreSQL connection URL.",
    )
    args = parser.parse_args()

    source = JsonJourneyStore(Path(args.source))
    journeys = [validate_patient_journey(item) for item in source.load_all()]
    target = PostgresJourneyStore(args.database_url)
    target.replace_all(journeys)
    print(f"Migrated {len(journeys)} patient journeys to PostgreSQL.")


if __name__ == "__main__":
    main()
