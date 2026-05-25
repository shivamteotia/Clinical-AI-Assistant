import json
from pathlib import Path

from app.api.his import get_patient_record, list_patients
from app.rag.safety import SAFETY_NOTICE

BASE_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BASE_DIR / "data"
JOURNEY_PATH = DATA_DIR / "patient_journeys.json"
DEFAULT_JOURNEY_MODEL = "phi3"
PATIENT_JOURNEY_SYSTEM_PROMPT = """
You are a clinical documentation assistant inside a prototype clinical AI system.

Task:
Create a concise patient journey summary for a doctor reviewing a synthetic local HIS record.

Rules:
- Use only the supplied patient record.
- Do not diagnose beyond diagnoses already present in the record.
- Do not recommend treatment, medication changes, triage, or follow-up actions.
- Do not invent missing dates, labs, medications, symptoms, or outcomes.
- Mention that this is dummy/synthetic data only when clinically relevant.
- Write in 1 short paragraph, suitable for a doctor-facing patient overview.
- Focus on chronology, presenting complaint, recorded diagnosis, key labs, medications, and note context.
""".strip()


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


def upsert_patient_journey(journey: dict) -> None:
    journeys_by_patient = load_patient_journeys()
    journeys_by_patient[journey["patient_id"]] = journey
    save_patient_journeys(
        sorted(journeys_by_patient.values(), key=lambda item: item["patient_id"])
    )


def get_patient_journey(patient_id: str) -> dict | None:
    record = get_patient_record(patient_id)
    if record is None:
        return None

    journeys = load_patient_journeys()
    return journeys.get(patient_id) or build_patient_journey(record, generated_by="local_fallback")


def generate_and_store_patient_journey(
    patient_id: str,
    use_llm: bool = True,
    model: str = DEFAULT_JOURNEY_MODEL,
) -> dict | None:
    record = get_patient_record(patient_id)
    if record is None:
        return None

    journey = build_patient_journey(record, use_llm=use_llm, model=model)
    upsert_patient_journey(journey)
    return journey


def build_all_patient_journeys(
    use_llm: bool = False,
    model: str = DEFAULT_JOURNEY_MODEL,
) -> list[dict]:
    journeys = []
    for patient in list_patients():
        record = get_patient_record(patient["patient_id"])
        if record is None:
            continue
        journeys.append(build_patient_journey(record, use_llm=use_llm, model=model))
    return journeys


def build_patient_journey(
    record: dict,
    use_llm: bool = False,
    generated_by: str = "local_fallback",
    model: str = DEFAULT_JOURNEY_MODEL,
) -> dict:
    if use_llm:
        llm_summary = _try_llm_summary(record, model)
        if llm_summary:
            generated_by = f"ollama:{model}"
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
        "journey_model": model if generated_by.startswith("ollama") else None,
        "system_prompt": PATIENT_JOURNEY_SYSTEM_PROMPT if generated_by.startswith("ollama") else None,
        "summary": llm_summary,
        "timeline": _timeline(record),
        "current_focus": _current_focus(latest_encounter),
        "key_labs": _key_labs(record),
        "active_medications": _active_medications(record),
        "safety_notice": SAFETY_NOTICE,
    }


def _try_llm_summary(record: dict, model: str) -> str | None:
    try:
        import ollama

        response = ollama.chat(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": PATIENT_JOURNEY_SYSTEM_PROMPT,
                },
                {
                    "role": "user",
                    "content": _format_record_for_llm(record),
                },
            ],
        )
        return response["message"]["content"].strip()
    except Exception:
        return None


def _format_record_for_llm(record: dict) -> str:
    return "\n".join(
        [
            "Patient record JSON:",
            json.dumps(record, ensure_ascii=True, indent=2),
        ]
    )


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
