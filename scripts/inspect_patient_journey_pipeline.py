import argparse
import json
import sys
from dataclasses import asdict, is_dataclass
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

from app.api.canonical_his import get_canonical_patient_record
from app.api.his import get_patient
from app.rag.config import get_patient_journey_llm_settings
from app.rag.patient_journey import (
    PATIENT_JOURNEY_SYSTEM_PROMPT,
    build_journey_llm_payload,
    build_patient_journey_context,
    build_patient_journey,
    get_patient_journey,
    load_patient_journeys,
    _fallback_summary,
    _format_record_for_llm,
    _try_llm_summary,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("patient_id")
    parser.add_argument(
        "--call-llm",
        action="store_true",
        help="Actually call the configured LLM and show the response. Default is dry-run.",
    )
    parser.add_argument(
        "--provider",
        choices=["groq", "ollama"],
        default=None,
        help="Provider to inspect. Defaults to PATIENT_JOURNEY_LLM_PROVIDER.",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Model to inspect. Defaults to PATIENT_JOURNEY_MODEL.",
    )
    args = parser.parse_args()

    patient_id = args.patient_id.upper()
    settings = get_patient_journey_llm_settings()
    provider = args.provider or settings.provider
    model = args.model or settings.model

    patient = get_patient(patient_id)
    if patient is None:
        raise SystemExit(f"Patient not found: {patient_id}")

    record = get_canonical_patient_record(patient_id)
    stored_journeys = load_patient_journeys()
    stored_journey = stored_journeys.get(patient_id)

    print_stage(
        1,
        "HIS Patient Row",
        patient,
        source="app.api.his.get_patient",
        input_value={"patient_id": patient_id},
        note="Loaded by app.api.his.get_patient(patient_id).",
    )
    print_stage(
        2,
        "HIS Full Record",
        record,
        source="app.api.his.get_patient_record",
        input_value={"patient_id": patient_id},
        note="Loaded by app.api.his.get_patient_record(patient_id). Structured and unstructured note text are together here.",
    )
    print_stage(
        3,
        "System Prompt",
        PATIENT_JOURNEY_SYSTEM_PROMPT,
        source="app.rag.patient_journey.PATIENT_JOURNEY_SYSTEM_PROMPT",
        input_value=None,
        note="This is the system instruction sent to the journey-generation LLM.",
    )

    context_packet = build_patient_journey_context(record)
    print_stage(
        4,
        "Packed LLM Context",
        context_packet,
        source="app.rag.patient_journey.build_patient_journey_context",
        input_value={"record": shape_of(record)},
        note="Controlled clinical packet sent to the journey-generation LLM.",
    )

    user_prompt = _format_record_for_llm(record)
    print_stage(
        5,
        "Formatted User Prompt",
        user_prompt,
        source="app.rag.patient_journey._format_record_for_llm",
        input_value={"context_packet": shape_of(context_packet)},
        note="Context packet serialized into the LLM user message.",
    )

    llm_payload = build_llm_payload(provider, model, record)
    print_stage(
        6,
        "LLM Request Payload",
        redact(llm_payload),
        source="scripts.inspect_patient_journey_pipeline.build_llm_payload",
        input_value={"provider": provider, "model": model, "record": shape_of(record)},
        note="This is the request body. API keys are not included in the payload and are never printed.",
    )

    if args.call_llm:
        llm_result = _try_llm_summary(record, model=model, provider=provider)
        print_stage(
            7,
            "LLM Raw Summary Result",
            dataclass_to_dict(llm_result),
            source="app.rag.patient_journey._try_llm_summary",
            input_value={"provider": provider, "model": model, "record": shape_of(record)},
            note="This is the direct output wrapper from the configured LLM provider.",
        )
        generated_journey = build_patient_journey(
            record,
            use_llm=True,
            provider=provider,
            model=model,
            require_llm=False,
        )
    else:
        fallback_summary = _fallback_summary(record)
        print_stage(
            7,
            "LLM Raw Summary Result",
            {
                "dry_run": True,
                "provider": provider,
                "model": model,
                "summary": None,
                "fallback_preview": fallback_summary,
            },
            source="app.rag.patient_journey._try_llm_summary",
            input_value={"provider": provider, "model": model, "record": shape_of(record)},
            note="Dry-run mode does not call the LLM. Pass --call-llm to inspect the real provider output.",
        )
        generated_journey = build_patient_journey(record, use_llm=False)

    print_stage(
        8,
        "Journey Object Built By App",
        generated_journey,
        source="app.rag.patient_journey.build_patient_journey",
        input_value={"record": shape_of(record), "use_llm": bool(args.call_llm)},
        note="This is the app's normalized journey JSON shape before/without persistence.",
    )
    print_stage(
        9,
        "Stored Journey From data/patient_journeys.json",
        stored_journey or {},
        source="app.rag.patient_journey.load_patient_journeys",
        input_value={"patient_id": patient_id},
        note="This is what the doctor page currently renders for the selected patient.",
    )
    print_stage(
        10,
        "Doctor UI Endpoint Output",
        get_patient_journey(patient_id),
        source=f"GET /patients/{patient_id}/journey",
        input_value={"path_patient_id": patient_id},
        note=f"This is the effective output of GET /patients/{patient_id}/journey.",
    )


def build_llm_payload(provider: str, model: str, record: dict) -> dict:
    return build_journey_llm_payload(record, provider, model)


def print_stage(
    index: int,
    title: str,
    value,
    source: str,
    input_value,
    note: str = "",
) -> None:
    print("\n" + "=" * 88)
    print(f"[{index}] {title}")
    print("=" * 88)
    print(f"Source: {source}")
    print(f"Input: {format_value(input_value)}")
    if note:
        print(f"Note: {note}")
    print(f"Type: {type(value).__name__}")
    print(f"Shape: {shape_of(value)}")
    print("Data:")
    print(format_value(value))


def shape_of(value) -> str:
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


def format_value(value) -> str:
    value = dataclass_to_dict(value)
    if isinstance(value, str):
        return value
    return json.dumps(value, indent=2, ensure_ascii=True)


def dataclass_to_dict(value):
    if is_dataclass(value):
        return asdict(value)
    return value


def redact(value):
    if isinstance(value, dict):
        return {
            key: ("<redacted>" if "key" in key.lower() or "authorization" in key.lower() else redact(item))
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


if __name__ == "__main__":
    main()
