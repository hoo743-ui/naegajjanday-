from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.v1.responses import PROBLEMS
from app.core.deps import SessionDep, rate_limit
from app.schemas import stay as dto
from app.services.stay_service import StayService

router = APIRouter(tags=["stays"], dependencies=[Depends(rate_limit("read"))])


def stay_service(session: SessionDep) -> StayService:
    return StayService(session)


StayServiceDep = Annotated[StayService, Depends(stay_service)]


@router.get(
    "/stays",
    response_model=dto.StayList,
    responses=PROBLEMS(422),
    summary="좌표 주변 숙소 (한국관광공사 공식 데이터 · 요금 없음)",
)
async def stays(
    service: StayServiceDep,
    lat: Annotated[float, Query(ge=-90, le=90)],
    lng: Annotated[float, Query(ge=-180, le=180)],
    radius_m: Annotated[int, Query(ge=200, le=30000, description="직선거리 반경(m)")] = 3000,
    limit: Annotated[int, Query(ge=1, le=50)] = 12,
) -> dto.StayList:
    # 사진이 있는 숙소가 먼저, 그다음 가까운 순. 요금은 공식 데이터가 없어 내려주지 않는다(price_note).
    return await service.near(lat, lng, radius_m, limit)
