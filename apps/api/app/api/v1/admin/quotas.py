"""외부 API 한도 대비 사용량 (docs/47) — 관리자 알림 종이 읽는다."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.core.deps import SessionDep
from app.infra import api_usage

router = APIRouter(tags=["admin:system"])


class QuotaOut(BaseModel):
    provider: str
    name: str
    period: str
    used: int
    limit: int | None
    share: float | None
    errors_today: int
    status: str  # ok | warn | critical | exhausted | unknown
    verified: bool
    where: str
    note: str


class QuotaList(BaseModel):
    items: list[QuotaOut]


@router.get("/quotas", response_model=QuotaList, summary="외부 API 한도 대비 사용량 (80% 넘으면 warn)")
async def quotas(session: SessionDep) -> QuotaList:
    return QuotaList(items=[QuotaOut.model_validate(r) for r in await api_usage.report(session)])
