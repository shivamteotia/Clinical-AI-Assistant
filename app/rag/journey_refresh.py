from __future__ import annotations

import json
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
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with QUEUE_PATH.open("a", encoding="utf-8") as file:
        file.write(json.dumps(event, sort_keys=True) + "\n")
    return event


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
