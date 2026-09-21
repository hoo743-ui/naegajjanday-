"""Batch tasks. Each task opens its own engine: Celery prefork workers must not share event loops."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.domain.recommendation.features import recency_weighted_sentiment
from app.infra.db.base import as_utc, utcnow
from app.infra.db.models import Category, Place, PlaceStats, Region, Review
from app.infra.db.session import Database
from app.infra.ingestion.registry import API_PROVIDERS
from app.infra.ingestion.stats import refresh_region_stats
from app.infra.llm.base import LLMError, LLMMessage, LLMRequest
from app.infra.llm.factory import build_llm
from app.infra.search.client import build_search
from app.infra.search.outbox import drain_outbox
from app.prompts.loader import PromptLoader
from app.services import retention_service as retention
from app.services.ingestion_runner import ingest, run_job
from app.workers.celery_app import celery_app

logger = get_logger(__name__)

REVIEW_BATCH = 20
MAX_REVIEW_BATCHES = 50


def _run[T](fn: Callable[[Database, Settings], Awaitable[T]]) -> T:
    async def main() -> T:
        settings = get_settings()
        db = Database(settings)
        try:
            return await fn(db, settings)
        finally:
            await db.dispose()

    return asyncio.run(main())


@celery_app.task(
    name="app.workers.tasks.ingest_region",
    autoretry_for=(ConnectionError,),
    max_retries=3,
    retry_backoff=True,
)
def ingest_region(provider: str, region_slug: str) -> dict[str, Any]:
    async def job(db: Database, settings: Settings) -> dict[str, Any]:
        _, report = await ingest(db, settings, provider_name=provider, region_slug=region_slug)
        return {
            "fetched": report.fetched,
            "created": report.created,
            "updated": report.updated,
            "failed": report.failed,
        }

    return _run(job)


@celery_app.task(name="app.workers.tasks.run_ingestion_job")
def run_ingestion_job(job_id: int) -> dict[str, Any]:
    async def job(db: Database, settings: Settings) -> dict[str, Any]:
        report = await run_job(db, settings, job_id)
        return {
            "fetched": report.fetched,
            "created": report.created,
            "updated": report.updated,
            "failed": report.failed,
        }

    return _run(job)


@celery_app.task(name="app.workers.tasks.ingest_active_regions")
def ingest_active_regions() -> int:
    """Fan out one task per (configured provider × active hotspot region)."""

    async def job(db: Database, settings: Settings) -> int:
        configured = [p for p in API_PROVIDERS if _has_key(settings, p)]
        async with db.sessionmaker() as s:
            slugs = (
                await s.scalars(select(Region.slug).where(Region.status == "active", Region.level == 3))
            ).all()
        for slug in slugs:
            for provider in configured:
                ingest_region.delay(provider, slug)
        return len(slugs) * len(configured)

    return _run(job)


def _has_key(settings: Settings, provider: str) -> bool:
    return bool(
        {
            "kakao_local": settings.kakao_rest_api_key,
            "naver_search": settings.naver_search_client_id and settings.naver_search_client_secret,
            "google_places": settings.google_places_api_key,
            "tourapi": settings.tourapi_service_key,
            "data_go_kr": settings.data_go_kr_service_key,
        }.get(provider)
    )


@celery_app.task(name="app.workers.tasks.refresh_stats")
def refresh_stats() -> int:
    """Bayesian ratings + popularity (recommend/save signals, log-scaled to 0~1 per region)."""

    async def job(db: Database, _settings: Settings) -> int:
        total = 0
        async with db.sessionmaker() as s:
            for region_id in (await s.scalars(select(Region.id))).all():
                total += await refresh_region_stats(s, region_id)
                rows = (
                    await s.scalars(
                        select(PlaceStats)
                        .join(Place, Place.id == PlaceStats.place_id)
                        .where(Place.region_id == region_id)
                    )
                ).all()
                raw = {r.place_id: (r.recommend_count or 0) + 3 * (r.save_count or 0) for r in rows}
                top = max(raw.values(), default=0)
                for r in rows:
                    r.popularity = round(_log_scale(raw[r.place_id], top), 4)
            await s.commit()
        return total

    return _run(job)


def _log_scale(value: int, top: int) -> float:
    import math

    return math.log1p(value) / math.log1p(top) if top > 0 else 0.0


@celery_app.task(name="app.workers.tasks.sync_search_index")
def sync_search_index() -> dict[str, int]:
    async def job(db: Database, settings: Settings) -> dict[str, int]:
        search = build_search(settings)
        if search is None:
            return {"processed": 0, "failed": 0}  # ES_URL unset: SQL fallback search needs no index
        try:
            await search.ensure_index()
            async with db.sessionmaker() as s:
                return await drain_outbox(s, search)
        finally:
            await search.aclose()

    return _run(job)


@celery_app.task(name="app.workers.tasks.analyze_reviews")
def analyze_reviews() -> dict[str, int]:
    """Batch review sentiment with the FAST model tier, then aggregate into place_stats.

    Only reviews whose provider terms allow storing text exist in `review`; the LLM output is a
    per-review sentiment/aspect value — it never touches place scores directly.
    """

    async def job(db: Database, settings: Settings) -> dict[str, int]:
        llm = build_llm(settings)
        if not llm.available:
            logger.info("analyze_reviews.skipped", reason="no LLM provider configured")
            return {"analyzed": 0, "places": 0}
        prompt = PromptLoader().get("review_sentiment")
        analyzed = 0
        touched: set[int] = set()
        async with db.sessionmaker() as s:
            for _ in range(MAX_REVIEW_BATCHES):
                rows = (
                    await s.execute(
                        select(Review, Category.name)
                        .join(Place, Place.id == Review.place_id)
                        .join(Category, Category.id == Place.category_id)
                        .where(Review.analyzed_at.is_(None), Review.content.is_not(None))
                        .order_by(Review.place_id, Review.id)
                        .limit(REVIEW_BATCH)
                    )
                ).all()
                if not rows:
                    break
                rendered = prompt.render(
                    category=rows[0][1], reviews=[{"id": str(r.id), "content": r.content} for r, _ in rows]
                )
                try:
                    data = await llm.complete_json(
                        LLMRequest(
                            system=rendered.system,
                            messages=[LLMMessage(role="user", content=rendered.user)],
                            tier="fast",
                            max_tokens=rendered.max_tokens,
                            json_schema=rendered.output_schema,
                        )
                    )
                except LLMError as exc:
                    logger.warning("analyze_reviews.llm_failed", error=str(exc))
                    break
                by_id = {str(item.get("id")): item for item in data.get("results", [])}
                for review, _cat in rows:
                    item = by_id.get(str(review.id))
                    review.analyzed_at = utcnow()  # never re-send a review the model skipped
                    review.model_version = f"{llm.model_for('fast')}|{prompt.ref}"
                    if item is None:
                        continue
                    review.sentiment = max(-1.0, min(1.0, float(item["sentiment"])))
                    review.aspects = {
                        k: max(0.0, min(1.0, float(v))) for k, v in (item.get("aspects") or {}).items()
                    }
                    analyzed += 1
                    touched.add(review.place_id)
                await s.commit()
            await _aggregate_sentiment(s, touched)
            await s.commit()
        return {"analyzed": analyzed, "places": len(touched)}

    return _run(job)


@celery_app.task(name="app.workers.tasks.purge_courses")
def purge_courses() -> dict[str, Any]:
    """Never-saved courses older than `unsaved_course_ttl_hours` (same job as `cli purge-courses`)."""
    return _run(lambda db, settings: retention.purge_unsaved_courses(db, settings)).as_dict()


@celery_app.task(name="app.workers.tasks.purge_accounts")
def purge_accounts() -> dict[str, Any]:
    """Accounts past the deletion grace period (same job as `cli purge-accounts`)."""
    return _run(lambda db, settings: retention.purge_deleted_accounts(db, settings)).as_dict()


async def _aggregate_sentiment(session: Any, place_ids: set[int]) -> None:
    now = datetime.now(UTC)
    for place_id in place_ids:
        reviews = (
            await session.scalars(
                select(Review).where(Review.place_id == place_id, Review.sentiment.is_not(None))
            )
        ).all()
        items = [(r.sentiment, as_utc(r.written_at) or now) for r in reviews]
        stats = await session.get(PlaceStats, place_id)
        if stats is None or not items:
            continue
        stats.sentiment_score = recency_weighted_sentiment(items, now)  # half-life 180 d
        stats.sentiment_count = len(items)
        sums: dict[str, list[float]] = {}
        for r in reviews:
            for key, value in (r.aspects or {}).items():
                sums.setdefault(key, []).append(float(value))
        stats.aspect_scores = {k: round(sum(v) / len(v), 3) for k, v in sums.items()}


__all__ = [
    "analyze_reviews",
    "func",
    "ingest_active_regions",
    "ingest_region",
    "purge_accounts",
    "purge_courses",
    "refresh_stats",
    "run_ingestion_job",
    "sync_search_index",
]
