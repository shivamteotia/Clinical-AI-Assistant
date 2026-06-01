from __future__ import annotations

from datetime import date, datetime
from typing import Any

EPISODE_STRATEGY = "encounter_date_episodes.v1"


def build_patient_episodes(record: dict[str, Any]) -> dict[str, Any]:
    patient = record.get("patient", {})
    patient_id = patient.get("patient_id", "UNKNOWN")
    dated_items = _collect_dated_items(record)
    encounter_dates = {item["date"] for item in dated_items if item["section"] == "encounters"}
    all_dates = sorted({item["date"] for item in dated_items})

    episode_dates = sorted(encounter_dates or all_dates)
    episodes = []
    for index, episode_date in enumerate(episode_dates, start=1):
        episode_items = [item for item in dated_items if item["date"] == episode_date]
        episode = _build_episode(patient_id, index, episode_date, episode_items)
        episodes.append(episode)

    covered_dates = {episode["date_range"]["start"] for episode in episodes}
    orphan_dates = [item_date for item_date in all_dates if item_date not in covered_dates]
    for orphan_date in orphan_dates:
        episode_items = [item for item in dated_items if item["date"] == orphan_date]
        episodes.append(_build_episode(patient_id, len(episodes) + 1, orphan_date, episode_items))

    episodes = sorted(episodes, key=lambda item: item["date_range"]["start"])
    for index, episode in enumerate(episodes, start=1):
        episode["episode_id"] = f"{patient_id}-E{index:02d}"
    for index, episode in enumerate(episodes):
        previous = episodes[index - 1] if index > 0 else None
        episode["transition_from_previous"] = _transition_text(previous, episode)

    return {
        "episode_strategy": EPISODE_STRATEGY,
        "patient_id": patient_id,
        "episode_count": len(episodes),
        "episodes": episodes,
    }


def compact_episode_timeline(record: dict[str, Any]) -> list[dict[str, Any]]:
    packet = build_patient_episodes(record)
    compact = []
    for episode in packet["episodes"]:
        compact.append({
            "episode_id": episode["episode_id"],
            "date_range": episode["date_range"],
            "title": episode["title"],
            "diagnoses": episode["diagnoses"],
            "chief_complaints": episode["chief_complaints"],
            "source_ids": episode["source_ids"],
        })
    return compact


def _collect_dated_items(record: dict[str, Any]) -> list[dict[str, Any]]:
    items = []
    for section in ("encounters", "labs", "medications", "clinical_notes"):
        for row in record.get(section, []):
            item_date = _row_date(row)
            if item_date is None:
                continue
            items.append({"section": section, "date": item_date, "row": row})
    return sorted(items, key=lambda item: (item["date"], item["section"]))


def _row_date(row: dict[str, Any]) -> str | None:
    raw_date = row.get("date") or row.get("start_date") or row.get("effective_date")
    if not raw_date:
        return None
    try:
        return date.fromisoformat(str(raw_date)[:10]).isoformat()
    except ValueError:
        return str(raw_date)


def _build_episode(
    patient_id: str,
    index: int,
    episode_date: str,
    episode_items: list[dict[str, Any]],
) -> dict[str, Any]:
    sections = {
        "encounters": [],
        "labs": [],
        "medications": [],
        "clinical_notes": [],
    }
    for item in episode_items:
        sections[item["section"]].append(item["row"])

    diagnoses = _unique_values(sections["encounters"], "diagnosis")
    complaints = _unique_values(sections["encounters"], "chief_complaint")
    visit_types = _unique_values(sections["encounters"], "visit_type")
    lab_names = _unique_values(sections["labs"], "test_name")
    medication_names = _unique_values(sections["medications"], "drug_name")
    title = diagnoses[0] if diagnoses else _fallback_title(sections)

    return {
        "episode_id": f"{patient_id}-E{index:02d}",
        "date_range": {"start": episode_date, "end": episode_date},
        "title": title,
        "visit_types": visit_types,
        "diagnoses": diagnoses,
        "chief_complaints": complaints,
        "lab_tests": lab_names,
        "medication_starts": medication_names,
        "encounters": sections["encounters"],
        "labs": sections["labs"],
        "medications": sections["medications"],
        "clinical_notes": sections["clinical_notes"],
        "source_ids": _source_ids(sections),
        "transition_from_previous": None,
    }


def _fallback_title(sections: dict[str, list[dict[str, Any]]]) -> str:
    if sections["clinical_notes"]:
        return "Clinical note"
    if sections["labs"]:
        return "Lab review"
    if sections["medications"]:
        return "Medication update"
    return "Clinical episode"


def _transition_text(previous: dict[str, Any] | None, current: dict[str, Any]) -> str | None:
    if previous is None:
        return "Initial recorded episode in the available HIS record."
    previous_date = previous["date_range"]["start"]
    current_date = current["date_range"]["start"]
    try:
        days = (datetime.fromisoformat(current_date) - datetime.fromisoformat(previous_date)).days
        return f"Recorded {days} days after {previous['episode_id']}."
    except ValueError:
        return f"Recorded after {previous['episode_id']}."


def _unique_values(rows: list[dict[str, Any]], field: str) -> list[str]:
    values = []
    for row in rows:
        value = row.get(field)
        if value and value not in values:
            values.append(value)
    return values


def _source_ids(sections: dict[str, list[dict[str, Any]]]) -> dict[str, list[str]]:
    return {
        "encounters": [row["encounter_id"] for row in sections["encounters"] if row.get("encounter_id")],
        "labs": [row["lab_id"] for row in sections["labs"] if row.get("lab_id")],
        "medications": [row["medication_id"] for row in sections["medications"] if row.get("medication_id")],
        "clinical_notes": [row["note_id"] for row in sections["clinical_notes"] if row.get("note_id")],
    }
