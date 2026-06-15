import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.his_sync import queue_or_process_his_journey_work, scan_his_journey_work


def main() -> None:
    parser = argparse.ArgumentParser(description="Scan dummy HIS for new/changed patients needing journey generation.")
    parser.add_argument("--queue", action="store_true", help="Queue new/changed patient journeys without generating them now.")
    parser.add_argument("--process", action="store_true", help="Generate/refresh new or changed patient journeys immediately.")
    parser.add_argument("--provider", default=None, help="Optional LLM provider override, such as groq or ollama.")
    parser.add_argument("--model", default=None, help="Optional journey model override.")
    parser.add_argument("--require-llm", action="store_true", help="Fail instead of falling back locally if LLM generation fails.")
    parser.add_argument("--local-only", action="store_true", help="Use local fallback generation instead of calling an LLM.")
    args = parser.parse_args()

    if args.queue or args.process:
        result = queue_or_process_his_journey_work(
            actor="his_sync_script",
            use_llm=not args.local_only,
            provider=args.provider,
            model=args.model,
            require_llm=args.require_llm,
            process=args.process,
        )
    else:
        result = scan_his_journey_work(persist_state=True)

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
