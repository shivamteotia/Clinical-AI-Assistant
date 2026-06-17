from __future__ import annotations

import os
from typing import Any

try:
    from celery import Celery
except ImportError:  # pragma: no cover - runtime guard for local JSON-only installs
    Celery = None

DEFAULT_BROKER_URL = "redis://redis:6379/0"
DEFAULT_RESULT_BACKEND = "redis://redis:6379/1"


def create_celery_app():
    if Celery is None:
        raise RuntimeError("Celery is not installed. Install project requirements.")
    app = Celery(
        "clinical_ai_system",
        broker=os.getenv("CELERY_BROKER_URL", DEFAULT_BROKER_URL),
        backend=os.getenv("CELERY_RESULT_BACKEND", DEFAULT_RESULT_BACKEND),
    )
    app.conf.update(
        task_default_queue="patient_journeys",
        task_track_started=True,
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
        worker_prefetch_multiplier=1,
    )
    return app


celery_app = create_celery_app() if Celery is not None else None


if celery_app is not None:

    @celery_app.task(
        name="patient_journeys.process_refresh_event",
        bind=True,
        autoretry_for=(RuntimeError, TimeoutError, OSError),
        retry_backoff=True,
        retry_kwargs={"max_retries": 3},
    )
    def process_journey_refresh_event(self, event: dict[str, Any]) -> dict[str, Any]:
        from app.rag.journey_refresh import refresh_patient_journey

        metadata = event.get("metadata", {})
        return refresh_patient_journey(
            event["patient_id"],
            actor=event.get("actor") or "celery_worker",
            use_llm=metadata.get("use_llm", True),
            provider=metadata.get("provider"),
            model=metadata.get("model"),
            require_llm=metadata.get("require_llm", False),
            reason=event.get("reason") or "celery_refresh",
            queued_event=event,
        )
