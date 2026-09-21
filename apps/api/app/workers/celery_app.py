"""Celery app + beat schedule. Start with:
celery -A app.workers.celery_app worker -l info
celery -A app.workers.celery_app beat -l info
"""

from __future__ import annotations

from celery import Celery
from celery.schedules import crontab

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "naegajjanday",
    broker=settings.celery_broker_url or settings.redis_url or "memory://",
    backend=settings.celery_result_backend or settings.redis_url or "cache+memory://",
    include=["app.workers.tasks"],
)
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone=settings.timezone,
    enable_utc=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_time_limit=60 * 30,
    task_soft_time_limit=60 * 25,
    task_default_queue="default",
    task_routes={
        "app.workers.tasks.ingest_region": {"queue": "ingestion"},
        "app.workers.tasks.run_ingestion_job": {"queue": "ingestion"},
        "app.workers.tasks.analyze_reviews": {"queue": "llm"},
    },
    beat_schedule={
        "sync-search-index": {"task": "app.workers.tasks.sync_search_index", "schedule": 60.0},
        "refresh-stats-nightly": {
            "task": "app.workers.tasks.refresh_stats",
            "schedule": crontab(hour=4, minute=0),
        },
        "analyze-reviews-nightly": {
            "task": "app.workers.tasks.analyze_reviews",
            "schedule": crontab(hour=4, minute=30),
        },
        "ingest-active-regions-weekly": {
            "task": "app.workers.tasks.ingest_active_regions",
            "schedule": crontab(hour=3, minute=0, day_of_week="mon"),
        },
    },
)

app = celery_app  # `celery -A app.workers.celery_app` finds either name
