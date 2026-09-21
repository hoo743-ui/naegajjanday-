from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Response

from app.api.v1.responses import PROBLEMS
from app.core.deps import SessionDep
from app.schemas import admin as dto
from app.services.admin_content_service import AdminContentService
from app.services.audit import AuditDep

router = APIRouter(prefix="/events", tags=["admin:events"])


def service(session: SessionDep, audit: AuditDep) -> AdminContentService:
    return AdminContentService(session, audit)


Svc = Annotated[AdminContentService, Depends(service)]


@router.get("", response_model=dto.AdminEventList)
async def list_events(svc: Svc, region: str | None = None, status: str | None = None) -> dto.AdminEventList:
    return await svc.list_events(region, status)


@router.post("", response_model=dto.AdminEventOut, status_code=201, responses=PROBLEMS(404, 422))
async def create_event(body: dto.EventIn, svc: Svc) -> dto.AdminEventOut:
    return await svc.create_event(body)


@router.patch("/{event_id}", response_model=dto.AdminEventOut, responses=PROBLEMS(404, 422))
async def patch_event(event_id: str, body: dto.EventPatch, svc: Svc) -> dto.AdminEventOut:
    return await svc.patch_event(event_id, body)


@router.delete("/{event_id}", status_code=204, responses=PROBLEMS(404))
async def delete_event(event_id: str, svc: Svc) -> Response:
    await svc.delete_event(event_id)
    return Response(status_code=204)
