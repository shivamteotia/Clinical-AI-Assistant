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
        help="Use local Ollama phi3 when available; falls back to local deterministic summaries.",
    )
    parser.add_argument(
        "--model",
        default="phi3",
        help="Ollama model to use when --ollama is enabled.",
    )
    args = parser.parse_args()

    journeys = build_all_patient_journeys(use_llm=args.ollama, model=args.model)
    save_patient_journeys(journeys)
    print(f"Generated {len(journeys)} patient journey summaries.")


if __name__ == "__main__":
    main()
