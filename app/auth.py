from __future__ import annotations

from dataclasses import dataclass
from secrets import compare_digest

from fastapi import HTTPException, Request, status

from app.rag.config import load_dotenv_file
import os


@dataclass(frozen=True)
class AuthSettings:
    doctor_api_key: str | None
    admin_api_key: str | None

    @property
    def enabled(self) -> bool:
        return bool(self.doctor_api_key or self.admin_api_key)


def get_auth_settings() -> AuthSettings:
    load_dotenv_file()
    return AuthSettings(
        doctor_api_key=os.getenv("CLINICAL_AI_DOCTOR_API_KEY") or None,
        admin_api_key=os.getenv("CLINICAL_AI_ADMIN_API_KEY") or None,
    )


def actor_from_request(request: Request) -> str:
    return request.headers.get("x-user-id") or "local_doctor"


def require_role(request: Request, role: str) -> str:
    settings = get_auth_settings()
    actor = actor_from_request(request)
    if not settings.enabled:
        return actor

    supplied_key = request.headers.get("x-api-key") or ""
    if role == "doctor":
        if _matches(supplied_key, settings.doctor_api_key) or _matches(supplied_key, settings.admin_api_key):
            return actor
    elif role == "admin":
        if _matches(supplied_key, settings.admin_api_key):
            return actor
    else:
        raise ValueError(f"Unsupported role: {role}")

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Valid API key with required role is required.",
    )


def require_doctor(request: Request) -> str:
    return require_role(request, "doctor")


def require_admin(request: Request) -> str:
    return require_role(request, "admin")


def _matches(supplied_key: str, expected_key: str | None) -> bool:
    if not supplied_key or not expected_key:
        return False
    return compare_digest(supplied_key, expected_key)
