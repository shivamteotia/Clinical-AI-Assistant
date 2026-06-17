from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class TaskQueueSettings:
    provider: str
    broker_url: str | None
    result_backend: str | None

    @property
    def enabled(self) -> bool:
        return self.provider == "celery"


def get_task_queue_settings() -> TaskQueueSettings:
    provider = os.getenv("TASK_QUEUE_PROVIDER", "local").strip().lower()
    return TaskQueueSettings(
        provider=provider,
        broker_url=os.getenv("CELERY_BROKER_URL"),
        result_backend=os.getenv("CELERY_RESULT_BACKEND"),
    )


def task_queue_status() -> dict[str, Any]:
    settings = get_task_queue_settings()
    return {
        "provider": settings.provider,
        "enabled": settings.enabled,
        "broker_url_configured": bool(settings.broker_url),
        "result_backend_configured": bool(settings.result_backend),
    }


def celery_is_available() -> bool:
    try:
        import celery  # noqa: F401
    except ImportError:
        return False
    return True


def enqueue_journey_refresh_task(event: dict[str, Any]) -> dict[str, Any]:
    settings = get_task_queue_settings()
    if not settings.enabled:
        return {"queued": False, "provider": settings.provider, "task_id": None}
    if not celery_is_available():
        raise RuntimeError("Celery task queue is configured but celery is not installed.")

    from app.worker import process_journey_refresh_event

    task = process_journey_refresh_event.delay(event)
    return {
        "queued": True,
        "provider": settings.provider,
        "task_id": task.id,
    }
