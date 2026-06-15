from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.rag.episodes import build_patient_episodes

JOURNEY_SCHEMA_VERSION = "patient_journey.v1"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)


class JourneyClaim(StrictModel):
    sentence: str = Field(min_length=1)
    sources: list[str] = Field(min_length=1)


class LLMJourneyResponse(StrictModel):
    summary: str = Field(min_length=1)
    claims: list[JourneyClaim] = Field(min_length=1)

    @model_validator(mode="after")
    def claims_must_appear_in_summary(self) -> "LLMJourneyResponse":
        normalized_summary = " ".join(self.summary.split())
        missing = [
            claim.sentence
            for claim in self.claims
            if " ".join(claim.sentence.split()) not in normalized_summary
        ]
        if missing:
            raise ValueError("Every claim sentence must appear verbatim in the summary.")
        return self


class JourneyTimelineEvent(StrictModel):
    date: str = Field(min_length=1)
    type: str = Field(min_length=1)
    title: str = Field(min_length=1)
    detail: str = Field(min_length=1)


class JourneyContextCounts(StrictModel):
    episodes: int = Field(ge=0)
    encounters: int = Field(ge=0)
    labs: int = Field(ge=0)
    medications: int = Field(ge=0)
    clinical_notes: int = Field(ge=0)


class JourneyContextMetadata(StrictModel):
    included_counts: JourneyContextCounts
    total_counts: JourneyContextCounts
    omitted_counts: JourneyContextCounts
    input_char_count: int = Field(ge=0)
    estimated_input_tokens: int = Field(ge=0)
    reserved_output_tokens: int = Field(ge=0)

    @model_validator(mode="after")
    def counts_must_reconcile(self) -> "JourneyContextMetadata":
        for section in (
            "episodes",
            "encounters",
            "labs",
            "medications",
            "clinical_notes",
        ):
            included = getattr(self.included_counts, section)
            total = getattr(self.total_counts, section)
            omitted = getattr(self.omitted_counts, section)
            if included > total or omitted != total - included:
                raise ValueError(f"Context counts do not reconcile for {section}.")
        return self


class JourneyRun(StrictModel):
    run_id: str = Field(min_length=1)
    patient_id: str = Field(min_length=1)
    status: Literal["completed", "failed"]
    trigger: str = Field(min_length=1)
    refresh_id: str | None
    provider: str | None
    model: str | None
    use_llm: bool
    require_llm: bool
    context_strategy: str | None
    source_record_version: str | None
    input_char_count: int | None = Field(default=None, ge=0)
    estimated_input_tokens: int | None = Field(default=None, ge=0)
    duration_ms: int = Field(ge=0)
    generated_by: str | None
    error_type: str | None
    error: str | None
    created_at: str = Field(min_length=1)


class PatientJourney(StrictModel):
    journey_schema_version: Literal["patient_journey.v1"] = JOURNEY_SCHEMA_VERSION
    patient_id: str = Field(min_length=1)
    patient_name: str = Field(min_length=1)
    generated_at: str = Field(min_length=1)
    generated_by: str = Field(min_length=1)
    journey_model: str | None
    system_prompt: str | None
    llm_error: str | None
    summary: str = Field(min_length=1)
    claims: list[JourneyClaim] = Field(min_length=1)
    context_strategy: str = Field(min_length=1)
    context_metadata: JourneyContextMetadata
    source_system: str | None
    source_record_id: str | None
    source_record_hash: str | None
    source_record_version: str | None
    source_record_updated_at: str | None
    current_source_record_hash: str | None
    current_source_record_version: str | None
    is_stale: bool
    timeline: list[JourneyTimelineEvent]
    current_focus: str = Field(min_length=1)
    key_labs: list[str]
    active_medications: list[str]
    safety_notice: str = Field(min_length=1)
    latest_run: JourneyRun | None = None

    @model_validator(mode="after")
    def internal_references_must_match(self) -> "PatientJourney":
        if self.source_record_id is not None and self.source_record_id != self.patient_id:
            raise ValueError("source_record_id must match patient_id.")
        if self.latest_run is not None and self.latest_run.patient_id != self.patient_id:
            raise ValueError("latest_run patient_id must match journey patient_id.")
        return self


def validate_llm_journey_response(payload: object, allowed_sources: set[str]) -> dict:
    response = LLMJourneyResponse.model_validate(payload)
    invalid_sources = sorted({
        source
        for claim in response.claims
        for source in claim.sources
        if source not in allowed_sources
    })
    if invalid_sources:
        raise ValueError(f"LLM journey contains unknown source IDs: {', '.join(invalid_sources)}")
    return response.model_dump(mode="json")


def validate_patient_journey(
    payload: dict,
    *,
    record: dict | None = None,
    require_current_source: bool = False,
) -> dict:
    upgraded = dict(payload)
    upgraded.setdefault("journey_schema_version", JOURNEY_SCHEMA_VERSION)
    journey = PatientJourney.model_validate(upgraded)

    if record is not None:
        patient_id = record.get("patient", {}).get("patient_id")
        if journey.patient_id != patient_id:
            raise ValueError(
                f"Journey patient_id {journey.patient_id!r} does not match canonical record {patient_id!r}."
            )

        allowed_sources = source_catalog(record)
        invalid_sources = sorted({
            source
            for claim in journey.claims
            for source in claim.sources
            if source not in allowed_sources
        })
        if invalid_sources:
            raise ValueError(f"Journey contains unknown source IDs: {', '.join(invalid_sources)}")

        if require_current_source:
            metadata = record.get("record_metadata", {})
            expected = {
                "source_record_id": metadata.get("source_record_id"),
                "source_record_hash": metadata.get("record_hash"),
                "source_record_version": metadata.get("record_version"),
            }
            for field, expected_value in expected.items():
                if getattr(journey, field) != expected_value:
                    raise ValueError(
                        f"Journey {field} does not match the current canonical record."
                    )

    return journey.model_dump(mode="json")


def source_catalog(record: dict) -> set[str]:
    patient = record.get("patient", {})
    patient_id = patient.get("patient_id")
    sources = {f"patient:{patient_id}"} if patient_id else set()
    sources.update(
        f"episode:{row['episode_id']}"
        for row in build_patient_episodes(record)["episodes"]
        if row.get("episode_id")
    )
    sources.update(
        f"encounter:{row['encounter_id']}"
        for row in record.get("encounters", [])
        if row.get("encounter_id")
    )
    sources.update(
        f"lab:{row['lab_id']}"
        for row in record.get("labs", [])
        if row.get("lab_id")
    )
    sources.update(
        f"medication:{row['medication_id']}"
        for row in record.get("medications", [])
        if row.get("medication_id")
    )
    sources.update(
        f"note:{row['note_id']}"
        for row in record.get("clinical_notes", [])
        if row.get("note_id")
    )
    return sources
