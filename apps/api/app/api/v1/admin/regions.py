from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.v1.responses import PROBLEMS
from app.core.deps import ContainerDep, SessionDep
from app.schemas import admin as dto
from app.services.admin_config_service import AdminConfigService
from app.services.admin_ingestion_service import AdminIngestionService
from app.services.audit import AuditDep

router = APIRouter(prefix="/regions", tags=["admin:regions"])


def config_service(container: ContainerDep, session: SessionDep, audit: AuditDep) -> AdminConfigService:
    return AdminConfigService(session, container.cache, audit)


def ingestion_service(container: ContainerDep, session: SessionDep, audit: AuditDep) -> AdminIngestionService:
    return AdminIngestionService(container.settings, session, audit)


ConfigSvc = Annotated[AdminConfigService, Depends(config_service)]
IngestionSvc = Annotated[AdminIngestionService, Depends(ingestion_service)]


@router.get("", response_model=dto.AdminRegionList)
async def list_regions(svc: ConfigSvc) -> dto.AdminRegionList:
    return await svc.list_regions()


@router.post("", response_model=dto.AdminRegionOut, status_code=201, responses=PROBLEMS(409, 422))
async def create_region(body: dto.RegionIn, svc: ConfigSvc) -> dto.AdminRegionOut:
    return await svc.create_region(body)


@router.patch("/{slug}", response_model=dto.AdminRegionOut, responses=PROBLEMS(404, 422))
async def patch_region(slug: str, body: dto.RegionPatch, svc: ConfigSvc) -> dto.AdminRegionOut:
    return await svc.patch_region(slug, body)


@router.post(
    "/{slug}/collect",
    response_model=list[dto.IngestionJobOut],
    status_code=202,
    responses=PROBLEMS(404, 422),
    summary="수집 잡 트리거 (provider별 1건)",
)
async def collect(slug: str, body: dto.CollectRequest, svc: IngestionSvc) -> list[dto.IngestionJobOut]:
    return await svc.create_jobs(slug, body.providers, body.job_type, mark_collecting=True)


@router.post("/{slug}/activate", response_model=dto.AdminRegionOut, responses=PROBLEMS(404, 409))
async def activate(slug: str, svc: ConfigSvc) -> dto.AdminRegionOut:
    return await svc.activate_region(slug)
