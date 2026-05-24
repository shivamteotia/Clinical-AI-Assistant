import json
import math
import re
import sqlite3
from pathlib import Path

from langchain_core.documents import Document

from app.rag.config import get_vector_store_settings
from app.rag.chunking import load_patient_chunks
from app.rag.embeddings import HuggingFaceLocalEmbeddings

BASE_DIR = Path(__file__).resolve().parents[2]
VECTOR_DB_PATH = BASE_DIR / "vector_store.db"
WORD_PATTERN = re.compile(r"[a-zA-Z0-9_]+")
PATIENT_ID_PATTERN = re.compile(r"\bP\d{3}\b", re.IGNORECASE)
CLINICAL_PHRASES = [
    "chest discomfort",
    "chronic kidney disease",
    "burning urination",
    "iron deficiency anemia",
    "shortness of breath",
    "fasting glucose",
    "type 2 diabetes",
    "high hba1c",
    "rheumatoid arthritis",
    "peripheral neuropathy",
]
STOP_WORDS = {
    "a",
    "about",
    "and",
    "find",
    "for",
    "has",
    "have",
    "is",
    "notes",
    "patient",
    "patients",
    "the",
    "to",
    "what",
    "which",
    "with",
}


def _connect() -> sqlite3.Connection:
    connection = sqlite3.connect(VECTOR_DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def _create_schema(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS vector_chunks (
            id TEXT PRIMARY KEY,
            page_content TEXT NOT NULL,
            metadata_json TEXT NOT NULL,
            embedding_json TEXT NOT NULL
        )
        """
    )


def rebuild_vector_store() -> dict[str, int | str]:
    settings = get_vector_store_settings()
    if settings.provider == "qdrant":
        from app.rag.qdrant_store import rebuild_qdrant_vector_store

        return rebuild_qdrant_vector_store(settings)
    if settings.provider != "sqlite":
        raise ValueError(f"Unsupported vector store provider: {settings.provider}")

    return rebuild_sqlite_vector_store()


def search_patient_chunks(query: str, k: int = 3) -> list[dict]:
    settings = get_vector_store_settings()
    if settings.provider == "qdrant":
        from app.rag.qdrant_store import search_qdrant_patient_chunks

        return search_qdrant_patient_chunks(query, k, settings)
    if settings.provider != "sqlite":
        raise ValueError(f"Unsupported vector store provider: {settings.provider}")

    return search_sqlite_patient_chunks(query, k)


def vector_store_status() -> dict:
    settings = get_vector_store_settings()
    if settings.provider == "qdrant":
        from app.rag.qdrant_store import qdrant_vector_store_status

        return qdrant_vector_store_status(settings)
    if settings.provider != "sqlite":
        return {
            "provider": settings.provider,
            "status": "unsupported",
            "connected": False,
            "message": f"Unsupported vector store provider: {settings.provider}",
        }

    return sqlite_vector_store_status()


def sqlite_vector_store_status() -> dict:
    if not VECTOR_DB_PATH.exists():
        return {
            "provider": "sqlite",
            "store": "sqlite_vector_store",
            "status": "missing",
            "connected": False,
            "persist_path": str(VECTOR_DB_PATH),
            "chunk_count": 0,
        }

    with _connect() as connection:
        _create_schema(connection)
        count = connection.execute("SELECT COUNT(*) FROM vector_chunks").fetchone()[0]

    return {
        "provider": "sqlite",
        "store": "sqlite_vector_store",
        "status": "ready" if count else "empty",
        "connected": True,
        "persist_path": str(VECTOR_DB_PATH),
        "chunk_count": count,
    }


def rebuild_sqlite_vector_store() -> dict[str, int | str]:
    chunks = load_patient_chunks()
    embedding_model = HuggingFaceLocalEmbeddings()
    texts = [chunk.page_content for chunk in chunks]
    embeddings = embedding_model.embed_documents(texts)

    with _connect() as connection:
        _create_schema(connection)
        connection.execute("DELETE FROM vector_chunks")

        for chunk, embedding in zip(chunks, embeddings):
            connection.execute(
                """
                INSERT INTO vector_chunks (
                    id, page_content, metadata_json, embedding_json
                )
                VALUES (?, ?, ?, ?)
                """,
                (
                    _chunk_id(chunk),
                    chunk.page_content,
                    json.dumps(chunk.metadata),
                    json.dumps(embedding),
                ),
            )

        connection.commit()

    return {
        "store": "sqlite_vector_store",
        "persist_path": str(VECTOR_DB_PATH),
        "chunk_count": len(chunks),
    }


def search_sqlite_patient_chunks(query: str, k: int = 3) -> list[dict]:
    _ensure_vector_store()

    embedding_model = HuggingFaceLocalEmbeddings()
    query_embedding = embedding_model.embed_query(query)

    with _connect() as connection:
        rows = connection.execute(
            """
            SELECT page_content, metadata_json, embedding_json
            FROM vector_chunks
            """
        ).fetchall()

    matches = []
    for row in rows:
        embedding = json.loads(row["embedding_json"])
        semantic_score = _cosine_similarity(query_embedding, embedding)
        keyword_score = _keyword_overlap(query, row["page_content"])
        phrase_score = _phrase_overlap(query, row["page_content"])
        patient_id_score = _patient_id_match(query, row["metadata_json"])
        score = (
            semantic_score
            + (0.15 * keyword_score)
            + (0.35 * phrase_score)
            + (0.60 * patient_id_score)
        )
        matches.append(
            {
                "page_content": row["page_content"],
                "metadata": json.loads(row["metadata_json"]),
                "score": score,
                "semantic_score": semantic_score,
                "keyword_score": keyword_score,
                "phrase_score": phrase_score,
                "patient_id_score": patient_id_score,
            }
        )

    return sorted(matches, key=lambda match: match["score"], reverse=True)[:k]


def _ensure_vector_store() -> None:
    if not VECTOR_DB_PATH.exists():
        rebuild_sqlite_vector_store()
        return

    with _connect() as connection:
        _create_schema(connection)
        count = connection.execute("SELECT COUNT(*) FROM vector_chunks").fetchone()[0]

    if count == 0:
        rebuild_sqlite_vector_store()


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    dot_product = sum(left_value * right_value for left_value, right_value in zip(left, right))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))

    if left_norm == 0 or right_norm == 0:
        return 0.0

    return dot_product / (left_norm * right_norm)


def _keyword_overlap(query: str, document: str) -> float:
    query_terms = _terms(query)
    if not query_terms:
        return 0.0

    document_terms = _terms(document)
    matches = query_terms.intersection(document_terms)
    return len(matches) / len(query_terms)


def _terms(text: str) -> set[str]:
    return {
        word
        for word in WORD_PATTERN.findall(text.lower())
        if len(word) > 2 and word not in STOP_WORDS
    }


def _phrase_overlap(query: str, document: str) -> float:
    query_text = query.lower()
    document_text = document.lower()
    query_phrases = [phrase for phrase in CLINICAL_PHRASES if phrase in query_text]
    if not query_phrases:
        return 0.0

    matches = [phrase for phrase in query_phrases if phrase in document_text]
    return len(matches) / len(query_phrases)


def _patient_id_match(query: str, metadata_json: str) -> float:
    patient_ids = {patient_id.upper() for patient_id in PATIENT_ID_PATTERN.findall(query)}
    if not patient_ids:
        return 0.0

    metadata = json.loads(metadata_json)
    patient_id = metadata.get("patient_id", "").upper()
    return 1.0 if patient_id in patient_ids else 0.0


def score_chunk_match(
    query: str,
    page_content: str,
    metadata: dict,
    semantic_score: float,
) -> dict[str, float]:
    keyword_score = _keyword_overlap(query, page_content)
    phrase_score = _phrase_overlap(query, page_content)
    patient_id_score = _patient_id_match(query, json.dumps(metadata))
    metadata_score = _metadata_overlap(query, metadata)
    score = (
        semantic_score
        + (0.15 * keyword_score)
        + (0.35 * phrase_score)
        + (0.60 * patient_id_score)
        + (0.20 * metadata_score)
    )
    return {
        "score": score,
        "semantic_score": semantic_score,
        "keyword_score": keyword_score,
        "phrase_score": phrase_score,
        "patient_id_score": patient_id_score,
        "metadata_score": metadata_score,
    }


def _metadata_overlap(query: str, metadata: dict) -> float:
    query_terms = _terms(query)
    if not query_terms:
        return 0.0

    metadata_terms = set()
    for key in [
        "diagnosis_terms",
        "lab_terms",
        "medication_terms",
        "source_section",
    ]:
        value = metadata.get(key)
        if isinstance(value, list):
            metadata_terms.update(str(item).lower() for item in value)
        elif value:
            metadata_terms.update(_terms(str(value)))

    matches = query_terms.intersection(metadata_terms)
    return len(matches) / len(query_terms)


def _chunk_id(chunk: Document) -> str:
    patient_id = chunk.metadata["patient_id"]
    chunk_index = chunk.metadata["chunk_index"]
    return f"{patient_id}-chunk-{chunk_index}"
