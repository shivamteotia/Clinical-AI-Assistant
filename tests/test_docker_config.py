import unittest
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]


class DockerConfigTests(unittest.TestCase):
    def test_dockerfile_defines_fastapi_runtime(self) -> None:
        dockerfile = (BASE_DIR / "Dockerfile").read_text(encoding="utf-8")

        self.assertIn("FROM python:3.12-slim", dockerfile)
        self.assertIn("COPY requirements.txt", dockerfile)
        self.assertIn("uvicorn", dockerfile)
        self.assertIn("python scripts/seed_data.py", dockerfile)
        self.assertIn("app.main:app", dockerfile)
        self.assertNotIn("GROQ_API_KEY", dockerfile)
        self.assertNotIn("QDRANT_API_KEY", dockerfile)

    def test_docker_compose_has_app_and_optional_qdrant_profile(self) -> None:
        compose = (BASE_DIR / "docker-compose.yml").read_text(encoding="utf-8")

        self.assertIn("services:", compose)
        self.assertIn("app:", compose)
        self.assertIn("env_file:", compose)
        self.assertIn("./data:/app/data", compose)
        self.assertNotIn("./his.db:/app/his.db", compose)
        self.assertNotIn("./vector_store.db:/app/vector_store.db", compose)
        self.assertIn("healthcheck:", compose)
        self.assertIn("qdrant/qdrant", compose)
        self.assertIn("local-qdrant", compose)
        self.assertNotIn("replace_with_your", compose)

    def test_dockerignore_excludes_local_state_and_credentials(self) -> None:
        dockerignore = (BASE_DIR / ".dockerignore").read_text(encoding="utf-8")

        self.assertIn(".env", dockerignore)
        self.assertIn(".venv", dockerignore)
        self.assertIn("*.db", dockerignore)
        self.assertIn("data/journey_runs.jsonl", dockerignore)
        self.assertIn("data/audit_logs.jsonl", dockerignore)


if __name__ == "__main__":
    unittest.main()
