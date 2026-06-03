import unittest
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]


class CiConfigTests(unittest.TestCase):
    def test_github_actions_ci_workflow_exists(self) -> None:
        workflow = BASE_DIR / ".github" / "workflows" / "ci.yml"

        self.assertTrue(workflow.exists())

        content = workflow.read_text(encoding="utf-8")
        self.assertIn("actions/checkout@v4", content)
        self.assertIn("actions/setup-python@v5", content)
        self.assertIn("python-version: \"3.12\"", content)
        self.assertIn("pip install -r requirements.txt", content)
        self.assertIn("python scripts/seed_data.py", content)
        self.assertIn("python -m unittest discover", content)
        self.assertIn("Secret pattern scan", content)
        self.assertIn("VECTOR_STORE_PROVIDER: sqlite", content)


if __name__ == "__main__":
    unittest.main()
