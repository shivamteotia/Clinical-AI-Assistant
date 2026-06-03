import argparse
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

from app.rag.journey_refresh import list_stale_patient_journeys, refresh_stale_patient_journeys


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", choices=["groq", "ollama", "local"], default=None)
    parser.add_argument("--model", default=None)
    parser.add_argument("--require-llm", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    stale = list_stale_patient_journeys()
    if args.dry_run:
        print(f"Stale patient journeys: {len(stale)}")
        for item in stale:
            print(f"{item['patient_id']} stored={item['source_record_version']} current={item['current_source_record_version']}")
        return

    provider = None if args.provider == "local" else args.provider
    result = refresh_stale_patient_journeys(
        actor="refresh_stale_journeys_script",
        use_llm=args.provider != "local",
        provider=provider,
        model=args.model,
        require_llm=args.require_llm,
    )
    print(result)


if __name__ == "__main__":
    main()
