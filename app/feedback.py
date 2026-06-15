from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FEEDBACK_PATH = PROJECT_ROOT / "data" / "journey_feedback.jsonl"
ALLOWED_FEEDBACK_TYPES = {"useful", "missing_info", "incorrect", "other"}


def feedback_log_path() -> Path:
    override = os.getenv("CLINICAL_AI_JOURNEY_FEEDBACK_PATH")
    if override:
        return Path(override)
    return DEFAULT_FEEDBACK_PATH


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def write_journey_feedback(
    *,
    patient_id: str,
    feedback_type: str,
    actor: str = "local_doctor",
    comment: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_type = feedback_type.strip().lower()
    if normalized_type not in ALLOWED_FEEDBACK_TYPES:
        raise ValueError(f"Unsupported feedback_type: {feedback_type}")

    event = {
        "feedback_id": uuid4().hex,
        "patient_id": patient_id,
        "feedback_type": normalized_type,
        "comment": (comment or "").strip()[:500],
        "actor": actor or "unknown",
        "created_at": utc_now(),
        "metadata": metadata or {},
    }
    path = feedback_log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(event, sort_keys=True) + "\n")
    return event


def read_journey_feedback(limit: int = 100, patient_id: str | None = None) -> list[dict[str, Any]]:
    bounded_limit = max(1, min(limit, 500))
    path = feedback_log_path()
    if not path.exists():
        return []

    rows: list[dict[str, Any]] = []
    for line in reversed(path.read_text(encoding="utf-8").splitlines()):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if patient_id and event.get("patient_id") != patient_id:
            continue
        rows.append(event)
        if len(rows) >= bounded_limit:
            break
    return rows
