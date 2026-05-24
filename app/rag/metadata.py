import re

WORD_PATTERN = re.compile(r"[a-zA-Z0-9_]+")


def build_patient_metadata(record: dict) -> dict:
    diagnoses = _unique(row["diagnosis"] for row in record["encounters"])
    lab_tests = _unique(row["test_name"] for row in record["labs"])
    medications = _unique(row["drug_name"] for row in record["medications"])
    note_types = _unique(row["note_type"] for row in record["clinical_notes"])

    return {
        "diagnoses": diagnoses,
        "lab_tests": lab_tests,
        "medications": medications,
        "note_types": note_types,
        "diagnosis_terms": _terms(diagnoses),
        "lab_terms": _terms(lab_tests),
        "medication_terms": _terms(medications),
    }


def enrich_chunk_metadata(chunk_text: str, metadata: dict) -> dict:
    section = infer_source_section(chunk_text)
    chunk_terms = set(WORD_PATTERN.findall(chunk_text.lower()))

    return {
        **metadata,
        "source_section": section,
        "mentioned_diagnoses": _mentioned(metadata.get("diagnoses", []), chunk_terms),
        "mentioned_lab_tests": _mentioned(metadata.get("lab_tests", []), chunk_terms),
        "mentioned_medications": _mentioned(metadata.get("medications", []), chunk_terms),
    }


def infer_source_section(text: str) -> str:
    lower_text = text.lower()
    if "lab results:" in lower_text or "lab_id:" in lower_text:
        return "labs"
    if "medications:" in lower_text or "medication_id:" in lower_text:
        return "medications"
    if "clinical notes:" in lower_text or "note_id:" in lower_text:
        return "clinical_notes"
    if "encounters:" in lower_text or "encounter_id:" in lower_text:
        return "encounters"
    return "patient_summary"


def _unique(values) -> list[str]:
    seen = set()
    results = []
    for value in values:
        normalized = str(value).strip()
        key = normalized.lower()
        if normalized and key not in seen:
            seen.add(key)
            results.append(normalized)
    return results


def _terms(values: list[str]) -> list[str]:
    terms = set()
    for value in values:
        terms.update(word.lower() for word in WORD_PATTERN.findall(value) if len(word) > 2)
    return sorted(terms)


def _mentioned(values: list[str], chunk_terms: set[str]) -> list[str]:
    mentioned = []
    for value in values:
        value_terms = {
            word.lower()
            for word in WORD_PATTERN.findall(value)
            if len(word) > 2
        }
        if value_terms and value_terms.intersection(chunk_terms):
            mentioned.append(value)
    return mentioned
