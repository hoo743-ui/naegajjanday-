from __future__ import annotations

from fastapi import APIRouter, Query

from app.api.v1.admin.regions import IngestionSvc
from app.api.v1.responses import PROBLEMS
from app.schemas import admin as dto

router = APIRouter(prefix="/ingestion", tags=["admin:ingestion"])


@router.get("/jobs", response_model=dto.IngestionJobList)
async def list_jobs(
    svc: IngestionSvc,
    status: str | None = None,
    cursor: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
) -> dto.IngestionJobList:
    return await svc.list_jobs(status, cursor, limit)


@router.post("/jobs", response_model=dto.IngestionJobOut, status_code=202, responses=PROBLEMS(404, 422))
async def create_job(body: dto.IngestionJobIn, svc: IngestionSvc) -> dto.IngestionJobOut:
    return (await svc.create_jobs(body.region, [body.provider], body.job_type))[0]


@router.post(
    "/jobs/{job_id}/retry", response_model=dto.IngestionJobOut, status_code=202, responses=PROBLEMS(404, 409)
)
async def retry_job(job_id: int, svc: IngestionSvc) -> dto.IngestionJobOut:
    return await svc.retry(job_id)
