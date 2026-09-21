from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from app.api.v1.responses import PROBLEMS
from app.core import errors
from app.core.deps import rate_limit
from app.domain.models import GeoPoint
from app.services.directions_service import DirectionsService, get_transit_index

router = APIRouter(prefix="/directions", tags=["directions"])

MAX_POINTS = 12


class RouteLeg(BaseModel):
    distance_m: int
    duration_min: int
    coordinates: list[tuple[float, float]] = []  # this leg only, [lat, lng] — the map draws leg by leg


class WalkRoute(BaseModel):
    source: Literal["osrm", "straight"]
    coordinates: list[tuple[float, float]]  # [lat, lng], ready for the map polyline
    legs: list[RouteLeg]
    distance_m: int
    duration_min: int


class SubwayAccess(BaseModel):
    station: str
    exit: str | None = None
    lat: float
    lng: float
    distance_m: int
    walk_min: int


class BusAccess(BaseModel):
    name: str
    stop_no: str | None = None
    lat: float
    lng: float
    distance_m: int
    walk_min: int


class AccessHint(BaseModel):
    subway: SubwayAccess | None = None
    bus: BusAccess | None = None


class AccessResponse(BaseModel):
    items: list[AccessHint]
    attribution: str = "© OpenStreetMap contributors"


def parse_points(raw: str) -> list[GeoPoint]:
    points: list[GeoPoint] = []
    for chunk in raw.split(";"):
        try:
            lat_s, lng_s = chunk.split(",")
            lat, lng = float(lat_s), float(lng_s)
        except ValueError as exc:
            raise errors.ValidationFailed("points 는 'lat,lng;lat,lng' 형식이어야 해요.") from exc
        if not (-90 <= lat <= 90 and -180 <= lng <= 180):
            raise errors.ValidationFailed("좌표 범위를 벗어났어요.")
        points.append(GeoPoint(lat, lng))
    if not 1 <= len(points) <= MAX_POINTS:
        raise errors.ValidationFailed(f"points 는 1~{MAX_POINTS}개까지 보낼 수 있어요.")
    return points


PointsQuery = Annotated[str, Query(description="'lat,lng;lat,lng;…' 방문 순서대로", max_length=600)]


@router.get(
    "/walk",
    response_model=WalkRoute,
    dependencies=[Depends(rate_limit("read"))],
    responses=PROBLEMS(422),
    summary="실제 보행 경로 (라우터가 응답하지 않으면 직선 폴백)",
)
async def walk(points: PointsQuery) -> WalkRoute:
    return WalkRoute.model_validate(await DirectionsService().walk(parse_points(points)))


@router.get(
    "/access",
    response_model=AccessResponse,
    dependencies=[Depends(rate_limit("read"))],
    responses=PROBLEMS(422),
    summary="지점별 가장 가까운 지하철 출구 · 버스 정류장",
)
async def access(points: PointsQuery) -> AccessResponse:
    index = get_transit_index()
    return AccessResponse(
        items=[AccessHint(subway=index.subway(p), bus=index.bus(p)) for p in parse_points(points)]
    )


class Station(BaseModel):
    name: str
    lat: float
    lng: float


class StationList(BaseModel):
    items: list[Station]
    attribution: str = "© OpenStreetMap contributors"


@router.get(
    "/stations",
    response_model=StationList,
    dependencies=[Depends(rate_limit("read"))],
    summary="역 이름 검색 — '신도림'·'반포' 처럼 행정구역이 아닌 동네도 역 주변으로 코스를 짤 수 있다",
)
async def stations(
    q: Annotated[str, Query(min_length=1, max_length=20, description="역 이름 일부")],
    limit: Annotated[int, Query(ge=1, le=20)] = 8,
) -> StationList:
    found = get_transit_index().search_stations(q, limit)
    return StationList(items=[Station.model_validate(s) for s in found])
