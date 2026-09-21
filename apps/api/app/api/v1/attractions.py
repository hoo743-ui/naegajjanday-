from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.v1.responses import PROBLEMS
from app.core.deps import rate_limit
from app.schemas import place as dto
from app.services.factory import PlaceServiceDep

router = APIRouter(tags=["attractions"], dependencies=[Depends(rate_limit("read"))])


@router.get(
    "/attractions",
    response_model=dto.AttractionList,
    responses=PROBLEMS(404, 422),
    summary="관광지·공원·전시·축제·문화공간 통합 조회",
)
async def attractions(
    service: PlaceServiceDep,
    region: Annotated[str | None, Query(description="생략하면 전체 지역")] = None,
    type: Annotated[str | None, Query(description="park,exhibition,festival,culture,attraction")] = None,
    date_: Annotated[date | None, Query(alias="date")] = None,
    q: Annotated[str | None, Query(max_length=60, description="이름·주소에 들어 있는 글자로 찾기")] = None,
    limit: Annotated[int | None, Query(ge=1, le=100, description="생략하면 전부(최대 300곳 + 행사)")] = None,
    cursor: Annotated[str | None, Query(pattern=r"^\d{1,5}$", description="앞 응답의 next_cursor")] = None,
) -> dto.AttractionList:
    # The web asked for `limit=24&cursor=…` from day one; ignoring it made the explore page draw every
    # card (377) and fetch every photo at once.
    # `q` filters inside the service, i.e. before the slicing below — a page is a page of the matches.
    full = await service.attractions(region, type, date_, q)
    if limit is None:
        return full
    start = int(cursor or 0)
    page = full.items[start : start + limit]
    more = start + limit < len(full.items)
    return dto.AttractionList(items=page, next_cursor=str(start + limit) if more else None)
