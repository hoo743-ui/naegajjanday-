from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, Header
from fastapi.responses import StreamingResponse

from app.api.v1.responses import PROBLEMS
from app.core.deps import CurrentUser, OptionalUser, rate_limit
from app.core.sse import SSE_HEADERS, sse, with_heartbeat
from app.schemas import course as dto
from app.schemas.common import Ok
from app.services.factory import CourseServiceDep

router = APIRouter(prefix="/courses", tags=["courses"])


@router.post(
    "/generate",
    response_model=dto.CourseGenerateResponse,
    dependencies=[Depends(rate_limit("generate"))],
    responses=PROBLEMS(404, 422, 429),
    summary="예산 기반 코스 생성",
)
async def generate(
    body: dto.CourseGenerateRequest,
    service: CourseServiceDep,
    user: OptionalUser,
    idempotency_key: Annotated[str | None, Header(max_length=128)] = None,
) -> dto.CourseGenerateResponse:
    return await service.generate(body, user, idempotency_key)


@router.get(
    "/{course_id}",
    response_model=dto.CourseDetailResponse,
    dependencies=[Depends(rate_limit("read"))],
    responses=PROBLEMS(404),
    summary="공유 링크 조회 (OG 메타 포함)",
)
async def get_course(course_id: str, service: CourseServiceDep) -> dto.CourseDetailResponse:
    return await service.get(course_id)


@router.post(
    "/{course_id}/swap",
    response_model=dto.CourseOut,
    dependencies=[Depends(rate_limit("read"))],
    responses=PROBLEMS(403, 404, 422),
    summary="특정 스톱만 교체하고 나머지는 고정한 채 재계산",
)
async def swap(
    course_id: str, body: dto.SwapRequest, service: CourseServiceDep, user: OptionalUser
) -> dto.CourseOut:
    return await service.swap(course_id, body, user)


@router.post(
    "/{course_id}/reorder",
    response_model=dto.CourseOut,
    dependencies=[Depends(rate_limit("read"))],
    responses=PROBLEMS(403, 404, 422),
    summary="순서 변경 후 이동시간·도착시각 재계산",
)
async def reorder(
    course_id: str, body: dto.ReorderRequest, service: CourseServiceDep, user: OptionalUser
) -> dto.CourseOut:
    return await service.reorder(course_id, body, user)


@router.get(
    "/{course_id}/narrative",
    dependencies=[Depends(rate_limit("read"))],
    responses={200: {"content": {"text/event-stream": {}}}, **PROBLEMS(404)},
    summary="코스 설명 SSE 스트림 (token → done)",
)
async def narrative(course_id: str, service: CourseServiceDep) -> StreamingResponse:
    tokens = await service.narrative_stream(course_id)  # 404 is raised before the stream starts

    async def events() -> AsyncIterator[str]:
        try:
            async for token in tokens:
                yield sse("token", {"text": token})
            yield sse("done", {})
        except Exception:
            yield sse("error", {"code": "NARRATIVE_FAILED"})

    return StreamingResponse(with_heartbeat(events()), media_type="text/event-stream", headers=SSE_HEADERS)


@router.post("/{course_id}/save", response_model=dto.CourseOut, responses=PROBLEMS(401, 403, 404))
async def save(course_id: str, service: CourseServiceDep, user: CurrentUser) -> dto.CourseOut:
    return await service.save(course_id, user)


@router.post("/{course_id}/feedback", response_model=Ok, responses=PROBLEMS(401, 404, 422))
async def feedback(
    course_id: str, body: dto.FeedbackRequest, service: CourseServiceDep, user: CurrentUser
) -> Ok:
    await service.feedback(course_id, body, user)
    return Ok()
