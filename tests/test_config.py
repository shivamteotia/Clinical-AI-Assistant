import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from app.rag.config import (
    DEFAULT_QDRANT_COLLECTION,
    DEFAULT_VECTOR_STORE_PROVIDER,
    get_vector_store_settings,
    load_dotenv_file,
)


class ConfigTests(unittest.TestCase):
    def test_default_vector_store_settings_use_sqlite(self) -> None:
        old_provider = os.environ.pop("VECTOR_STORE_PROVIDER", None)
        old_collection = os.environ.pop("QDRANT_COLLECTION", None)
        try:
            settings = get_vector_store_settings()

            self.assertEqual(settings.provider, DEFAULT_VECTOR_STORE_PROVIDER)
            self.assertEqual(settings.qdrant_collection, DEFAULT_QDRANT_COLLECTION)
        finally:
            if old_provider is not None:
                os.environ["VECTOR_STORE_PROVIDER"] = old_provider
            if old_collection is not None:
                os.environ["QDRANT_COLLECTION"] = old_collection

    def test_load_dotenv_file_does_not_override_existing_environment(self) -> None:
        with TemporaryDirectory() as temp_dir:
            env_path = Path(temp_dir) / ".env"
            env_path.write_text(
                "\n".join(
                    [
                        "VECTOR_STORE_PROVIDER=qdrant",
                        "QDRANT_URL=https://example.qdrant.tech",
                        "QDRANT_API_KEY=from_file",
                    ]
                ),
                encoding="utf-8",
            )

            old_values = {
                key: os.environ.get(key)
                for key in ["VECTOR_STORE_PROVIDER", "QDRANT_URL", "QDRANT_API_KEY"]
            }
            os.environ["QDRANT_API_KEY"] = "from_environment"
            try:
                load_dotenv_file(env_path)

                self.assertEqual(os.environ["VECTOR_STORE_PROVIDER"], "qdrant")
                self.assertEqual(os.environ["QDRANT_URL"], "https://example.qdrant.tech")
                self.assertEqual(os.environ["QDRANT_API_KEY"], "from_environment")
            finally:
                for key, value in old_values.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value


if __name__ == "__main__":
    unittest.main()
