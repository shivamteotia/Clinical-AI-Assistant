import argparse
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

from app.rag.patient_journey import build_all_patient_journeys, save_patient_journeys


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--ollama",
        action="store_true",
        help="Shortcut for --provider ollama.",
    )
    parser.add_argument(
        "--provider",
        choices=["groq", "ollama", "local"],
        default=None,
        help="LLM provider for generated summaries. Defaults to PATIENT_JOURNEY_LLM_PROVIDER.",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Model to use for the selected provider. Defaults to PATIENT_JOURNEY_MODEL.",
    )
    parser.add_argument(
        "--require-llm",
        action="store_true",
        help="Fail instead of saving local fallback summaries if LLM generation fails.",
    )
    args = parser.parse_args()

    provider = "ollama" if args.ollama else args.provider
    use_llm = provider != "local"
    journeys = build_all_patient_journeys(
        use_llm=use_llm,
        model=args.model,
        provider=provider,
        require_llm=args.require_llm,
    )
    save_patient_journeys(journeys)
    print(f"Generated {len(journeys)} patient journey summaries.")


if __name__ == "__main__":
    main()
