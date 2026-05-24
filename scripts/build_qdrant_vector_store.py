import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

os.environ["VECTOR_STORE_PROVIDER"] = "qdrant"

from app.rag.vector_store import rebuild_vector_store


def main() -> None:
    result = rebuild_vector_store()
    print("Built Qdrant vector store")
    print(f"Collection: {result['collection']}")
    print(f"Chunks indexed: {result['chunk_count']}")


if __name__ == "__main__":
    main()
