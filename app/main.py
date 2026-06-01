from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.api.canonical_his import get_canonical_patient_record
from app.api.his import get_patient, list_patients
from app.audit import read_audit_events, write_audit_event
from app.rag.answering import answer_question
from app.rag.chunking import load_patient_chunks
from app.rag.loaders import load_patient_documents, serialize_documents
from app.rag.llm import answer_with_local_llm
from app.rag.patient_journey import (
    DEFAULT_JOURNEY_MODEL,
    generate_and_store_patient_journey,
    get_patient_journey,
    inspect_patient_journey_pipeline,
)
from app.rag.vector_store import (
    rebuild_vector_store,
    search_patient_chunks,
    vector_store_status,
)

app = FastAPI(title="Clinical AI System - Local HIS", version="0.1.0")
STATIC_DIR = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1)
    k: int = Field(default=3, ge=1, le=10)


class JourneyGenerationRequest(BaseModel):
    use_llm: bool = True
    model: str | None = Field(default=DEFAULT_JOURNEY_MODEL, min_length=1)
    provider: str | None = None
    require_llm: bool = False


def _actor_from_request(request: Request) -> str:
    return request.headers.get("x-user-id") or "local_doctor"


@app.get("/")
def frontend() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/inspect")
def inspector_frontend() -> FileResponse:
    return FileResponse(STATIC_DIR / "inspect.html")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/audit/events")
def audit_events(limit: int = Query(default=100, ge=1, le=500)) -> list[dict]:
    return read_audit_events(limit=limit)


@app.get("/rag/status")
def rag_status() -> dict:
    return vector_store_status()


@app.get("/patients")
def patients() -> list[dict]:
    return list_patients()


@app.get("/patients/{patient_id}")
def patient(patient_id: str) -> dict:
    result = get_patient(patient_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Patient not found")
    return result


@app.get("/patients/{patient_id}/record")
def patient_record(patient_id: str, request: Request) -> dict:
    result = get_canonical_patient_record(patient_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Patient not found")
    metadata = result.get("record_metadata", {})
    write_audit_event(
        "patient_record_viewed",
        actor=_actor_from_request(request),
        patient_id=patient_id,
        metadata={
            "source_system": metadata.get("source_system"),
            "source_record_id": metadata.get("source_record_id"),
            "record_version": metadata.get("record_version"),
            "last_updated": metadata.get("last_updated"),
            "section_counts": {
                "encounters": len(result.get("encounters", [])),
                "labs": len(result.get("labs", [])),
                "medications": len(result.get("medications", [])),
                "clinical_notes": len(result.get("clinical_notes", [])),
            },
        },
    )
    return result


@app.get("/patients/{patient_id}/journey")
def patient_journey(patient_id: str, request: Request) -> dict:
    result = get_patient_journey(patient_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Patient not found")
    write_audit_event(
        "patient_journey_viewed",
        actor=_actor_from_request(request),
        patient_id=patient_id,
        metadata={
            "generated_by": result.get("generated_by"),
            "journey_model": result.get("journey_model"),
            "is_stale": result.get("is_stale"),
            "source_record_version": result.get("source_record_version"),
            "current_source_record_version": result.get("current_source_record_version"),
            "context_strategy": result.get("context_strategy"),
        },
    )
    return result


@app.get("/patients/{patient_id}/journey/inspect")
def patient_journey_inspection(patient_id: str, request: Request) -> dict:
    result = inspect_patient_journey_pipeline(patient_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Patient not found")
    write_audit_event(
        "patient_journey_pipeline_inspected",
        actor=_actor_from_request(request),
        patient_id=patient_id,
        metadata={"dry_run": result.get("dry_run"), "stage_count": len(result.get("stages", []))},
    )
    return result


@app.post("/patients/{patient_id}/journey/generate")
def generate_patient_journey(
    patient_id: str,
    request: JourneyGenerationRequest,
    http_request: Request,
) -> dict:
    result = generate_and_store_patient_journey(
        patient_id,
        use_llm=request.use_llm,
        model=request.model,
        provider=request.provider,
        require_llm=request.require_llm,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Patient not found")
    write_audit_event(
        "patient_journey_regenerated",
        actor=_actor_from_request(http_request),
        patient_id=patient_id,
        metadata={
            "requested_provider": request.provider,
            "requested_model": request.model,
            "require_llm": request.require_llm,
            "generated_by": result.get("generated_by"),
            "journey_model": result.get("journey_model"),
            "source_record_version": result.get("source_record_version"),
        },
    )
    return result


@app.get("/rag/documents")
def rag_documents() -> list[dict]:
    documents = load_patient_documents()
    return serialize_documents(documents)


@app.get("/rag/chunks")
def rag_chunks() -> list[dict]:
    chunks = load_patient_chunks()
    return serialize_documents(chunks)


@app.post("/rag/index")
def rag_index(request: Request) -> dict[str, int | str]:
    result = rebuild_vector_store()
    write_audit_event(
        "vector_index_rebuilt",
        actor=_actor_from_request(request),
        metadata={
            "provider": result.get("provider"),
            "status": result.get("status"),
            "chunk_count": result.get("chunk_count"),
        },
    )
    return result


@app.post("/rag/search")
def rag_search(request: SearchRequest, http_request: Request) -> list[dict]:
    result = search_patient_chunks(request.query, request.k)
    write_audit_event(
        "rag_search_performed",
        actor=_actor_from_request(http_request),
        metadata={"k": request.k, "result_count": len(result), "query_length": len(request.query)},
    )
    return result


@app.post("/rag/ask")
def rag_ask(request: SearchRequest, http_request: Request) -> dict:
    result = answer_question(request.query, request.k)
    write_audit_event(
        "rag_answer_requested",
        actor=_actor_from_request(http_request),
        metadata={
            "mode": "rules",
            "k": request.k,
            "query_length": len(request.query),
            "source_count": len(result.get("sources", [])),
        },
    )
    return result


@app.post("/rag/ask-llm")
def rag_ask_llm(request: SearchRequest, http_request: Request) -> dict:
    result = answer_with_local_llm(request.query, request.k)
    write_audit_event(
        "rag_answer_requested",
        actor=_actor_from_request(http_request),
        metadata={
            "mode": "llm",
            "k": request.k,
            "query_length": len(request.query),
            "source_count": len(result.get("sources", [])),
        },
    )
    return result


@app.post("/patients/{patient_id}/ask")
def patient_ask(patient_id: str, request: SearchRequest, http_request: Request) -> dict:
    if get_patient(patient_id) is None:
        raise HTTPException(status_code=404, detail="Patient not found")
    result = answer_question(request.query, request.k, patient_id=patient_id)
    write_audit_event(
        "patient_rag_answer_requested",
        actor=_actor_from_request(http_request),
        patient_id=patient_id,
        metadata={
            "mode": "rules",
            "k": request.k,
            "query_length": len(request.query),
            "source_count": len(result.get("sources", [])),
        },
    )
    return result


@app.post("/patients/{patient_id}/ask-llm")
def patient_ask_llm(patient_id: str, request: SearchRequest, http_request: Request) -> dict:
    if get_patient(patient_id) is None:
        raise HTTPException(status_code=404, detail="Patient not found")
    result = answer_with_local_llm(request.query, request.k, patient_id=patient_id)
    write_audit_event(
        "patient_rag_answer_requested",
        actor=_actor_from_request(http_request),
        patient_id=patient_id,
        metadata={
            "mode": "llm",
            "k": request.k,
            "query_length": len(request.query),
            "source_count": len(result.get("sources", [])),
        },
    )
    return result
