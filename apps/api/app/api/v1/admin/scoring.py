from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.admin.regions import ConfigSvc
from app.api.v1.responses import PROBLEMS
from app.schemas import admin as dto

router = APIRouter(tags=["admin:scoring"])


@router.get("/scoring-profiles/{purpose}", response_model=dto.ScoringProfileOut, responses=PROBLEMS(404))
async def get_profile(purpose: str, svc: ConfigSvc) -> dto.ScoringProfileOut:
    return await svc.get_profile(purpose)


@router.put(
    "/scoring-profiles/{purpose}",
    response_model=dto.ScoringProfileOut,
    responses=PROBLEMS(404, 422),
    summary="가중치·파라미터 수정 (버전 +1, 코드 배포 없음)",
)
async def put_profile(purpose: str, body: dto.ScoringProfileBody, svc: ConfigSvc) -> dto.ScoringProfileOut:
    return await svc.put_profile(purpose, body)


@router.get("/purposes/{code}/tag-affinities", response_model=dto.TagAffinitiesBody, responses=PROBLEMS(404))
async def get_affinities(code: str, svc: ConfigSvc) -> dto.TagAffinitiesBody:
    return await svc.get_affinities(code)


@router.put(
    "/purposes/{code}/tag-affinities", response_model=dto.TagAffinitiesBody, responses=PROBLEMS(404, 422)
)
async def put_affinities(code: str, body: dto.TagAffinitiesBody, svc: ConfigSvc) -> dto.TagAffinitiesBody:
    return await svc.put_affinities(code, body)
