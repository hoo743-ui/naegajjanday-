from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.responses import PROBLEMS
from app.core.deps import CurrentUser, SessionDep, rate_limit
from app.domain.recommendation.option_text import last_choices
from app.domain.recommendation.style import extra_roles
from app.infra.db.models import OAuthAccount, RecommendationLog, User
from app.schemas import auth as dto
from app.schemas.course import CourseListResponse, LastChoices
from app.services.factory import AuthServiceDep, CourseServiceDep

router = APIRouter(
    prefix="/me", tags=["me"], dependencies=[Depends(rate_limit("read"))], responses=PROBLEMS(401)
)


async def _with_provider(session: AsyncSession, user: User, out: dto.UserOut) -> dto.UserOut:
    """`provider` lives on the linked OAuth account, not on the user row: report the first one linked."""
    provider = await session.scalar(
        select(OAuthAccount.provider)
        .where(OAuthAccount.user_id == user.id)
        .order_by(OAuthAccount.id)
        .limit(1)
    )
    return out.model_copy(update={"provider": provider})


@router.get("", response_model=dto.UserOut)
async def me(user: CurrentUser, service: AuthServiceDep, session: SessionDep) -> dto.UserOut:
    return await _with_provider(session, user, service.user_out(user))


@router.patch("", response_model=dto.UserOut)
async def patch_me(
    body: dto.UserPatch, user: CurrentUser, service: AuthServiceDep, session: SessionDep
) -> dto.UserOut:
    return await _with_provider(session, user, await service.patch_me(user, body))


@router.delete("", response_model=dto.DeleteAccountResponse, summary="탈퇴 (30일 유예 후 파기)")
async def delete_me(user: CurrentUser, service: AuthServiceDep) -> dto.DeleteAccountResponse:
    return await service.request_deletion(user)


@router.get("/preferences", response_model=dto.PreferencesBody)
async def get_preferences(user: CurrentUser, service: AuthServiceDep) -> dto.PreferencesBody:
    return await service.get_preferences(user)


@router.put("/preferences", response_model=dto.PreferencesBody)
async def put_preferences(
    body: dto.PreferencesBody, user: CurrentUser, service: AuthServiceDep
) -> dto.PreferencesBody:
    return await service.put_preferences(user, body)


@router.get("/last-choices", response_model=LastChoices, summary="지난번에 고른 것 (위저드의 기본값)")
async def my_last_choices(user: CurrentUser, session: SessionDep) -> LastChoices:
    body = await session.scalar(
        select(RecommendationLog.request)
        .where(RecommendationLog.user_id == user.id)
        .order_by(RecommendationLog.id.desc())
        .limit(1)
    )
    if not isinstance(body, dict):
        return LastChoices()
    try:
        return LastChoices.model_validate(last_choices(body, extra_roles()))
    except ValueError:  # an old request shape the wizard no longer speaks: start fresh rather than fail
        return LastChoices()


@router.get("/courses", response_model=CourseListResponse)
async def my_courses(
    user: CurrentUser,
    service: CourseServiceDep,
    cursor: str | None = None,
    limit: int = Query(default=20, ge=1, le=50),
) -> CourseListResponse:
    return await service.list_mine(user, cursor, limit)


@router.delete("/courses/{course_id}", status_code=204, responses=PROBLEMS(404))
async def delete_course(course_id: str, user: CurrentUser, service: CourseServiceDep) -> Response:
    await service.delete_mine(course_id, user)
    return Response(status_code=204)
