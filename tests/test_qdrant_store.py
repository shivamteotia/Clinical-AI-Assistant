import unittest
from types import SimpleNamespace

from langchain_core.documents import Document

from app.rag.config import VectorStoreSettings
from app.rag import qdrant_store


class FakeEmbeddings:
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0, 0.0] for _ in texts]

    def embed_query(self, text: str) -> list[float]:
        return [1.0, 0.0, 0.0]


class FakeModels:
    class Distance:
        COSINE = "Cosine"

    class VectorParams:
        def __init__(self, size: int, distance: str) -> None:
            self.size = size
            self.distance = distance

    class PointStruct:
        def __init__(self, id: str, vector: list[float], payload: dict) -> None:
            self.id = id
            self.vector = vector
            self.payload = payload

    class MatchAny:
        def __init__(self, any: list[str]) -> None:
            self.any = any

    class FieldCondition:
        def __init__(self, key: str, match) -> None:
            self.key = key
            self.match = match

    class Filter:
        def __init__(self, must: list) -> None:
            self.must = must

    class PayloadSchemaType:
        KEYWORD = "keyword"


class FakeQdrantClient:
    latest = None
    search_points = []
    collection_exists_result = False

    def __init__(self, url: str, api_key: str | None = None, timeout: int | None = None) -> None:
        self.url = url
        self.api_key = api_key
        self.timeout = timeout
        self.created_collection = None
        self.created_payload_indexes = []
        self.deleted_collections = []
        self.upserted_points = []
        self.last_query_filter = None
        FakeQdrantClient.latest = self

    def collection_exists(self, collection_name: str) -> bool:
        return self.collection_exists_result

    def delete_collection(self, collection_name: str) -> None:
        self.deleted_collections.append(collection_name)

    def create_collection(self, collection_name: str, vectors_config) -> None:
        self.created_collection = (collection_name, vectors_config)

    def create_payload_index(
        self,
        collection_name: str,
        field_name: str,
        field_schema: str,
    ) -> None:
        self.created_payload_indexes.append((collection_name, field_name, field_schema))

    def upsert(self, collection_name: str, points: list) -> None:
        self.upserted_points.extend(points)

    def search(
        self,
        collection_name: str,
        query_vector: list[float],
        query_filter,
        limit: int,
        with_payload: bool,
    ) -> list:
        self.last_query_filter = query_filter
        return self.search_points[:limit]

    def count(self, collection_name: str, exact: bool) -> SimpleNamespace:
        return SimpleNamespace(count=len(self.upserted_points) or len(self.search_points))


class QdrantStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.original_client = qdrant_store.QdrantClient
        self.original_models = qdrant_store.models
        self.original_embeddings = qdrant_store.HuggingFaceLocalEmbeddings
        self.original_loader = qdrant_store.load_patient_chunks
        qdrant_store.QdrantClient = FakeQdrantClient
        qdrant_store.models = FakeModels
        qdrant_store.HuggingFaceLocalEmbeddings = FakeEmbeddings
        qdrant_store.load_patient_chunks = lambda: [
            Document(
                page_content="Patient has type 2 diabetes and high HbA1c.",
                metadata={
                    "patient_id": "P001",
                    "patient_name": "Aarav Sharma",
                    "chunk_index": 0,
                },
            )
        ]

    def tearDown(self) -> None:
        qdrant_store.QdrantClient = self.original_client
        qdrant_store.models = self.original_models
        qdrant_store.HuggingFaceLocalEmbeddings = self.original_embeddings
        qdrant_store.load_patient_chunks = self.original_loader

    def test_rebuild_qdrant_vector_store_creates_collection_and_upserts_chunks(self) -> None:
        settings = VectorStoreSettings(
            provider="qdrant",
            qdrant_url="https://example.qdrant.tech",
            qdrant_api_key="secret",
            qdrant_collection="clinical_test",
        )

        result = qdrant_store.rebuild_qdrant_vector_store(settings)

        client = FakeQdrantClient.latest
        self.assertEqual(result["store"], "qdrant_vector_store")
        self.assertEqual(result["collection"], "clinical_test")
        self.assertEqual(result["chunk_count"], 1)
        self.assertEqual(client.created_collection[0], "clinical_test")
        self.assertEqual(client.created_collection[1].size, 3)
        self.assertEqual(
            client.created_payload_indexes,
            [("clinical_test", "metadata.patient_id", "keyword")],
        )
        self.assertEqual(len(client.upserted_points), 1)
        self.assertEqual(client.timeout, 60)
        self.assertEqual(
            client.upserted_points[0].payload["metadata"]["patient_id"],
            "P001",
        )

    def test_search_qdrant_patient_chunks_returns_normalized_matches(self) -> None:
        FakeQdrantClient.search_points = [
            SimpleNamespace(
                score=0.8,
                payload={
                    "page_content": "Patient has type 2 diabetes and high HbA1c.",
                    "metadata": {
                        "patient_id": "P001",
                        "patient_name": "Aarav Sharma",
                        "diagnosis_terms": ["diabetes"],
                        "lab_terms": ["hba1c"],
                        "medication_terms": [],
                    },
                },
            )
        ]
        settings = VectorStoreSettings(
            provider="qdrant",
            qdrant_url="https://example.qdrant.tech",
            qdrant_api_key="secret",
            qdrant_collection="clinical_test",
        )

        matches = qdrant_store.search_qdrant_patient_chunks(
            "Which patient has diabetes and high HbA1c?",
            3,
            settings,
        )

        self.assertEqual(matches[0]["metadata"]["patient_id"], "P001")
        self.assertGreater(matches[0]["score"], matches[0]["semantic_score"])

    def test_search_uses_patient_id_filter_when_query_names_patient(self) -> None:
        FakeQdrantClient.search_points = []
        settings = VectorStoreSettings(
            provider="qdrant",
            qdrant_url="https://example.qdrant.tech",
            qdrant_api_key="secret",
            qdrant_collection="clinical_test",
        )

        qdrant_store.search_qdrant_patient_chunks(
            "What medication is P001 taking?",
            3,
            settings,
        )

        client = FakeQdrantClient.latest
        self.assertIsNotNone(client.last_query_filter)
        self.assertEqual(client.last_query_filter.must[0].key, "metadata.patient_id")
        self.assertEqual(client.last_query_filter.must[0].match.any, ["P001"])

    def test_qdrant_status_reports_ready_collection(self) -> None:
        FakeQdrantClient.search_points = [SimpleNamespace()]
        FakeQdrantClient.collection_exists_result = True
        settings = VectorStoreSettings(
            provider="qdrant",
            qdrant_url="https://example.qdrant.tech",
            qdrant_api_key="secret",
            qdrant_collection="clinical_test",
        )

        status = qdrant_store.qdrant_vector_store_status(settings)

        self.assertEqual(status["provider"], "qdrant")
        self.assertEqual(status["collection"], "clinical_test")
        self.assertTrue(status["connected"])
        self.assertEqual(status["status"], "ready")
        self.assertEqual(status["chunk_count"], 1)


if __name__ == "__main__":
    unittest.main()
