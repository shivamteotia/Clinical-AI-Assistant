import json
import os
import time
from time import perf_counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.api.canonical_his import get_canonical_patient_record
from app.api.his import list_patients
from app.rag.config import get_patient_journey_llm_settings
from app.rag.episodes import EPISODE_STRATEGY, build_patient_episodes, compact_episode_timeline
from app.rag.journey_runs import latest_journey_run, write_journey_run
from app.rag.safety import SAFETY_NOTICE

BASE_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BASE_DIR / "data"
JOURNEY_PATH = DATA_DIR / "patient_journeys.json"
DEFAULT_JOURNEY_MODEL = "phi3"
DEFAULT_GROQ_MODEL = "llama-3.3-70b-versatile"
CONTEXT_STRATEGY = "episodic_patient_context.v1"
MAX_CONTEXT_ITEMS = {
    "episodes": 5,
    "encounters": 5,
    "labs": 8,
    "medications": 8,
    "clinical_notes": 5,
}
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
- Return only valid JSON with this shape:
  {"summary":"one paragraph","claims":[{"sentence":"one sentence from the summary","sources":["patient:P001","encounter:E001"]}]}
- Every claim source must use IDs from the supplied record: patient:{patient_id}, episode:{episode_id}, encounter:{encounter_id}, lab:{lab_id}, medication:{medication_id}, note:{note_id}.
""".strip()


@dataclass(frozen=True)
class JourneySummaryResult:
    summary: str | None
    provider: str | None
    model: str | None
    claims: list[dict] | None = None
    error: str | None = None


def get_journey_path() -> Path:
    configured_path = os.getenv("CLINICAL_AI_JOURNEY_PATH")
    if configured_path:
        return Path(configured_path)
    return JOURNEY_PATH

def load_patient_journeys() -> dict[str, dict]:
    journey_path = get_journey_path()
    if not journey_path.exists():
        return {}

    with open(journey_path, "r", encoding="utf-8") as file:
        journeys = json.load(file)

    return {journey["patient_id"]: journey for journey in journeys}


def save_patient_journeys(journeys: list[dict]) -> None:
    journey_path = get_journey_path()
    journey_path.parent.mkdir(parents=True, exist_ok=True)
    with open(journey_path, "w", encoding="utf-8") as file:
        json.dump(journeys, file, indent=2)
        file.write("\n")


def upsert_patient_journey(journey: dict) -> None:
    journeys_by_patient = load_patient_journeys()
    journeys_by_patient[journey["patient_id"]] = journey
    save_patient_journeys(
        sorted(journeys_by_patient.values(), key=lambda item: item["patient_id"])
    )


def get_patient_journey(patient_id: str) -> dict | None:
    record = get_canonical_patient_record(patient_id)
    if record is None:
        return None

    journeys = load_patient_journeys()
    journey = journeys.get(patient_id) or build_patient_journey(record, generated_by="local_fallback")
    return _finalize_journey(journey, record)


def inspect_patient_journey_pipeline(
    patient_id: str,
    provider: str | None = None,
    model: str | None = None,
) -> dict | None:
    record = get_canonical_patient_record(patient_id)
    if record is None:
        return None

    settings = get_patient_journey_llm_settings()
    resolved_provider = (provider or settings.provider).lower()
    resolved_model = model or settings.model
    patient = record["patient"]
    stored_journey = load_patient_journeys().get(patient_id)
    episode_packet = build_patient_episodes(record)
    context_packet = build_patient_journey_context(record)
    formatted_prompt = _format_record_for_llm(record)
    llm_payload = build_journey_llm_payload(record, resolved_provider, resolved_model)
    endpoint_output = _finalize_journey(
        stored_journey or build_patient_journey(record, generated_by="local_fallback"),
        record,
    )

    return {
        "patient_id": patient_id,
        "provider": resolved_provider,
        "model": resolved_model,
        "dry_run": True,
        "stages": [
            _inspection_stage(
                "HIS Patient Row",
                "app.api.his.get_patient",
                {"patient_id": patient_id},
                patient,
                "Single row from the patients table.",
            ),
            _inspection_stage(
                "HIS Full Record",
                "app.api.his.get_patient_record",
                {"patient_id": patient_id},
                record,
                "Structured patient data plus unstructured clinical note text.",
            ),
            _inspection_stage(
                "Episode Builder Output",
                "app.rag.episodes.build_patient_episodes",
                {"record": _shape_of(record)},
                episode_packet,
                "Chronological clinical episodes built from encounters, labs, medications, and notes.",
            ),
            _inspection_stage(
                "System Prompt",
                "app.rag.patient_journey.PATIENT_JOURNEY_SYSTEM_PROMPT",
                None,
                PATIENT_JOURNEY_SYSTEM_PROMPT,
                "Instruction sent as the LLM system message.",
            ),
            _inspection_stage(
                "Episode-Packed LLM Context",
                "app.rag.patient_journey.build_patient_journey_context",
                {"record": _shape_of(record), "episode_packet": _shape_of(episode_packet)},
                context_packet,
                "Episode-organized clinical packet sent to the journey-generation LLM.",
            ),
            _inspection_stage(
                "Formatted User Prompt",
                "app.rag.patient_journey._format_record_for_llm",
                {"context_packet": _shape_of(context_packet)},
                formatted_prompt,
                "Context packet serialized into the LLM user message.",
            ),
            _inspection_stage(
                "LLM Request Payload",
                "app.rag.patient_journey.build_journey_llm_payload",
                {
                    "provider": resolved_provider,
                    "model": resolved_model,
                    "record": _shape_of(record),
                },
                llm_payload,
                "Dry-run request body only. API keys are not included or returned.",
            ),
            _inspection_stage(
                "Stored Journey JSON",
                "app.rag.patient_journey.load_patient_journeys",
                {"patient_id": patient_id},
                _finalize_journey(stored_journey, record) if stored_journey else {},
                "Precomputed journey currently stored for the doctor page.",
            ),
            _inspection_stage(
                "Doctor UI Endpoint Output",
                f"GET /patients/{patient_id}/journey",
                {"path_patient_id": patient_id},
                endpoint_output,
                "Effective JSON returned to the doctor-facing page.",
            ),
        ],
    }


def generate_and_store_patient_journey(
    patient_id: str,
    use_llm: bool = True,
    model: str | None = None,
    provider: str | None = None,
    require_llm: bool = False,
    trigger: str = "generation",
    refresh_id: str | None = None,
) -> dict | None:
    record = get_canonical_patient_record(patient_id)
    if record is None:
        return None

    started = perf_counter()
    context_packet = build_patient_journey_context(record)
    resolved_provider, resolved_model = _resolved_run_provider_model(use_llm, provider, model)
    try:
        journey = build_patient_journey(
            record,
            use_llm=use_llm,
            model=model,
            provider=provider,
            require_llm=require_llm,
        )
    except Exception as error:
        _write_generation_run(
            record,
            context_packet,
            started,
            status="failed",
            provider=resolved_provider,
            model=resolved_model,
            use_llm=use_llm,
            require_llm=require_llm,
            trigger=trigger,
            refresh_id=refresh_id,
            error=error,
        )
        raise

    run = _write_generation_run(
        record,
        context_packet,
        started,
        status="completed",
        provider=resolved_provider,
        model=resolved_model,
        use_llm=use_llm,
        require_llm=require_llm,
        trigger=trigger,
        refresh_id=refresh_id,
        generated_by=journey.get("generated_by"),
    )
    journey["latest_run"] = run
    upsert_patient_journey(journey)
    return journey


def build_all_patient_journeys(
    use_llm: bool = False,
    model: str | None = None,
    provider: str | None = None,
    require_llm: bool = False,
    request_delay_seconds: float = 0.0,
) -> list[dict]:
    journeys = []
    patients = list_patients()
    for index, patient in enumerate(patients):
        record = get_canonical_patient_record(patient["patient_id"])
        if record is None:
            continue
        started = perf_counter()
        context_packet = build_patient_journey_context(record)
        resolved_provider, resolved_model = _resolved_run_provider_model(use_llm, provider, model)
        try:
            journey = build_patient_journey(
                record,
                use_llm=use_llm,
                model=model,
                provider=provider,
                require_llm=require_llm,
            )
        except Exception as error:
            _write_generation_run(
                record,
                context_packet,
                started,
                status="failed",
                provider=resolved_provider,
                model=resolved_model,
                use_llm=use_llm,
                require_llm=require_llm,
                trigger="batch_generation",
                error=error,
            )
            raise
        journey["latest_run"] = _write_generation_run(
            record,
            context_packet,
            started,
            status="completed",
            provider=resolved_provider,
            model=resolved_model,
            use_llm=use_llm,
            require_llm=require_llm,
            trigger="batch_generation",
            generated_by=journey.get("generated_by"),
        )
        journeys.append(journey)
        if use_llm and request_delay_seconds > 0 and index < len(patients) - 1:
            time.sleep(request_delay_seconds)
    return journeys


def build_patient_journey(
    record: dict,
    use_llm: bool = False,
    generated_by: str = "local_fallback",
    model: str | None = None,
    provider: str | None = None,
    require_llm: bool = False,
) -> dict:
    llm_error = None
    claims = None
    if use_llm:
        llm_result = _try_llm_summary(record, model=model, provider=provider)
        if llm_result.summary:
            llm_summary = llm_result.summary
            claims = llm_result.claims
            generated_by = f"{llm_result.provider}:{llm_result.model}"
            model = llm_result.model
        else:
            llm_error = llm_result.error
            if require_llm:
                raise RuntimeError(llm_error or "LLM patient journey generation failed.")
            llm_summary = _fallback_summary(record)
    else:
        llm_summary = _fallback_summary(record)

    patient = record["patient"]
    latest_encounter = record["encounters"][0] if record["encounters"] else None
    source_metadata = record.get("record_metadata", {})
    generated_at = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return {
        "patient_id": patient["patient_id"],
        "patient_name": patient["name"],
        "generated_at": generated_at,
        "generated_by": generated_by,
        "journey_model": model if generated_by != "local_fallback" else None,
        "system_prompt": PATIENT_JOURNEY_SYSTEM_PROMPT if generated_by != "local_fallback" else None,
        "llm_error": llm_error,
        "summary": llm_summary,
        "claims": _normalize_claims(claims, record, llm_summary),
        "context_strategy": CONTEXT_STRATEGY,
        "context_metadata": build_patient_journey_context(record)["context_metadata"],
        "source_system": source_metadata.get("source_system"),
        "source_record_id": source_metadata.get("source_record_id"),
        "source_record_hash": source_metadata.get("record_hash"),
        "source_record_version": source_metadata.get("record_version"),
        "source_record_updated_at": source_metadata.get("last_updated"),
        "current_source_record_hash": source_metadata.get("record_hash"),
        "current_source_record_version": source_metadata.get("record_version"),
        "is_stale": False,
        "timeline": _timeline(record),
        "current_focus": _current_focus(latest_encounter),
        "key_labs": _key_labs(record),
        "active_medications": _active_medications(record),
        "safety_notice": SAFETY_NOTICE,
    }


def _resolved_run_provider_model(use_llm: bool, provider: str | None, model: str | None) -> tuple[str, str | None]:
    if not use_llm:
        return "local", None
    settings = get_patient_journey_llm_settings()
    return (provider or settings.provider).lower(), model or settings.model


def _write_generation_run(
    record: dict,
    context_packet: dict,
    started: float,
    *,
    status: str,
    provider: str | None,
    model: str | None,
    use_llm: bool,
    require_llm: bool,
    trigger: str,
    refresh_id: str | None = None,
    generated_by: str | None = None,
    error: Exception | None = None,
) -> dict:
    metadata = record.get("record_metadata", {})
    context_metadata = context_packet.get("context_metadata", {})
    return write_journey_run(
        patient_id=record["patient"]["patient_id"],
        status=status,
        provider=provider,
        model=model,
        use_llm=use_llm,
        require_llm=require_llm,
        context_strategy=context_packet.get("context_strategy"),
        source_record_version=metadata.get("record_version"),
        input_char_count=context_metadata.get("input_char_count"),
        estimated_input_tokens=context_metadata.get("estimated_input_tokens"),
        duration_ms=max(0, int((perf_counter() - started) * 1000)),
        generated_by=generated_by,
        trigger=trigger,
        refresh_id=refresh_id,
        error_type=error.__class__.__name__ if error else None,
        error=str(error) if error else None,
    )

def _try_llm_summary(
    record: dict,
    model: str | None = None,
    provider: str | None = None,
) -> JourneySummaryResult:
    settings = get_patient_journey_llm_settings()
    resolved_provider = (provider or settings.provider).lower()
    resolved_model = model or settings.model

    if resolved_provider == "groq":
        return _try_groq_summary(record, resolved_model, settings.groq_api_key, settings.groq_base_url)
    if resolved_provider == "ollama":
        return _try_ollama_summary(record, resolved_model)

    return JourneySummaryResult(
        summary=None,
        provider=resolved_provider,
        model=resolved_model,
        error=f"Unsupported patient journey LLM provider: {resolved_provider}",
    )


def _try_ollama_summary(record: dict, model: str) -> JourneySummaryResult:
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
        parsed = _parse_llm_journey_content(response["message"]["content"])
        return JourneySummaryResult(
            summary=parsed["summary"],
            provider="ollama",
            model=model,
            claims=parsed["claims"],
        )
    except Exception as error:
        return JourneySummaryResult(
            summary=None,
            provider="ollama",
            model=model,
            error=f"Ollama generation failed: {error.__class__.__name__}",
        )


def _try_groq_summary(
    record: dict,
    model: str,
    api_key: str | None,
    base_url: str,
) -> JourneySummaryResult:
    if not api_key:
        return JourneySummaryResult(
            summary=None,
            provider="groq",
            model=model,
            error="GROQ_API_KEY is required for Groq patient journey generation.",
        )

    payload = build_groq_journey_payload(record, model)
    request = Request(
        base_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "ClinicalAISystem/0.1",
        },
        method="POST",
    )

    for attempt in range(3):
        try:
            with urlopen(request, timeout=60) as response:
                data = json.loads(response.read().decode("utf-8"))
            parsed = _parse_llm_journey_content(data["choices"][0]["message"]["content"])
            return JourneySummaryResult(
                summary=parsed["summary"],
                provider="groq",
                model=model,
                claims=parsed["claims"],
            )
        except HTTPError as error:
            if error.code == 429 and attempt < 2:
                retry_after = error.headers.get("Retry-After")
                wait_seconds = float(retry_after) if retry_after else 10.0
                time.sleep(wait_seconds)
                continue
            return JourneySummaryResult(
                summary=None,
                provider="groq",
                model=model,
                error=f"Groq generation failed: HTTP {error.code}",
            )
        except (KeyError, IndexError, URLError, TimeoutError, OSError) as error:
            return JourneySummaryResult(
                summary=None,
                provider="groq",
                model=model,
                error=f"Groq generation failed: {error.__class__.__name__}",
            )

    return JourneySummaryResult(
        summary=None,
        provider="groq",
        model=model,
        error="Groq generation failed after retries.",
    )


def build_groq_journey_payload(record: dict, model: str) -> dict:
    return {
        "model": model,
        "messages": [
            {"role": "system", "content": PATIENT_JOURNEY_SYSTEM_PROMPT},
            {"role": "user", "content": _format_record_for_llm(record)},
        ],
        "temperature": 0.2,
        "max_tokens": 550,
    }


def build_journey_llm_payload(record: dict, provider: str, model: str) -> dict:
    if provider == "groq":
        return build_groq_journey_payload(record, model)

    return {
        "model": model,
        "messages": [
            {"role": "system", "content": PATIENT_JOURNEY_SYSTEM_PROMPT},
            {"role": "user", "content": _format_record_for_llm(record)},
        ],
    }


def _inspection_stage(
    title: str,
    source: str,
    input_value,
    output_value,
    note: str,
) -> dict:
    return {
        "title": title,
        "source": source,
        "input": input_value,
        "note": note,
        "output_type": type(output_value).__name__,
        "output_shape": _shape_of(output_value),
        "data": output_value,
    }


def _shape_of(value) -> str:
    if isinstance(value, dict):
        parts = []
        for key, item in value.items():
            if isinstance(item, list):
                item_shape = f"list[{len(item)}]"
                if item and isinstance(item[0], dict):
                    item_shape += f" of dict keys {list(item[0].keys())}"
            elif isinstance(item, dict):
                item_shape = f"dict keys {list(item.keys())}"
            else:
                item_shape = type(item).__name__
            parts.append(f"{key}: {item_shape}")
        return "; ".join(parts)
    if isinstance(value, list):
        if not value:
            return "list[0]"
        return f"list[{len(value)}] item_type={type(value[0]).__name__}"
    if isinstance(value, str):
        return f"str length={len(value)}"
    return type(value).__name__


def build_patient_journey_context(record: dict) -> dict:
    episode_packet = build_patient_episodes(record)
    packet = {
        "context_strategy": CONTEXT_STRATEGY,
        "episode_strategy": EPISODE_STRATEGY,
        "patient": record["patient"],
        "record_metadata": record.get("record_metadata", {}),
        "episodes": _limit_context_items(episode_packet["episodes"], "episodes"),
        "episode_timeline": compact_episode_timeline(record),
    }
    packet["context_metadata"] = _context_metadata(record, packet, episode_packet)
    return packet


def _limit_context_items(items: list[dict], section: str) -> list[dict]:
    return items[:MAX_CONTEXT_ITEMS[section]]


def _context_metadata(record: dict, packet: dict, episode_packet: dict) -> dict:
    included_counts = {
        "episodes": len(packet["episodes"]),
        "encounters": sum(len(episode["encounters"]) for episode in packet["episodes"]),
        "labs": sum(len(episode["labs"]) for episode in packet["episodes"]),
        "medications": sum(len(episode["medications"]) for episode in packet["episodes"]),
        "clinical_notes": sum(len(episode["clinical_notes"]) for episode in packet["episodes"]),
    }
    total_counts = {
        "episodes": episode_packet["episode_count"],
        "encounters": len(record.get("encounters", [])),
        "labs": len(record.get("labs", [])),
        "medications": len(record.get("medications", [])),
        "clinical_notes": len(record.get("clinical_notes", [])),
    }
    omitted_counts = {
        section: max(total_counts[section] - included_counts[section], 0)
        for section in total_counts
    }
    payload_without_metadata = {key: value for key, value in packet.items() if key != "context_metadata"}
    serialized = json.dumps(payload_without_metadata, ensure_ascii=True, indent=2)
    return {
        "included_counts": included_counts,
        "total_counts": total_counts,
        "omitted_counts": omitted_counts,
        "input_char_count": len(serialized),
        "estimated_input_tokens": estimate_tokens(serialized),
        "reserved_output_tokens": 550,
    }


def estimate_tokens(text: str) -> int:
    return max(1, (len(text) + 3) // 4)


def _format_record_for_llm(record: dict) -> str:
    context_packet = build_patient_journey_context(record)
    return "\n".join(
        [
            "Patient journey context packet JSON:",
            json.dumps(context_packet, ensure_ascii=True, indent=2),
        ]
    )


def _parse_llm_journey_content(content: str) -> dict:
    text = content.strip()
    try:
        parsed = json.loads(_extract_json_object(text))
    except json.JSONDecodeError:
        return {"summary": text, "claims": None}

    if not isinstance(parsed, dict):
        return {"summary": text, "claims": None}

    summary = parsed.get("summary")
    claims = parsed.get("claims")
    return {
        "summary": summary.strip() if isinstance(summary, str) and summary.strip() else text,
        "claims": claims if isinstance(claims, list) else None,
    }


def _extract_json_object(text: str) -> str:
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start:end + 1]
    return text


def _finalize_journey(journey: dict | None, record: dict) -> dict | None:
    grounded = _with_grounded_claims(journey, record)
    if grounded is None:
        return None
    fresh = _with_record_freshness(grounded, record)
    fresh["latest_run"] = latest_journey_run(record["patient"]["patient_id"])
    return fresh


def _with_record_freshness(journey: dict, record: dict) -> dict:
    metadata = record.get("record_metadata", {})
    current_hash = metadata.get("record_hash")
    current_version = metadata.get("record_version")
    source_hash = journey.get("source_record_hash")
    augmented = dict(journey)
    augmented.setdefault("source_system", metadata.get("source_system"))
    augmented.setdefault("source_record_id", metadata.get("source_record_id"))
    augmented.setdefault("source_record_updated_at", metadata.get("last_updated"))
    augmented["current_source_record_hash"] = current_hash
    augmented["current_source_record_version"] = current_version
    augmented["is_stale"] = source_hash != current_hash
    return augmented


def _with_grounded_claims(journey: dict | None, record: dict) -> dict | None:
    if journey is None:
        return None

    if journey.get("claims"):
        return journey

    augmented = dict(journey)
    augmented["claims"] = _claims_for_summary(record, augmented.get("summary", ""))
    return augmented


def _normalize_claims(claims: list[dict] | None, record: dict, summary: str) -> list[dict]:
    allowed_sources = _source_catalog(record)
    normalized = []
    for claim in claims or []:
        if not isinstance(claim, dict):
            continue
        sentence = claim.get("sentence")
        if not isinstance(sentence, str) or not sentence.strip():
            continue
        sources = [
            source
            for source in claim.get("sources", [])
            if isinstance(source, str) and source in allowed_sources
        ]
        if sources:
            normalized.append({
                "sentence": sentence.strip(),
                "sources": sources,
            })

    return normalized or _claims_for_summary(record, summary)


def _claims_for_summary(record: dict, summary: str) -> list[dict]:
    sentences = _split_sentences(summary)
    return [
        {
            "sentence": sentence,
            "sources": _infer_sources_for_sentence(record, sentence),
        }
        for sentence in sentences
    ]


def _split_sentences(text: str) -> list[str]:
    cleaned = " ".join((text or "").split())
    if not cleaned:
        return []

    sentences = []
    start = 0
    for index, character in enumerate(cleaned):
        if character not in ".!?":
            continue
        if index + 1 < len(cleaned) and not cleaned[index + 1].isspace():
            continue
        sentence = cleaned[start:index + 1].strip()
        if sentence:
            sentences.append(sentence)
        start = index + 1

    remainder = cleaned[start:].strip()
    if remainder:
        sentences.append(remainder)
    return sentences


def _infer_sources_for_sentence(record: dict, sentence: str) -> list[str]:
    text = sentence.lower()
    sources = []
    patient = record["patient"]

    if (
        patient["patient_id"].lower() in text
        or patient["name"].lower() in text
        or str(patient["age"]) in text
        or patient["gender"].lower() in text
    ):
        sources.append(f"patient:{patient['patient_id']}")

    for encounter in record["encounters"]:
        if (
            encounter["encounter_id"].lower() in text
            or encounter["diagnosis"].lower() in text
            or encounter["chief_complaint"].lower() in text
            or encounter["date"].lower() in text
        ):
            sources.append(f"encounter:{encounter['encounter_id']}")

    for lab in record["labs"]:
        if lab["lab_id"].lower() in text or lab["test_name"].lower() in text or lab["value"].lower() in text:
            sources.append(f"lab:{lab['lab_id']}")

    for medication in record["medications"]:
        if (
            medication["medication_id"].lower() in text
            or medication["drug_name"].lower() in text
            or medication["dose"].lower() in text
        ):
            sources.append(f"medication:{medication['medication_id']}")

    for note in record["clinical_notes"]:
        note_terms = [
            note["note_id"].lower(),
            note["date"].lower(),
            note["note_type"].lower(),
            "progress note",
            "symptom",
            "symptoms",
            "follow-up",
            "synthetic",
            "dummy",
        ]
        if any(term in text for term in note_terms):
            sources.append(f"note:{note['note_id']}")

    return list(dict.fromkeys(sources)) or [f"patient:{patient['patient_id']}"]


def _source_catalog(record: dict) -> set[str]:
    sources = {f"patient:{record['patient']['patient_id']}"}
    sources.update(f"episode:{episode['episode_id']}" for episode in build_patient_episodes(record)["episodes"])
    sources.update(f"encounter:{row['encounter_id']}" for row in record["encounters"])
    sources.update(f"lab:{row['lab_id']}" for row in record["labs"])
    sources.update(f"medication:{row['medication_id']}" for row in record["medications"])
    sources.update(f"note:{row['note_id']}" for row in record["clinical_notes"])
    return sources


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

