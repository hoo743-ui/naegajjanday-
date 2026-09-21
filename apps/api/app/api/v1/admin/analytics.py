from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.v1.responses import PROBLEMS
from app.core import errors
from app.core.deps import SessionDep
from app.schemas import admin as dto
from app.services.analytics_service import AnalyticsService

router = APIRouter(prefix="/analytics", tags=["admin:analytics"])


@router.get("/users", responses=PROBLEMS(501), summary="DAU/WAU · 리텐션 코호트 · 유입 (미구현)")
async def users(
    date_from: Annotated[date | None, Query(alias="from")] = None,
    date_to: Annotated[date | None, Query(alias="to")] = None,
) -> None:
    # DAU/retention/acquisition need the client event stream (GA4 / PostHog); the API database only
    # sees course generation. Returning numbers derived from it would be misleading.
    raise errors.NotImplementedYet(
        "사용자 분석은 제품 분석 도구(PostHog/GA4) 연동 후 제공돼요. ANALYTICS_PROVIDER 를 설정해 주세요."
    )


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
