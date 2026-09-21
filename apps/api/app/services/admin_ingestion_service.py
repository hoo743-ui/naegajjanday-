"""Admin: ingestion jobs. Jobs are queued rows; a Celery worker executes them when a broker is
configured, otherwise `python -m app.cli ingest-job <id>` (or the retry endpoint later) runs them."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import errors
from app.core.config import Settings
from app.core.logging import get_logger
from app.infra.db.base import as_utc, utcnow
from app.infra.db.models import IngestionJob, Region
from app.infra.ingestion.registry import ALL_PROVIDERS, API_PROVIDERS
from app.schemas import admin as dto
from app.schemas.common import decode_cursor, encode_cursor
from app.services.audit import AuditLogger

logger = get_logger(__name__)


def job_out(job: IngestionJob, region_slug: str | None) -> dto.IngestionJobOut:
    return dto.IngestionJobOut(
        id=job.id, provider=job.provider, region=region_slug, job_type=job.job_type, status=job.status,
        fetched_count=job.fetched_count or 0, created_count=job.created_count or 0,
        updated_count=job.updated_count or 0, failed_count=job.failed_count or 0, error=job.error,
        started_at=as_utc(job.started_at), finished_at=as_utc(job.finished_at),
        created_at=as_utc(job.created_at) or utcnow(),
    )  # fmt: skip


def enqueue(settings: Settings, job_id: int) -> bool:
    """Hand the job to Celery when a broker is configured. Returns False when it stays queued."""
    if not settings.celery_broker_url:
        return False
    from app.workers.tasks import run_ingestion_job

    run_ingestion_job.delay(job_id)
    return True


class AdminIngestionService:
    def __init__(self, settings: Settings, session: AsyncSession, audit: AuditLogger) -> None:
        self._settings = settings
        self._s = session
        self._audit = audit

    async def list_jobs(self, status: str | None, cursor: str | None, limit: int) -> dto.IngestionJobList:
        stmt = select(IngestionJob).order_by(IngestionJob.id.desc())
        if status:
            stmt = stmt.where(IngestionJob.status == status)
        if (after := decode_cursor(cursor)) is not None:
            stmt = stmt.where(IngestionJob.id < after)
        rows = (await self._s.scalars(stmt.limit(limit + 1))).all()
        slugs = {i: s for i, s in (await self._s.execute(select(Region.id, Region.slug))).all()}
        page = rows[:limit]
        return dto.IngestionJobList(
            items=[job_out(j, slugs.get(j.region_id or -1)) for j in page],
            next_cursor=encode_cursor(page[-1].id) if len(rows) > limit and page else None,
        )

    async def create_jobs(
        self, region_slug: str, providers: list[str], job_type: str, *, mark_collecting: bool = False
    ) -> list[dto.IngestionJobOut]:
        region = await self._s.scalar(select(Region).where(Region.slug == region_slug))
        if region is None:
            raise errors.RegionNotFound()
        allowed = API_PROVIDERS if mark_collecting else ALL_PROVIDERS
        unknown = [p for p in providers if p not in allowed or p == "file"]
        if unknown:
            raise errors.ValidationFailed(
                f"사용할 수 없는 provider: {', '.join(unknown)} (가능: {', '.join(API_PROVIDERS)}; "
                "파일은 POST /admin/places/import 를 사용하세요)"
            )
        jobs = [
            IngestionJob(provider=p, region_id=region.id, job_type=job_type, params={}) for p in providers
        ]
        self._s.add_all(jobs)
        if mark_collecting and region.status == "draft":
            region.status = "collecting"
        await self._s.flush()
        for job in jobs:
            self._audit.record(
                "ingestion_job.create",
                "ingestion_job",
                job.id,
                {"provider": job.provider, "region": region_slug},
            )
        await self._s.commit()
        for job in jobs:
            dispatched = enqueue(self._settings, job.id)
            logger.info("ingestion.job_created", job_id=job.id, provider=job.provider, dispatched=dispatched)
        return [job_out(j, region_slug) for j in jobs]

    async def retry(self, job_id: int) -> dto.IngestionJobOut:
        job = await self._s.get(IngestionJob, job_id)
        if job is None:
            raise errors.NotFound("수집 잡을 찾을 수 없어요.")
        if job.status in {"queued", "running"}:
            raise errors.Conflict("이미 대기 중이거나 실행 중인 잡이에요.")
        job.status, job.error, job.started_at, job.finished_at = "queued", None, None, None
        self._audit.record("ingestion_job.retry", "ingestion_job", job.id, {})
        await self._s.commit()
        enqueue(self._settings, job.id)
        region = await self._s.get(Region, job.region_id) if job.region_id else None
        return job_out(job, region.slug if region else None)
