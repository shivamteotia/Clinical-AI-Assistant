from typing import Literal
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.api.canonical_his import get_canonical_patient_record
from app.api.his import get_patient, list_patients
from app.auth import actor_from_request, get_auth_settings, require_admin, require_doctor
from app.audit import read_audit_events, write_audit_event
from app.feedback import read_journey_feedback, write_journey_feedback
from app.his_sync import queue_or_process_his_journey_work, scan_his_journey_work
from app.rag.config import get_patient_journey_llm_settings, get_vector_store_settings
from app.rag.answering import answer_question
from app.rag.chunking import load_patient_chunks
from app.rag.loaders import load_patient_documents, serialize_documents
from app.rag.llm import answer_with_local_llm
from app.rag.journey_runs import read_journey_runs
from app.rag.journey_refresh import (
    list_pending_journey_refreshes,
    list_stale_patient_journeys,
    process_pending_journey_refreshes,
    queue_patient_journey_refresh,
    refresh_patient_journey,
    refresh_stale_patient_journeys,
)
from app.rag.patient_journey import (
    DEFAULT_JOURNEY_MODEL,
    generate_and_store_patient_journey,
    get_patient_journey,
    inspect_patient_journey_pipeline,
)
from app.rag.journey_store import journey_store_status
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


class HisSyncRequest(BaseModel):
    use_llm: bool = True
    model: str | None = Field(default=None, min_length=1)
    provider: str | None = None
    require_llm: bool = False
    process: bool = False

class JourneyQueueProcessRequest(BaseModel):
    use_llm: bool = True
    model: str | None = Field(default=None, min_length=1)
    provider: str | None = None
    require_llm: bool = False
    limit: int = Field(default=10, ge=1, le=100)

class JourneyGenerationRequest(BaseModel):
    use_llm: bool = True
    model: str | None = Field(default=DEFAULT_JOURNEY_MODEL, min_length=1)
    provider: str | None = None
    require_llm: bool = False


class JourneyFeedbackRequest(BaseModel):
    feedback_type: Literal["useful", "missing_info", "incorrect", "other"]
    comment: str | None = Field(default=None, max_length=500)

class JourneyRefreshRequest(BaseModel):
    use_llm: bool = True
    model: str | None = Field(default=None, min_length=1)
    provider: str | None = None
    require_llm: bool = False
    background: bool = False


@app.get("/")
def frontend() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/inspect")
def inspector_frontend() -> FileResponse:
    return FileResponse(STATIC_DIR / "inspect.html")


@app.get("/admin")
def admin_frontend() -> FileResponse:
    return FileResponse(STATIC_DIR / "admin.html")

@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/his/sync/status")
def his_sync_status(request: Request) -> dict:
    require_admin(request)
    return scan_his_journey_work(persist_state=True)


@app.post("/his/sync")
def his_sync(request: HisSyncRequest, http_request: Request) -> dict:
    require_admin(http_request)
    return queue_or_process_his_journey_work(
        actor=actor_from_request(http_request),
        use_llm=request.use_llm,
        provider=request.provider,
        model=request.model,
        require_llm=request.require_llm,
        process=request.process,
    )

@app.get("/admin/status")
def admin_status(request: Request) -> dict:
    require_admin(request)
    auth_settings = get_auth_settings()
    vector_settings = get_vector_store_settings()
    journey_llm_settings = get_patient_journey_llm_settings()
    vector_status = vector_store_status()
    stale = list_stale_patient_journeys()
    recent_runs = read_journey_runs(limit=25)
    recent_audit_events = read_audit_events(limit=25)
    return {
        "auth": {
            "enabled": auth_settings.enabled,
            "doctor_key_configured": bool(auth_settings.doctor_api_key),
            "admin_key_configured": bool(auth_settings.admin_api_key),
        },
        "vector_store": {
            "configured_provider": vector_settings.provider,
            "active_provider": vector_status.get("provider"),
            "status": vector_status.get("status"),
            "connected": vector_status.get("connected"),
            "collection": vector_status.get("collection") or vector_settings.qdrant_collection,
            "chunk_count": vector_status.get("chunk_count"),
            "qdrant_url_configured": bool(vector_settings.qdrant_url),
            "qdrant_api_key_configured": bool(vector_settings.qdrant_api_key),
        },
        "journey_llm": {
            "provider": journey_llm_settings.provider,
            "model": journey_llm_settings.model,
            "groq_api_key_configured": bool(journey_llm_settings.groq_api_key),
        },
        "journeys": {
            "store": journey_store_status(),
            "stale_count": len(stale),
            "recent_run_count": len(recent_runs),
            "latest_run_status": recent_runs[0].get("status") if recent_runs else None,
            "latest_run_patient_id": recent_runs[0].get("patient_id") if recent_runs else None,
        },
        "audit": {
            "recent_event_count": len(recent_audit_events),
            "latest_event_type": recent_audit_events[0].get("event_type") if recent_audit_events else None,
        },
    }
