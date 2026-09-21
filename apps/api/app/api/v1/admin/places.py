from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Query, UploadFile

from app.api.v1.responses import PROBLEMS
from app.core import errors
from app.core.deps import ContainerDep, SessionDep
from app.schemas import admin as dto
from app.services.admin_place_service import AdminPlaceService
from app.services.audit import AuditDep

router = APIRouter(prefix="/places", tags=["admin:places"])

MAX_IMPORT_BYTES = 10 * 1024 * 1024


def service(container: ContainerDep, session: SessionDep, audit: AuditDep) -> AdminPlaceService:
    return AdminPlaceService(container.settings, session, audit)


Svc = Annotated[AdminPlaceService, Depends(service)]


@router.get("", response_model=dto.AdminPlaceList, summary="장소 목록 (status=pending 승인 큐)")
async def list_places(
    svc: Svc,
    status: dto.PlaceStatus | None = None,
    region: str | None = None,
    q: str | None = Query(default=None, max_length=50),
    cursor: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
) -> dto.AdminPlaceList:
    return await svc.list(status, region, q, cursor, limit)


@router.post(
    "",
    response_model=dto.AdminPlaceOut,
    status_code=201,
    responses=PROBLEMS(404, 422),
    summary="관광지 등 직접 추가",
)
async def create_place(body: dto.AdminPlaceCreate, svc: Svc) -> dto.AdminPlaceOut:
    return await svc.create(body)


@router.post("/bulk-approve", response_model=dto.BulkResult)
async def bulk_approve(body: dto.BulkApproveRequest, svc: Svc) -> dto.BulkResult:
    return await svc.bulk_approve(body.ids)


@router.post(
    "/import",
    response_model=dto.IngestionJobOut,
    responses=PROBLEMS(404, 422),
    summary="CSV/JSON 업로드 → file provider 수집 잡",
)
async def import_places(svc: Svc, file: UploadFile, region: Annotated[str, Form()]) -> dto.IngestionJobOut:
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in {".json", ".csv"}:
        raise errors.ValidationFailed(".json 또는 .csv 파일만 올릴 수 있어요.")
    data = await file.read(MAX_IMPORT_BYTES + 1)
    if len(data) > MAX_IMPORT_BYTES:
        raise errors.ValidationFailed("파일이 너무 커요 (최대 10MB).")
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / f"upload{suffix}"
        path.write_bytes(data)
        return await svc.import_file(path, region)


@router.patch("/{place_id}", response_model=dto.AdminPlaceOut, responses=PROBLEMS(404, 422))
async def patch_place(place_id: str, body: dto.AdminPlacePatch, svc: Svc) -> dto.AdminPlaceOut:
    return await svc.patch(place_id, body)


@router.post("/{place_id}/approve", response_model=dto.AdminPlaceOut, responses=PROBLEMS(404))
async def approve(place_id: str, svc: Svc, body: dto.ModerationNote | None = None) -> dto.AdminPlaceOut:
    return await svc.set_status(place_id, "approved", "approve", body.note if body else None)


@router.post("/{place_id}/reject", response_model=dto.AdminPlaceOut, responses=PROBLEMS(404))
async def reject(place_id: str, svc: Svc, body: dto.ModerationNote | None = None) -> dto.AdminPlaceOut:
    return await svc.set_status(place_id, "rejected", "reject", body.note if body else None)


@router.post(
    "/{place_id}/merge", response_model=dto.AdminPlaceOut, responses=PROBLEMS(404, 422), summary="중복 병합"
)
async def merge(place_id: str, body: dto.MergeRequest, svc: Svc) -> dto.AdminPlaceOut:
    return await svc.merge(place_id, body)


@router.get("/{place_id}/revisions", response_model=dto.RevisionList, responses=PROBLEMS(404))
async def revisions(place_id: str, svc: Svc) -> dto.RevisionList:
    return await svc.revisions(place_id)
