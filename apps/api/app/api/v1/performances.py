from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.v1.responses import PROBLEMS
from app.core.deps import ContainerDep, SessionDep, rate_limit
from app.infra.ingestion.providers.kopis import shared_client
from app.schemas import performance as dto
from app.services.performance_service import PerformanceService, PerformanceSource

router = APIRouter(tags=["performances"], dependencies=[Depends(rate_limit("read"))])


def performance_source(container: ContainerDep) -> PerformanceSource:
    """Process-wide client (= one response cache). Tests override this dependency with a fake."""
    return shared_client(container.settings.kopis_api_key)


def performance_service(
    session: SessionDep, source: Annotated[PerformanceSource, Depends(performance_source)]
) -> PerformanceService:
    return PerformanceService(session, source)


PerformanceServiceDep = Annotated[PerformanceService, Depends(performance_service)]


@router.get(
    "/performances",
    response_model=dto.PerformanceList,
    responses=PROBLEMS(422),
    summary="좌표 주변에서 그 시간대에 실제로 시작하는 공연 (KOPIS 공식 Open API)",
)
async def performances(
    service: PerformanceServiceDep,
    lat: Annotated[float, Query(ge=-90, le=90)],
    lng: Annotated[float, Query(ge=-180, le=180)],
    start_at: Annotated[datetime, Query(description="만나는 시각(ISO 8601). 시간대가 없으면 한국 시각")],
    radius_m: Annotated[int, Query(ge=200, le=30000, description="직선거리 반경(m)")] = 3000,
    duration_min: Annotated[int, Query(ge=30, le=1440, description="함께 보내는 시간(분)")] = 240,
) -> dto.PerformanceList:
    # 공연장이 반경 안이고, 회차가 [start_at, start_at+duration) 안에 시작해 창 끝+30분 전에 끝나는 공연만.
    # 키가 없으면 available=false — 외부 호출을 하지 않는다.
    return await service.nearby(lat, lng, radius_m, start_at, duration_min)
