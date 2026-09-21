from __future__ import annotations

from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query

from app.api.v1.responses import PROBLEMS
from app.core.deps import CurrentUser, rate_limit
from app.schemas import place as dto
from app.services.factory import PlaceServiceDep

router = APIRouter(tags=["places"], dependencies=[Depends(rate_limit("read"))])

Sort = Literal["relevance", "distance", "rating", "price", "popularity"]


@router.get("/places/search", response_model=dto.PlaceSearchResponse, summary="장소 검색 (ES, 미설정 시 SQL)")
async def search(
    service: PlaceServiceDep,
    q: str | None = Query(default=None, max_length=50),
    region: str | None = None,
    role: str | None = Query(default=None, description="쉼표 구분: MEAL,CAFE"),
    max_price: int | None = Query(default=None, ge=0),
    lat: float | None = Query(default=None, ge=-90, le=90),
    lng: float | None = Query(default=None, ge=-180, le=180),
    radius: float | None = Query(default=None, gt=0, le=20000),
    sort: Sort = "relevance",
    cursor: int = Query(default=0, ge=0, le=10000),
    limit: int = Query(default=20, ge=1, le=50),
) -> dto.PlaceSearchResponse:
    return await service.search(
        q=q, region=region, role=role, max_price=max_price, lat=lat, lng=lng, radius=radius,
        sort=sort, limit=limit, offset=cursor,
    )  # fmt: skip


@router.get("/places/autocomplete", response_model=dto.AutocompleteResponse)
async def autocomplete(
    service: PlaceServiceDep, q: Annotated[str, Query(min_length=1, max_length=30)]
) -> dto.AutocompleteResponse:
    return await service.autocomplete(q)


@router.post(
    "/places/suggest",
    response_model=dto.PlaceSuggestResponse,
    status_code=201,
    responses=PROBLEMS(401, 404, 422),
)
async def suggest(
    body: dto.PlaceSuggestRequest, service: PlaceServiceDep, user: CurrentUser
) -> dto.PlaceSuggestResponse:
    return await service.suggest(body, user)


@router.get("/places/{place_id}", response_model=dto.PlaceDetail, responses=PROBLEMS(404))
async def detail(place_id: str, service: PlaceServiceDep) -> dto.PlaceDetail:
    return await service.detail(place_id)


@router.get("/places/{place_id}/nearby", response_model=dto.PlaceSearchResponse, responses=PROBLEMS(404))
async def nearby(
    place_id: str,
    service: PlaceServiceDep,
    role: str | None = None,
    radius: float = Query(default=700, gt=0, le=5000),
    limit: int = Query(default=10, ge=1, le=30),
) -> dto.PlaceSearchResponse:
    return await service.nearby(place_id, role, radius, limit)


@router.get("/events", response_model=dto.EventList, responses=PROBLEMS(404), summary="기간 내 이벤트")
async def events(
    service: PlaceServiceDep,
    region: Annotated[str | None, Query(description="생략하면 전체 지역")] = None,
    date_from: Annotated[date | None, Query(alias="from")] = None,
    date_to: Annotated[date | None, Query(alias="to")] = None,
) -> dto.EventList:
    return await service.events(region, date_from, date_to)
