from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.api.canonical_his import get_canonical_patient_record
from app.api.his import list_patients
from app.audit import write_audit_event
from app.rag.patient_journey import generate_and_store_patient_journey, get_patient_journey

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
QUEUE_PATH = DATA_DIR / "journey_refresh_queue.jsonl"


def get_refresh_queue_path() -> Path:
    configured_path = os.getenv("CLINICAL_AI_JOURNEY_REFRESH_QUEUE_PATH")
    if configured_path:
        return Path(configured_path)
    return QUEUE_PATH

def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def append_refresh_queue_event(
    patient_id: str,
    *,
    actor: str = "system",
    status: str = "queued",
    reason: str = "manual",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    event = {
        "refresh_id": uuid4().hex,
        "patient_id": patient_id,
        "status": status,
        "reason": reason,
        "actor": actor,
        "created_at": utc_now(),
        "metadata": metadata or {},
    }
    queue_path = get_refresh_queue_path()
    queue_path.parent.mkdir(parents=True, exist_ok=True)
    with queue_path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(event, sort_keys=True) + "\n")
    return event


def read_refresh_queue_events(limit: int = 500) -> list[dict[str, Any]]:
    bounded_limit = max(1, min(limit, 1000))
    queue_path = get_refresh_queue_path()
    if not queue_path.exists():
        return []

    events: list[dict[str, Any]] = []
    for line in reversed(queue_path.read_text(encoding="utf-8").splitlines()):
        if not line.strip():
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
        if len(events) >= bounded_limit:
            break
    return events


def list_pending_journey_refreshes(limit: int = 100) -> list[dict[str, Any]]:
    events = read_refresh_queue_events(limit=1000)
    terminal_refresh_ids = {
        event.get("metadata", {}).get("refresh_id")
        for event in events
        if event.get("status") in {"completed", "failed"}
    }
    pending: list[dict[str, Any]] = []
    seen_refresh_ids: set[str] = set()
    for event in reversed(events):
        refresh_id = event.get("refresh_id")
        if event.get("status") != "queued" or not refresh_id:
            continue
        if refresh_id in terminal_refresh_ids or refresh_id in seen_refresh_ids:
            continue
        pending.append(event)
        seen_refresh_ids.add(refresh_id)
        if len(pending) >= limit:
            break
    return pending


def process_pending_journey_refreshes(
    *,
    actor: str = "system",
    use_llm: bool = True,
    provider: str | None = None,
    model: str | None = None,
    require_llm: bool = False,
    limit: int = 10,
) -> dict[str, Any]:
    pending = list_pending_journey_refreshes(limit=limit)
    processed = []
    failed = []
    for event in pending:
        patient_id = event.get("patient_id")
        if not patient_id:
            continue
        metadata = event.get("metadata", {})
        try:
            result = refresh_patient_journey(
                patient_id,
                actor=actor,
                use_llm=metadata.get("use_llm", use_llm),
                provider=metadata.get("provider") or provider,
                model=metadata.get("model") or model,
                require_llm=metadata.get("require_llm", require_llm),
                reason=event.get("reason") or "queued_refresh",
                queued_event=event,
            )
            if result:
                processed.append({
                    "patient_id": patient_id,
                    "refresh_id": result.get("refresh_id"),
                    "generated_by": result.get("journey", {}).get("generated_by"),
                    "source_record_version": result.get("journey", {}).get("source_record_version"),
                })
        except Exception as error:
            failed.append({
                "patient_id": patient_id,
                "refresh_id": event.get("refresh_id"),
                "error_type": error.__class__.__name__,
                "error": str(error),
            })

    write_audit_event(
        "journey_refresh_queue_processed",
        actor=actor,
        metadata={
            "pending_count": len(pending),
            "processed_count": len(processed),
            "failed_count": len(failed),
            "limit": limit,
        },
    )
    return {
        "status": "completed",
        "pending_count": len(pending),
        "processed_count": len(processed),
        "failed_count": len(failed),
        "processed": processed,
        "failed": failed,
    }

