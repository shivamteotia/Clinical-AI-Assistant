import os
from dataclasses import dataclass
from pathlib import Path


DEFAULT_VECTOR_STORE_PROVIDER = "sqlite"
DEFAULT_QDRANT_COLLECTION = "clinical_patient_chunks"
BASE_DIR = Path(__file__).resolve().parents[2]
ENV_PATH = BASE_DIR / ".env"


@dataclass(frozen=True)
class VectorStoreSettings:
    provider: str
    qdrant_url: str | None
    qdrant_api_key: str | None
    qdrant_collection: str


def get_vector_store_settings() -> VectorStoreSettings:
    load_dotenv_file()
    return VectorStoreSettings(
        provider=os.getenv("VECTOR_STORE_PROVIDER", DEFAULT_VECTOR_STORE_PROVIDER).lower(),
        qdrant_url=os.getenv("QDRANT_URL"),
        qdrant_api_key=os.getenv("QDRANT_API_KEY"),
        qdrant_collection=os.getenv("QDRANT_COLLECTION", DEFAULT_QDRANT_COLLECTION),
    )


def load_dotenv_file(path: Path = ENV_PATH) -> None:
    if not path.exists():
        return

    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value
