import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.rag.journey_refresh import list_pending_journey_refreshes, process_pending_journey_refreshes


def main() -> None:
    parser = argparse.ArgumentParser(description="Process queued patient journey refresh work.")
    parser.add_argument("--limit", type=int, default=10, help="Maximum queued items to process.")
    parser.add_argument("--provider", default=None, help="Optional LLM provider override, such as groq or ollama.")
    parser.add_argument("--model", default=None, help="Optional journey model override.")
    parser.add_argument("--require-llm", action="store_true", help="Fail instead of falling back locally if LLM generation fails.")
    parser.add_argument("--local-only", action="store_true", help="Use local fallback generation instead of calling an LLM.")
    parser.add_argument("--dry-run", action="store_true", help="List pending queue items without processing.")
    args = parser.parse_args()

    if args.dry_run:
        result = {"pending": list_pending_journey_refreshes(limit=args.limit)}
    else:
        result = process_pending_journey_refreshes(
            actor="journey_queue_worker",
            use_llm=not args.local_only,
            provider=args.provider,
            model=args.model,
            require_llm=args.require_llm,
            limit=args.limit,
        )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
