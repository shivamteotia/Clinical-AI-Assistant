from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RUN_LOG_PATH = PROJECT_ROOT / "data" / "journey_runs.jsonl"


def _run_log_path() -> Path:
    override = os.getenv("CLINICAL_AI_JOURNEY_RUN_LOG_PATH")
    if override:
        return Path(override)
    return DEFAULT_RUN_LOG_PATH


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def write_journey_run(
    *,
    patient_id: str,
    status: str,
    provider: str | None,
    model: str | None,
    use_llm: bool,
    require_llm: bool,
    context_strategy: str | None,
    source_record_version: str | None,
    input_char_count: int | None,
    estimated_input_tokens: int | None,
    duration_ms: int,
    generated_by: str | None = None,
    trigger: str = "generation",
    refresh_id: str | None = None,
    error_type: str | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    event = {
        "run_id": uuid4().hex,
        "patient_id": patient_id,
        "status": status,
        "trigger": trigger,
        "refresh_id": refresh_id,
        "provider": provider,
        "model": model,
        "use_llm": use_llm,
        "require_llm": require_llm,
        "context_strategy": context_strategy,
        "source_record_version": source_record_version,
        "input_char_count": input_char_count,
        "estimated_input_tokens": estimated_input_tokens,
        "duration_ms": duration_ms,
        "generated_by": generated_by,
        "error_type": error_type,
        "error": error,
        "created_at": utc_now(),
    }
    path = _run_log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(event, sort_keys=True) + "\n")
    return event


def read_journey_runs(limit: int = 100, patient_id: str | None = None) -> list[dict[str, Any]]:
    bounded_limit = max(1, min(limit, 500))
    path = _run_log_path()
    if not path.exists():
        return []

    events: list[dict[str, Any]] = []
    for line in reversed(path.read_text(encoding="utf-8").splitlines()):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if patient_id and event.get("patient_id") != patient_id:
            continue
        events.append(event)
        if len(events) >= bounded_limit:
            break
    return events


def latest_journey_run(patient_id: str) -> dict[str, Any] | None:
    runs = read_journey_runs(limit=1, patient_id=patient_id)
    return runs[0] if runs else None