def list_stale_patient_journeys() -> list[dict[str, Any]]:
    stale = []
    for patient in list_patients():
        patient_id = patient["patient_id"]
        journey = get_patient_journey(patient_id)
        if not journey or not journey.get("is_stale"):
            continue
        stale.append({
            "patient_id": patient_id,
            "patient_name": journey.get("patient_name") or patient.get("name"),
            "source_record_version": journey.get("source_record_version"),
            "current_source_record_version": journey.get("current_source_record_version"),
            "generated_at": journey.get("generated_at"),
            "generated_by": journey.get("generated_by"),
        })
    return stale


def queue_patient_journey_refresh(
    patient_id: str,
    *,
    actor: str = "system",
    reason: str = "manual",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    if get_canonical_patient_record(patient_id) is None:
        return None
    event = append_refresh_queue_event(
        patient_id,
        actor=actor,
        status="queued",
        reason=reason,
        metadata=metadata,
    )
    write_audit_event(
        "patient_journey_refresh_requested",
        actor=actor,
        patient_id=patient_id,
        metadata={"refresh_id": event["refresh_id"], "reason": reason, **(metadata or {})},
    )
    return event


def refresh_patient_journey(
    patient_id: str,
    *,
    actor: str = "system",
    use_llm: bool = True,
    provider: str | None = None,
    model: str | None = None,
    require_llm: bool = False,
    reason: str = "manual",
    queued_event: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    queued = queued_event or queue_patient_journey_refresh(
        patient_id,
        actor=actor,
        reason=reason,
        metadata={
            "use_llm": use_llm,
            "provider": provider,
            "model": model,
            "require_llm": require_llm,
        },
    )
    if queued is None:
        return None

    try:
        journey = generate_and_store_patient_journey(
            patient_id,
            use_llm=use_llm,
            provider=provider,
            model=model,
            require_llm=require_llm,
            trigger="refresh",
            refresh_id=queued["refresh_id"],
        )
    except Exception as error:
        failure = append_refresh_queue_event(
            patient_id,
            actor=actor,
            status="failed",
            reason=reason,
            metadata={
                "refresh_id": queued["refresh_id"],
                "error_type": error.__class__.__name__,
                "error": str(error),
            },
        )
        write_audit_event(
            "patient_journey_refresh_failed",
            actor=actor,
            patient_id=patient_id,
            metadata=failure["metadata"],
        )
        raise

    completed = append_refresh_queue_event(
        patient_id,
        actor=actor,
        status="completed",
        reason=reason,
        metadata={
            "refresh_id": queued["refresh_id"],
            "generated_by": journey.get("generated_by") if journey else None,
            "journey_model": journey.get("journey_model") if journey else None,
            "source_record_version": journey.get("source_record_version") if journey else None,
            "context_strategy": journey.get("context_strategy") if journey else None,
            "run_id": journey.get("latest_run", {}).get("run_id") if journey else None,
        },
    )
    write_audit_event(
        "patient_journey_refresh_completed",
        actor=actor,
        patient_id=patient_id,
        metadata=completed["metadata"],
    )
    return {
        "status": "completed",
        "refresh_id": queued["refresh_id"],
        "patient_id": patient_id,
        "journey": journey,
    }


def refresh_stale_patient_journeys(
    *,
    actor: str = "system",
    use_llm: bool = True,
    provider: str | None = None,
    model: str | None = None,
    require_llm: bool = False,
) -> dict[str, Any]:
    stale = list_stale_patient_journeys()
    refreshed = []
    failed = []
    for item in stale:
        patient_id = item["patient_id"]
        try:
            result = refresh_patient_journey(
                patient_id,
                actor=actor,
                use_llm=use_llm,
                provider=provider,
                model=model,
                require_llm=require_llm,
                reason="stale_record_hash",
            )
            if result:
                refreshed.append({
                    "patient_id": patient_id,
                    "refresh_id": result["refresh_id"],
                    "generated_by": result["journey"].get("generated_by"),
                    "source_record_version": result["journey"].get("source_record_version"),
                })
        except Exception as error:
            failed.append({
                "patient_id": patient_id,
                "error_type": error.__class__.__name__,
                "error": str(error),
            })

    return {
        "stale_count": len(stale),
        "refreshed_count": len(refreshed),
        "failed_count": len(failed),
        "refreshed": refreshed,
        "failed": failed,
    }
