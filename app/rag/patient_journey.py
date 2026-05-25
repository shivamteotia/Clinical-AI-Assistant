import json
from pathlib import Path

from app.api.his import get_patient_record, list_patients
from app.rag.safety import SAFETY_NOTICE

BASE_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BASE_DIR / "data"
JOURNEY_PATH = DATA_DIR / "patient_journeys.json"


def load_patient_journeys() -> dict[str, dict]:
    if not JOURNEY_PATH.exists():
        return {}

    with open(JOURNEY_PATH, "r", encoding="utf-8") as file:
        journeys = json.load(file)

    return {journey["patient_id"]: journey for journey in journeys}


def save_patient_journeys(journeys: list[dict]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(JOURNEY_PATH, "w", encoding="utf-8") as file:
        json.dump(journeys, file, indent=2)
        file.write("\n")


def get_patient_journey(patient_id: str) -> dict | None:
    record = get_patient_record(patient_id)
    if record is None:
        return None

    journeys = load_patient_journeys()
    return journeys.get(patient_id) or build_patient_journey(record, generated_by="local_fallback")


def build_all_patient_journeys(use_llm: bool = False) -> list[dict]:
    journeys = []
    for patient in list_patients():
        record = get_patient_record(patient["patient_id"])
        if record is None:
            continue
        journeys.append(build_patient_journey(record, use_llm=use_llm))
    return journeys


def build_patient_journey(record: dict, use_llm: bool = False, generated_by: str = "local_fallback") -> dict:
    if use_llm:
        llm_summary = _try_llm_summary(record)
        if llm_summary:
            generated_by = "ollama"
        else:
            llm_summary = _fallback_summary(record)
    else:
        llm_summary = _fallback_summary(record)

    patient = record["patient"]
    latest_encounter = record["encounters"][0] if record["encounters"] else None
    return {
        "patient_id": patient["patient_id"],
        "patient_name": patient["name"],
        "generated_by": generated_by,
        "summary": llm_summary,
        "timeline": _timeline(record),
        "current_focus": _current_focus(latest_encounter),
        "key_labs": _key_labs(record),
        "active_medications": _active_medications(record),
        "safety_notice": SAFETY_NOTICE,
    }


def _try_llm_summary(record: dict) -> str | None:
    try:
        import ollama

        response = ollama.chat(
            model="phi3",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Summarize this dummy clinical record as a concise patient journey. "
                        "Do not diagnose, recommend treatment, or add facts not in the record."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(record, ensure_ascii=True),
                },
            ],
        )
        return response["message"]["content"].strip()
    except Exception:
        return None


def _fallback_summary(record: dict) -> str:
    patient = record["patient"]
    encounter = record["encounters"][0] if record["encounters"] else {}
    medication_names = ", ".join(row["drug_name"] for row in record["medications"]) or "no recorded medications"
    lab_names = ", ".join(row["test_name"] for row in record["labs"]) or "no recorded labs"
    note_text = record["clinical_notes"][0]["note_text"] if record["clinical_notes"] else "No note text recorded."

    return (
        f"{patient['name']} ({patient['patient_id']}) is a {patient['age']}-year-old "
        f"{patient['gender'].lower()} patient. The latest recorded encounter lists "
        f"{encounter.get('diagnosis', 'no recorded diagnosis')} after a visit for "
        f"{encounter.get('chief_complaint', 'no recorded complaint')}. Recorded labs include "
        f"{lab_names}. Current recorded medications include {medication_names}. "
        f"Clinical note context: {note_text}"
    )


def _timeline(record: dict) -> list[dict]:
    items = []
    for encounter in record["encounters"][:3]:
        items.append({
            "date": encounter["date"],
            "type": encounter["visit_type"],
            "title": encounter["diagnosis"],
            "detail": encounter["chief_complaint"],
        })
    for note in record["clinical_notes"][:1]:
        items.append({
            "date": note["date"],
            "type": note["note_type"],
            "title": "Clinical note",
            "detail": note["note_text"],
        })
    return sorted(items, key=lambda item: item["date"], reverse=True)


def _current_focus(encounter: dict | None) -> str:
    if not encounter:
        return "No current encounter focus recorded."
    return f"{encounter['diagnosis']} - {encounter['chief_complaint']}"


def _key_labs(record: dict) -> list[str]:
    return [
        f"{row['test_name']}: {row['value']} {row['unit']} (ref {row['reference_range']})"
        for row in record["labs"][:4]
    ]


def _active_medications(record: dict) -> list[str]:
    return [
        f"{row['drug_name']} {row['dose']} {row['frequency']}"
        for row in record["medications"][:4]
    ]
