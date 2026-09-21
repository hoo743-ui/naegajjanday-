from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.admin.regions import ConfigSvc
from app.api.v1.responses import PROBLEMS
from app.schemas import admin as dto

router = APIRouter(prefix="/templates", tags=["admin:templates"])


@router.get("", response_model=dto.TemplateList, responses=PROBLEMS(404))
async def list_templates(svc: ConfigSvc, purpose: str | None = None) -> dto.TemplateList:
    return await svc.list_templates(purpose)


@router.post("", response_model=dto.TemplateOut, status_code=201, responses=PROBLEMS(404, 409, 422))
async def create_template(body: dto.TemplateIn, svc: ConfigSvc) -> dto.TemplateOut:
    return await svc.create_template(body)


@router.patch("/{code}", response_model=dto.TemplateOut, responses=PROBLEMS(404, 422))
async def patch_template(code: str, body: dto.TemplatePatch, svc: ConfigSvc) -> dto.TemplateOut:
    return await svc.patch_template(code, body)
