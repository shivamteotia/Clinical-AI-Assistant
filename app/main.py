from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.api.his import get_patient, get_patient_record, list_patients
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


@app.get("/")
def frontend() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/inspect")
def inspector_frontend() -> FileResponse:
    return FileResponse(STATIC_DIR / "inspect.html")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


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
def patient_record(patient_id: str) -> dict:
    result = get_patient_record(patient_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Patient not found")
    return result


@app.get("/patients/{patient_id}/journey")
def patient_journey(patient_id: str) -> dict:
    result = get_patient_journey(patient_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Patient not found")
    return result


@app.get("/patients/{patient_id}/journey/inspect")
def patient_journey_inspection(patient_id: str) -> dict:
    result = inspect_patient_journey_pipeline(patient_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Patient not found")
    return result


@app.post("/patients/{patient_id}/journey/generate")
def generate_patient_journey(
    patient_id: str,
    request: JourneyGenerationRequest,
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
def rag_index() -> dict[str, int | str]:
    return rebuild_vector_store()


@app.post("/rag/search")
def rag_search(request: SearchRequest) -> list[dict]:
    return search_patient_chunks(request.query, request.k)


@app.post("/rag/ask")
def rag_ask(request: SearchRequest) -> dict:
    return answer_question(request.query, request.k)


@app.post("/rag/ask-llm")
def rag_ask_llm(request: SearchRequest) -> dict:
    return answer_with_local_llm(request.query, request.k)


@app.post("/patients/{patient_id}/ask")
def patient_ask(patient_id: str, request: SearchRequest) -> dict:
    if get_patient(patient_id) is None:
        raise HTTPException(status_code=404, detail="Patient not found")
    return answer_question(request.query, request.k, patient_id=patient_id)


@app.post("/patients/{patient_id}/ask-llm")
def patient_ask_llm(patient_id: str, request: SearchRequest) -> dict:
    if get_patient(patient_id) is None:
        raise HTTPException(status_code=404, detail="Patient not found")
    return answer_with_local_llm(request.query, request.k, patient_id=patient_id)
