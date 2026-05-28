import hashlib
import json
from datetime import UTC, datetime

from app.api.his import get_patient_record

SOURCE_SYSTEM = "dummy_his"
CANONICAL_SCHEMA_VERSION = "canonical_patient_record.v1"


def get_canonical_patient_record(patient_id: str) -> dict | None:
    record = get_patient_record(patient_id)
    if record is None:
        return None

    record_hash = hash_patient_record(record)
    metadata = {
        "schema_version": CANONICAL_SCHEMA_VERSION,
        "source_system": SOURCE_SYSTEM,
        "source_record_id": patient_id,
        "record_hash": record_hash,
        "record_version": record_hash[:12],
        "last_updated": latest_record_date(record),
        "canonicalized_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    }
    return {
        **record,
        "record_metadata": metadata,
    }


def hash_patient_record(record: dict) -> str:
    canonical_payload = {
        "patient": record.get("patient", {}),
        "encounters": sorted(record.get("encounters", []), key=lambda row: row.get("encounter_id", "")),
        "labs": sorted(record.get("labs", []), key=lambda row: row.get("lab_id", "")),
        "medications": sorted(record.get("medications", []), key=lambda row: row.get("medication_id", "")),
        "clinical_notes": sorted(record.get("clinical_notes", []), key=lambda row: row.get("note_id", "")),
    }
    encoded = json.dumps(canonical_payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def latest_record_date(record: dict) -> str | None:
    dates = []
    for section in ("encounters", "labs", "clinical_notes"):
        dates.extend(row.get("date") for row in record.get(section, []) if row.get("date"))
    dates.extend(row.get("start_date") for row in record.get("medications", []) if row.get("start_date"))
    return max(dates) if dates else None