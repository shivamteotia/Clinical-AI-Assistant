from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_AUDIT_LOG_PATH = PROJECT_ROOT / "data" / "audit_logs.jsonl"
SENSITIVE_KEY_PARTS = (
    "api_key",
    "authorization",
    "secret",
    "token",
    "password",
    "prompt",
    "note_text",
    "page_content",
    "summary",
    "answer",
)


def _audit_log_path() -> Path:
    override = os.getenv("CLINICAL_AI_AUDIT_LOG_PATH")
    if override:
        return Path(override)
    return DEFAULT_AUDIT_LOG_PATH


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _sanitize_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, list):
        return [_sanitize_value(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize_value(item) for item in value]
    if isinstance(value, dict):
        safe: dict[str, Any] = {}
        for raw_key, raw_value in value.items():
            key = str(raw_key)
            lowered = key.lower()
            if any(part in lowered for part in SENSITIVE_KEY_PARTS):
                safe[key] = "[redacted]"
            else:
                safe[key] = _sanitize_value(raw_value)
        return safe
    return str(value)


def write_audit_event(
    event_type: str,
    *,
    actor: str = "local_doctor",
    patient_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    event = {
        "event_id": uuid4().hex,
        "event_type": event_type,
        "timestamp": _utc_now(),
        "actor": actor or "unknown",
        "patient_id": patient_id,
        "metadata": _sanitize_value(metadata or {}),
    }
    path = _audit_log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as audit_file:
        audit_file.write(json.dumps(event, sort_keys=True) + "\n")
    return event


def read_audit_events(limit: int = 100) -> list[dict[str, Any]]:
    bounded_limit = max(1, min(limit, 500))
    path = _audit_log_path()
    if not path.exists():
        return []

    lines = path.read_text(encoding="utf-8").splitlines()
    events: list[dict[str, Any]] = []
    for line in reversed(lines):
        if not line.strip():
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            events.append({
                "event_type": "audit_log_parse_error",
                "timestamp": _utc_now(),
                "actor": "system",
                "patient_id": None,
                "metadata": {"raw_line_length": len(line)},
            })
        if len(events) >= bounded_limit:
            break
    return events
