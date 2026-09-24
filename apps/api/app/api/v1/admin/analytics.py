from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Query

from app.core import errors
from app.core.deps import ContainerDep, SessionDep
from app.schemas import admin as dto
from app.services.analytics_service import AnalyticsService
from app.services.usage_service import UsageService

router = APIRouter(prefix="/analytics", tags=["admin:analytics"])


@router.get(
    "/users",
    response_model=dto.UserAnalytics,
    summary="날짜별 방문자(로그인 · 비로그인) · 가입 · 로그인 · 코스 · 유입 · 리텐션 (docs/50)",
)
async def users(
    session: SessionDep,
    container: ContainerDep,
    date_from: Annotated[date | None, Query(alias="from")] = None,
    date_to: Annotated[date | None, Query(alias="to")] = None,
) -> dto.UserAnalytics:
    tz = ZoneInfo(container.settings.timezone)
    end = date_to or datetime.now(tz).date()
    start = date_from or end - timedelta(days=13)
    if start > end:
        raise errors.ValidationFailed("from 은 to 보다 앞서야 해요.")
    if (end - start).days > 180:
        raise errors.ValidationFailed("기간은 180일까지 볼 수 있어요.")
    return await UsageService(session, container.settings.timezone).users(start, end)


@router.get(
    "/recommendations", response_model=dto.RecommendationStats, summary="추천 통계 (recommendation_log 기반)"
)
async def recommendations(
    session: SessionDep,
    date_from: Annotated[date | None, Query(alias="from")] = None,
    date_to: Annotated[date | None, Query(alias="to")] = None,
) -> dto.RecommendationStats:
    end = date_to or datetime.now(UTC).date()
    start = date_from or end - timedelta(days=29)
    if start > end:
        raise errors.ValidationFailed("from 은 to 보다 앞서야 해요.")
    return await AnalyticsService(session).recommendations(start, end)


@router.get("/places/top", response_model=dto.TopPlaceList)
async def top_places(
    session: SessionDep, region: str | None = None, limit: int = Query(default=20, ge=1, le=100)
) -> dto.TopPlaceList:
    return await AnalyticsService(session).top_places(region, limit)
