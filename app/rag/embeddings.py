import hashlib
import math
import re

from langchain_core.embeddings import Embeddings


TOKEN_PATTERN = re.compile(r"[a-zA-Z0-9_]+")
DEFAULT_SENTENCE_TRANSFORMER_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


class HuggingFaceLocalEmbeddings(Embeddings):
    """Local Hugging Face embeddings for better V1 retrieval quality."""

    def __init__(self, model_name: str = DEFAULT_SENTENCE_TRANSFORMER_MODEL) -> None:
        self.model_name = model_name
        self.fallback = LocalHashEmbeddings()
        try:
            from sentence_transformers import SentenceTransformer

            self.model = SentenceTransformer(model_name, local_files_only=True)
        except Exception:
            self.model = None

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if self.model is None:
            return self.fallback.embed_documents(texts)

        embeddings = self.model.encode(
            texts,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return embeddings.tolist()

    def embed_query(self, text: str) -> list[float]:
        if self.model is None:
            return self.fallback.embed_query(text)

        embedding = self.model.encode(
            text,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return embedding.tolist()


class LocalHashEmbeddings(Embeddings):
    """Small local embedding model for V1 demos without API keys or model downloads."""

    def __init__(self, dimensions: int = 384) -> None:
        self.dimensions = dimensions

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text)

    def _embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        tokens = TOKEN_PATTERN.findall(text.lower())

        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimensions
            vector[index] += 1.0

        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0:
            return vector

        return [value / norm for value in vector]