@app.get("/audit/events")
def audit_events(request: Request, limit: int = Query(default=100, ge=1, le=500)) -> list[dict]:
    require_admin(request)
    return read_audit_events(limit=limit)


@app.get("/rag/status")
def rag_status() -> dict:
    return vector_store_status()


@app.get("/journey-feedback")
def journey_feedback_events(
    request: Request,
    patient_id: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
) -> list[dict]:
    require_admin(request)
    return read_journey_feedback(limit=limit, patient_id=patient_id)

@app.get("/journeys/runs")
def journey_runs(request: Request, limit: int = Query(default=100, ge=1, le=500)) -> list[dict]:
    require_admin(request)
    return read_journey_runs(limit=limit)


@app.get("/patients/{patient_id}/journey/runs")
def patient_journey_runs(patient_id: str, request: Request, limit: int = Query(default=50, ge=1, le=500)) -> list[dict]:
    require_admin(request)
    if get_patient(patient_id) is None:
        raise HTTPException(status_code=404, detail="Patient not found")
    return read_journey_runs(limit=limit, patient_id=patient_id)


@app.get("/journeys/queue")
def journey_refresh_queue(request: Request, limit: int = Query(default=100, ge=1, le=500)) -> dict:
    require_admin(request)
    pending = list_pending_journey_refreshes(limit=limit)
    return {"pending_count": len(pending), "pending": pending}


@app.post("/journeys/process-queue")
def process_journey_refresh_queue(request: JourneyQueueProcessRequest, http_request: Request) -> dict:
    require_admin(http_request)
    return process_pending_journey_refreshes(
        actor=actor_from_request(http_request),
        use_llm=request.use_llm,
        provider=request.provider,
        model=request.model,
        require_llm=request.require_llm,
        limit=request.limit,
    )

@app.get("/journeys/stale")
def stale_journeys(request: Request) -> dict:
    require_admin(request)
    stale = list_stale_patient_journeys()
    return {"stale_count": len(stale), "stale": stale}


@app.post("/journeys/refresh-stale")
def refresh_stale_journeys(request: JourneyRefreshRequest, http_request: Request) -> dict:
    require_admin(http_request)
    return refresh_stale_patient_journeys(
        actor=actor_from_request(http_request),
        use_llm=request.use_llm,
        provider=request.provider,
        model=request.model,
        require_llm=request.require_llm,
    )


@app.get("/patients")
def patients(request: Request) -> list[dict]:
    require_doctor(request)
    return list_patients()


