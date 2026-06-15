import os
import unittest
from contextlib import redirect_stdout
from io import StringIO

from fastapi.testclient import TestClient

from app.main import app
from scripts.seed_data import main as seed_data


class AuthTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        os.environ["VECTOR_STORE_PROVIDER"] = "sqlite"
        with redirect_stdout(StringIO()):
            seed_data()
        cls.client = TestClient(app)

    def setUp(self) -> None:
        self.previous_doctor = os.environ.get("CLINICAL_AI_DOCTOR_API_KEY")
        self.previous_admin = os.environ.get("CLINICAL_AI_ADMIN_API_KEY")
        os.environ["CLINICAL_AI_DOCTOR_API_KEY"] = "doctor-test-key"
        os.environ["CLINICAL_AI_ADMIN_API_KEY"] = "admin-test-key"

    def tearDown(self) -> None:
        if self.previous_doctor is None:
            os.environ.pop("CLINICAL_AI_DOCTOR_API_KEY", None)
        else:
            os.environ["CLINICAL_AI_DOCTOR_API_KEY"] = self.previous_doctor
        if self.previous_admin is None:
            os.environ.pop("CLINICAL_AI_ADMIN_API_KEY", None)
        else:
            os.environ["CLINICAL_AI_ADMIN_API_KEY"] = self.previous_admin

    def test_health_stays_public_when_auth_enabled(self) -> None:
        response = self.client.get("/health")

        self.assertEqual(response.status_code, 200)

    def test_doctor_endpoint_requires_doctor_or_admin_key(self) -> None:
        missing = self.client.get("/patients")
        doctor = self.client.get("/patients", headers={"x-api-key": "doctor-test-key"})
        admin = self.client.get("/patients", headers={"x-api-key": "admin-test-key"})

        self.assertEqual(missing.status_code, 403)
        self.assertEqual(doctor.status_code, 200)
        self.assertEqual(admin.status_code, 200)

    def test_admin_endpoint_rejects_doctor_key(self) -> None:
        missing = self.client.get("/audit/events")
        doctor = self.client.get("/audit/events", headers={"x-api-key": "doctor-test-key"})
        admin = self.client.get("/audit/events", headers={"x-api-key": "admin-test-key"})

        self.assertEqual(missing.status_code, 403)
        self.assertEqual(doctor.status_code, 403)
        self.assertEqual(admin.status_code, 200)

    def test_admin_status_endpoint_rejects_doctor_key(self) -> None:
        missing = self.client.get("/admin/status")
        doctor = self.client.get("/admin/status", headers={"x-api-key": "doctor-test-key"})
        admin = self.client.get("/admin/status", headers={"x-api-key": "admin-test-key"})

        self.assertEqual(missing.status_code, 403)
        self.assertEqual(doctor.status_code, 403)
        self.assertEqual(admin.status_code, 200)
        payload = admin.json()
        self.assertIn("auth", payload)
        self.assertIn("vector_store", payload)
        self.assertNotIn("admin-test-key", str(payload))
        self.assertNotIn("doctor-test-key", str(payload))
    def test_journey_feedback_accepts_doctor_or_admin_key(self) -> None:
        missing = self.client.post(
            "/patients/P001/journey/feedback",
            json={"feedback_type": "useful"},
        )
        doctor = self.client.post(
            "/patients/P001/journey/feedback",
            json={"feedback_type": "useful"},
            headers={"x-api-key": "doctor-test-key"},
        )
        admin = self.client.post(
            "/patients/P001/journey/feedback",
            json={"feedback_type": "useful"},
            headers={"x-api-key": "admin-test-key"},
        )

        self.assertEqual(missing.status_code, 403)
        self.assertEqual(doctor.status_code, 200)
        self.assertEqual(admin.status_code, 200)

    def test_journey_feedback_listing_requires_admin_key(self) -> None:
        doctor = self.client.get("/journey-feedback", headers={"x-api-key": "doctor-test-key"})
        admin = self.client.get("/journey-feedback", headers={"x-api-key": "admin-test-key"})

        self.assertEqual(doctor.status_code, 403)
        self.assertEqual(admin.status_code, 200)
    def test_admin_refresh_endpoint_rejects_doctor_key(self) -> None:
        response = self.client.post(
            "/patients/P001/journey/refresh",
            json={"use_llm": False},
            headers={"x-api-key": "doctor-test-key"},
        )

        self.assertEqual(response.status_code, 403)

    def test_auth_is_open_when_keys_are_unset(self) -> None:
        os.environ.pop("CLINICAL_AI_DOCTOR_API_KEY", None)
        os.environ.pop("CLINICAL_AI_ADMIN_API_KEY", None)

        response = self.client.get("/patients")

        self.assertEqual(response.status_code, 200)


if __name__ == "__main__":
    unittest.main()
