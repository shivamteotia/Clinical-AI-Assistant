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
from app.rag.journey_refresh import queue_patient_journey_refresh, refresh_patient_journey
from app.rag.patient_journey import load_patient_journeys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SYNC_STATE_PATH = PROJECT_ROOT / "data" / "his_sync_state.json"


def his_sync_state_path() -> Path:
    override = os.getenv("CLINICAL_AI_HIS_SYNC_STATE_PATH")
    if override:
        return Path(override)
    return DEFAULT_SYNC_STATE_PATH


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_his_sync_state() -> dict[str, Any]:
    path = his_sync_state_path()
    if not path.exists():
        return {"patients": {}, "last_scan_at": None}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"patients": {}, "last_scan_at": None, "parse_error": True}


def save_his_sync_state(state: dict[str, Any]) -> None:
    path = his_sync_state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def scan_his_journey_work(*, persist_state: bool = True) -> dict[str, Any]:
    scan_id = uuid4().hex
    scanned_at = utc_now()
    previous_state = load_his_sync_state()
    previous_patients = previous_state.get("patients", {})
    stored_journeys = load_patient_journeys()
    items: list[dict[str, Any]] = []
    next_patients: dict[str, Any] = {}

    for patient in list_patients():
        patient_id = patient["patient_id"]
        record = get_canonical_patient_record(patient_id)
        if record is None:
            continue
        metadata = record.get("record_metadata", {})
        record_hash = metadata.get("record_hash")
        record_version = metadata.get("record_version")
        stored_journey = stored_journeys.get(patient_id)
        stored_hash = stored_journey.get("source_record_hash") if stored_journey else None
        previous_hash = previous_patients.get(patient_id, {}).get("record_hash")

        change_type = None
        if stored_journey is None:
            change_type = "new_patient"
        elif stored_hash != record_hash:
            change_type = "record_changed"

        item = {
            "patient_id": patient_id,
            "patient_name": patient.get("name"),
            "record_hash": record_hash,
            "record_version": record_version,
            "last_updated": metadata.get("last_updated"),
            "stored_journey_hash": stored_hash,
            "previous_scan_hash": previous_hash,
            "known_to_previous_scan": patient_id in previous_patients,
            "has_stored_journey": stored_journey is not None,
            "change_type": change_type,
            "action_required": change_type is not None,
        }
        items.append(item)
        next_patients[patient_id] = {
            "record_hash": record_hash,
            "record_version": record_version,
            "last_updated": metadata.get("last_updated"),
            "seen_at": scanned_at,
        }

    action_items = [item for item in items if item["action_required"]]
    next_state = {
        "last_scan_at": scanned_at,
        "last_scan_id": scan_id,
        "patient_count": len(items),
        "action_required_count": len(action_items),
        "patients": next_patients,
    }
    if persist_state:
        save_his_sync_state(next_state)

    return {
        "scan_id": scan_id,
        "scanned_at": scanned_at,
        "patient_count": len(items),
        "action_required_count": len(action_items),
        "new_patient_count": len([item for item in action_items if item["change_type"] == "new_patient"]),
        "changed_patient_count": len([item for item in action_items if item["change_type"] == "record_changed"]),
        "last_scan_at": previous_state.get("last_scan_at"),
        "items": action_items,
    }


def queue_or_process_his_journey_work(
    *,
    actor: str = "system",
    use_llm: bool = True,
    provider: str | None = None,
    model: str | None = None,
    require_llm: bool = False,
    process: bool = False,
) -> dict[str, Any]:
    scan = scan_his_journey_work(persist_state=True)
    queued: list[dict[str, Any]] = []
    processed: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []

    for item in scan["items"]:
        patient_id = item["patient_id"]
        reason = "new_his_patient" if item["change_type"] == "new_patient" else "his_record_changed"
        metadata = {
            "scan_id": scan["scan_id"],
            "change_type": item["change_type"],
            "record_version": item.get("record_version"),
            "use_llm": use_llm,
            "provider": provider,
            "model": model,
            "require_llm": require_llm,
        }
        try:
            if process:
                result = refresh_patient_journey(
                    patient_id,
                    actor=actor,
                    use_llm=use_llm,
                    provider=provider,
                    model=model,
                    require_llm=require_llm,
                    reason=reason,
                )
                if result:
                    processed.append({
                        "patient_id": patient_id,
                        "change_type": item["change_type"],
                        "refresh_id": result.get("refresh_id"),
                        "generated_by": result.get("journey", {}).get("generated_by"),
                    })
            else:
                queued_event = queue_patient_journey_refresh(
                    patient_id,
                    actor=actor,
                    reason=reason,
                    metadata=metadata,
                )
                if queued_event:
                    queued.append({
                        "patient_id": patient_id,
                        "change_type": item["change_type"],
                        "refresh_id": queued_event.get("refresh_id"),
                    })
        except Exception as error:
            failed.append({
                "patient_id": patient_id,
                "change_type": item["change_type"],
                "error_type": error.__class__.__name__,
                "error": str(error),
            })

    write_audit_event(
        "his_journey_sync_completed",
        actor=actor,
        metadata={
            "scan_id": scan["scan_id"],
            "patient_count": scan["patient_count"],
            "action_required_count": scan["action_required_count"],
            "queued_count": len(queued),
            "processed_count": len(processed),
            "failed_count": len(failed),
            "process": process,
        },
    )

    return {
        "status": "completed",
        "scan": scan,
        "queued_count": len(queued),
        "processed_count": len(processed),
        "failed_count": len(failed),
        "queued": queued,
        "processed": processed,
        "failed": failed,
    }
