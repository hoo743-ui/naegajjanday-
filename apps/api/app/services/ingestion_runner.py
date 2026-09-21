"""Runs ingestion outside the request path (CLI, Celery). One code path for every provider."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import select

from app.core.config import Settings
from app.infra.db.models import IngestionJob, Region
from app.infra.db.session import Database
from app.infra.ingestion.pipeline import IngestionPipeline, IngestionReport
from app.infra.ingestion.providers.file_provider import FileProvider
from app.infra.ingestion.registry import build_provider


class IngestionError(RuntimeError):
    pass


async def ingest(
    db: Database, settings: Settings, *, provider_name: str, region_slug: str | None, path: Path | None = None
) -> tuple[str, IngestionReport]:
    provider = build_provider(provider_name, settings, path=path)
    slug = region_slug or (provider.region_slug if isinstance(provider, FileProvider) else None)
    if not slug:
        raise IngestionError("region is required (pass --region or put a 'region' key in the file)")
    async with db.sessionmaker() as session:
        region = await session.scalar(select(Region).where(Region.slug == slug))
        if region is None:
            raise IngestionError(
                f"unknown region '{slug}' — add it to regions.json and run seed-config first"
            )
        job = IngestionJob(provider=provider_name, region_id=region.id, job_type="full", params={})
        if path is not None:
            job.params = {"filename": path.name}
        session.add(job)
        await session.flush()
        report = await IngestionPipeline(session, settings.trusted_providers).run(provider, region, job)
        await session.commit()
    close = getattr(provider, "aclose", None)
    if close is not None:
        await close()
    return slug, report


async def run_job(db: Database, settings: Settings, job_id: int) -> IngestionReport:
    """Execute a queued `ingestion_job` row (created by the admin API)."""
    async with db.sessionmaker() as session:
        job = await session.get(IngestionJob, job_id)
        if job is None:
            raise IngestionError(f"ingestion_job {job_id} not found")
        region = await session.get(Region, job.region_id) if job.region_id else None
        if region is None:
            raise IngestionError(f"ingestion_job {job_id} has no region")
        try:
            provider = build_provider(job.provider, settings)
        except Exception as exc:  # missing API key etc. → visible on the job row
            job.status, job.error = "failed", str(exc)
            await session.commit()
            raise IngestionError(str(exc)) from exc
        report = await IngestionPipeline(session, settings.trusted_providers).run(provider, region, job)
        await session.commit()
    close = getattr(provider, "aclose", None)
    if close is not None:
        await close()
    return report
