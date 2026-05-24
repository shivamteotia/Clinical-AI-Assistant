import uuid
import re
from typing import Any

from langchain_core.documents import Document

from app.rag.chunking import load_patient_chunks
from app.rag.config import VectorStoreSettings
from app.rag.embeddings import HuggingFaceLocalEmbeddings
from app.rag.vector_store import score_chunk_match

PATIENT_ID_PATTERN = re.compile(r"\bP\d{3}\b", re.IGNORECASE)
UPSERT_BATCH_SIZE = 16

try:
    from qdrant_client import QdrantClient
    from qdrant_client import models
except ImportError:
    QdrantClient = None
    models = None


def rebuild_qdrant_vector_store(settings: VectorStoreSettings) -> dict[str, int | str]:
    client = _client(settings)
    chunks = load_patient_chunks()
    embedding_model = HuggingFaceLocalEmbeddings()
    texts = [chunk.page_content for chunk in chunks]
    embeddings = embedding_model.embed_documents(texts)

    if not embeddings:
        return {
            "store": "qdrant_vector_store",
            "collection": settings.qdrant_collection,
            "chunk_count": 0,
        }

    vector_size = len(embeddings[0])
    _recreate_collection(client, settings.qdrant_collection, vector_size)

    points = [
        models.PointStruct(
            id=_point_id(chunk),
            vector=embedding,
            payload={
                "chunk_id": _chunk_id(chunk),
                "page_content": chunk.page_content,
                "metadata": chunk.metadata,
            },
        )
        for chunk, embedding in zip(chunks, embeddings)
    ]
    for batch in _batches(points, UPSERT_BATCH_SIZE):
        client.upsert(collection_name=settings.qdrant_collection, points=batch)

    return {
        "store": "qdrant_vector_store",
        "collection": settings.qdrant_collection,
        "chunk_count": len(chunks),
    }


def search_qdrant_patient_chunks(
    query: str,
    k: int,
    settings: VectorStoreSettings,
) -> list[dict]:
    client = _client(settings)
    embedding_model = HuggingFaceLocalEmbeddings()
    query_embedding = embedding_model.embed_query(query)
    search_limit = max(k * 5, k)
    query_filter = _build_query_filter(query)

    points = client.search(
        collection_name=settings.qdrant_collection,
        query_vector=query_embedding,
        query_filter=query_filter,
        limit=search_limit,
        with_payload=True,
    )

    matches = []
    for point in points:
        payload = point.payload or {}
        page_content = payload.get("page_content", "")
        metadata = payload.get("metadata", {})
        semantic_score = float(point.score or 0.0)
        scores = score_chunk_match(query, page_content, metadata, semantic_score)
        matches.append(
            {
                "page_content": page_content,
                "metadata": metadata,
                **scores,
            }
        )

    return sorted(matches, key=lambda match: match["score"], reverse=True)[:k]


def qdrant_vector_store_status(settings: VectorStoreSettings) -> dict:
    base_status = {
        "provider": "qdrant",
        "store": "qdrant_vector_store",
        "collection": settings.qdrant_collection,
    }

    try:
        client = _client(settings)
        exists = client.collection_exists(collection_name=settings.qdrant_collection)
        chunk_count = None
        if exists:
            chunk_count = client.count(
                collection_name=settings.qdrant_collection,
                exact=True,
            ).count

        return {
            **base_status,
            "status": "ready" if exists else "missing",
            "connected": True,
            "chunk_count": chunk_count,
        }
    except Exception as error:
        return {
            **base_status,
            "status": "unavailable",
            "connected": False,
            "chunk_count": None,
            "message": error.__class__.__name__,
        }


def _client(settings: VectorStoreSettings) -> Any:
    if QdrantClient is None:
        raise RuntimeError(
            "qdrant-client is not installed. Run `pip install -r requirements.txt`."
        )
    if not settings.qdrant_url:
        raise RuntimeError("QDRANT_URL is required when VECTOR_STORE_PROVIDER=qdrant.")

    return QdrantClient(
        url=settings.qdrant_url,
        api_key=settings.qdrant_api_key,
        timeout=60,
    )


def _recreate_collection(client: Any, collection_name: str, vector_size: int) -> None:
    if client.collection_exists(collection_name=collection_name):
        client.delete_collection(collection_name=collection_name)

    client.create_collection(
        collection_name=collection_name,
        vectors_config=models.VectorParams(
            size=vector_size,
            distance=models.Distance.COSINE,
        ),
    )
    client.create_payload_index(
        collection_name=collection_name,
        field_name="metadata.patient_id",
        field_schema=models.PayloadSchemaType.KEYWORD,
    )


def _build_query_filter(query: str) -> Any | None:
    patient_ids = sorted({patient_id.upper() for patient_id in PATIENT_ID_PATTERN.findall(query)})
    if not patient_ids:
        return None

    conditions = [
        models.FieldCondition(
            key="metadata.patient_id",
            match=models.MatchAny(any=patient_ids),
        )
    ]
    return models.Filter(must=conditions)


def _batches(items: list, batch_size: int) -> list[list]:
    return [
        items[index:index + batch_size]
        for index in range(0, len(items), batch_size)
    ]


def _point_id(chunk: Document) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, _chunk_id(chunk)))


def _chunk_id(chunk: Document) -> str:
    patient_id = chunk.metadata["patient_id"]
    chunk_index = chunk.metadata["chunk_index"]
    return f"{patient_id}-chunk-{chunk_index}"