@app.get("/patients/{patient_id}")
def patient(patient_id: str, request: Request) -> dict:
    require_doctor(request)
    result = get_patient(patient_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Patient not found")
    return result


@app.get("/patients/{patient_id}/record")
def patient_record(patient_id: str, request: Request) -> dict:
    require_doctor(request)
    result = get_canonical_patient_record(patient_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Patient not found")
    metadata = result.get("record_metadata", {})
    write_audit_event(
        "patient_record_viewed",
        actor=actor_from_request(request),
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
    require_doctor(request)
    result = get_patient_journey(patient_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Patient not found")
    write_audit_event(
        "patient_journey_viewed",
        actor=actor_from_request(request),
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


@app.post("/patients/{patient_id}/journey/feedback")
def submit_patient_journey_feedback(
    patient_id: str,
    request: JourneyFeedbackRequest,
    http_request: Request,
) -> dict:
    require_doctor(http_request)
    journey = get_patient_journey(patient_id)
    if journey is None:
        raise HTTPException(status_code=404, detail="Patient not found")
    feedback = write_journey_feedback(
        patient_id=patient_id,
        feedback_type=request.feedback_type,
        comment=request.comment,
        actor=actor_from_request(http_request),
        metadata={
            "journey_generated_by": journey.get("generated_by"),
            "journey_model": journey.get("journey_model"),
            "source_record_version": journey.get("source_record_version"),
            "is_stale": journey.get("is_stale"),
        },
    )
    write_audit_event(
        "patient_journey_feedback_submitted",
        actor=actor_from_request(http_request),
        patient_id=patient_id,
        metadata={
            "feedback_id": feedback.get("feedback_id"),
            "feedback_type": feedback.get("feedback_type"),
            "comment_length": len(feedback.get("comment") or ""),
            "journey_generated_by": journey.get("generated_by"),
            "journey_model": journey.get("journey_model"),
            "source_record_version": journey.get("source_record_version"),
        },
    )
    return {"status": "recorded", **feedback}

@app.get("/patients/{patient_id}/journey/inspect")
def patient_journey_inspection(patient_id: str, request: Request) -> dict:
    require_admin(request)
    result = inspect_patient_journey_pipeline(patient_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Patient not found")
    write_audit_event(
        "patient_journey_pipeline_inspected",
        actor=actor_from_request(request),
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
    require_admin(http_request)
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
        actor=actor_from_request(http_request),
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


@app.post("/patients/{patient_id}/journey/refresh")
def refresh_patient_journey_endpoint(
    patient_id: str,
    request: JourneyRefreshRequest,
    http_request: Request,
    background_tasks: BackgroundTasks,
) -> dict:
    require_admin(http_request)
    actor = actor_from_request(http_request)
    if request.background:
        queued = queue_patient_journey_refresh(
            patient_id,
            actor=actor,
            reason="manual_background",
            metadata={
                "use_llm": request.use_llm,
                "provider": request.provider,
                "model": request.model,
                "require_llm": request.require_llm,
            },
        )
        if queued is None:
            raise HTTPException(status_code=404, detail="Patient not found")
        background_tasks.add_task(
            refresh_patient_journey,
            patient_id,
            actor=actor,
            use_llm=request.use_llm,
            provider=request.provider,
            model=request.model,
            require_llm=request.require_llm,
            reason="manual_background",
            queued_event=queued,
        )
        return {"status": "queued", **queued}

    try:
        result = refresh_patient_journey(
            patient_id,
            actor=actor,
            use_llm=request.use_llm,
            provider=request.provider,
            model=request.model,
            require_llm=request.require_llm,
            reason="manual",
        )
    except RuntimeError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    if result is None:
        raise HTTPException(status_code=404, detail="Patient not found")
    return result


@app.get("/rag/documents")
def rag_documents(request: Request) -> list[dict]:
    require_admin(request)
    documents = load_patient_documents()
    return serialize_documents(documents)


@app.get("/rag/chunks")
def rag_chunks(request: Request) -> list[dict]:
    require_admin(request)
    chunks = load_patient_chunks()
    return serialize_documents(chunks)


@app.post("/rag/index")
def rag_index(request: Request) -> dict[str, int | str]:
    require_admin(request)
    result = rebuild_vector_store()
    write_audit_event(
        "vector_index_rebuilt",
        actor=actor_from_request(request),
        metadata={
            "provider": result.get("provider"),
            "status": result.get("status"),
            "chunk_count": result.get("chunk_count"),
        },
    )
    return result


@app.post("/rag/search")
def rag_search(request: SearchRequest, http_request: Request) -> list[dict]:
    require_doctor(http_request)
    result = search_patient_chunks(request.query, request.k)
    write_audit_event(
        "rag_search_performed",
        actor=actor_from_request(http_request),
        metadata={"k": request.k, "result_count": len(result), "query_length": len(request.query)},
    )
    return result


@app.post("/rag/ask")
def rag_ask(request: SearchRequest, http_request: Request) -> dict:
    require_doctor(http_request)
    result = answer_question(request.query, request.k)
    write_audit_event(
        "rag_answer_requested",
        actor=actor_from_request(http_request),
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
    require_doctor(http_request)
    result = answer_with_local_llm(request.query, request.k)
    write_audit_event(
        "rag_answer_requested",
        actor=actor_from_request(http_request),
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
    require_doctor(http_request)
    if get_patient(patient_id) is None:
        raise HTTPException(status_code=404, detail="Patient not found")
    result = answer_question(request.query, request.k, patient_id=patient_id)
    write_audit_event(
        "patient_rag_answer_requested",
        actor=actor_from_request(http_request),
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
    require_doctor(http_request)
    if get_patient(patient_id) is None:
        raise HTTPException(status_code=404, detail="Patient not found")
    result = answer_with_local_llm(request.query, request.k, patient_id=patient_id)
    write_audit_event(
        "patient_rag_answer_requested",
        actor=actor_from_request(http_request),
        patient_id=patient_id,
        metadata={
            "mode": "llm",
            "k": request.k,
            "query_length": len(request.query),
            "source_count": len(result.get("sources", [])),
        },
    )
    return result
