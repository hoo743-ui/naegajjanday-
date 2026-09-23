from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query
from fastapi.responses import StreamingResponse

from app.api.v1.responses import PROBLEMS
from app.core.course_key import capture_course_key
from app.core.deps import CurrentUser, OptionalUser, rate_limit
from app.core.sse import SSE_HEADERS, sse, with_heartbeat
from app.domain.recommendation.preference import interpret
from app.schemas import course as dto
from app.schemas import route as route_dto
from app.schemas.common import Ok
from app.services.factory import CourseServiceDep

# X-Course-Key (the anonymous creator's edit key) is read once per request for the ownership check (docs/28)
router = APIRouter(prefix="/courses", tags=["courses"], dependencies=[Depends(capture_course_key)])


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


@router.post(
    "/interpret",
    response_model=dto.InterpretResponse,
    responses=PROBLEMS(422),
    summary="고른 하루를 어떻게 이해했는지 (코스를 만들기 전 확인용)",
)
async def interpret_preferences(body: dto.InterpretRequest) -> dto.InterpretResponse:
    got = interpret(
        pace=body.pace,
        move_style=body.move_style,
        wishes=body.wishes,
        liked_tags=body.liked_tags,
        disliked_tags=body.disliked_tags,
        budget_total=body.budget_total,
        party_size=body.party_size,
    )
    return dto.InterpretResponse(
        summary=[dto.SummaryLine.model_validate(line) for line in got.summary], layers=got.layers()
    )


@router.get(
    "/{course_id}",
    response_model=dto.CourseDetailResponse,
    dependencies=[Depends(rate_limit("read"))],
    responses=PROBLEMS(404),
    summary="공유 링크 조회 (OG 메타 + 조회자 기준 is_owner / can_edit / is_saved)",
)
async def get_course(
    course_id: str, service: CourseServiceDep, viewer: OptionalUser
) -> dto.CourseDetailResponse:
    return await service.get(course_id, viewer)


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


@router.get(
    "/{course_id}/stops/{position}/candidates",
    response_model=dto.StopCandidateList,
    dependencies=[Depends(rate_limit("read"))],
    responses=PROBLEMS(404, 422),
    summary="한 스톱을 바꿀 후보 몇 곳 (swap 이 받아 주는 곳만, place_id 로 고르면 그대로 바뀐다)",
)
async def stop_candidates(
    course_id: str,
    position: int,
    service: CourseServiceDep,
    viewer: OptionalUser,
    limit: Annotated[int, Query(ge=1, le=5)] = 3,
) -> dto.StopCandidateList:
    return await service.candidates(course_id, position, limit, viewer)


@router.get(
    "/{course_id}/suggestions",
    response_model=dto.SuggestionList,
    dependencies=[Depends(rate_limit("read"))],
    responses=PROBLEMS(404),
    summary="예산이 남았을 때: 마지막 장소 근처에서 남은 돈으로 갈 만한 곳",
)
async def suggestions(course_id: str, service: CourseServiceDep, user: OptionalUser) -> dto.SuggestionList:
    return await service.suggestions(course_id, user)


@router.post(
    "/{course_id}/stops",
    response_model=dto.CourseOut,
    dependencies=[Depends(rate_limit("read"))],
    responses=PROBLEMS(403, 404, 422),
    summary="권한 곳을 코스의 끝에 넣고 시각 · 합계를 다시 계산",
)
async def add_stop(
    course_id: str, body: dto.AddStopRequest, service: CourseServiceDep, user: OptionalUser
) -> dto.CourseOut:
    return await service.add_stop(course_id, body, user)


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


@router.get(
    "/{course_id}/route",
    response_model=route_dto.CourseRouteOut,
    dependencies=[Depends(rate_limit("read"))],
    responses=PROBLEMS(404),
    summary="코스의 실제 경로: 구간별 거리 · 시간 · 경로 좌표 + 이동 가능 여부 검증 (docs/27)",
)
async def course_route(course_id: str, service: CourseServiceDep) -> route_dto.CourseRouteOut:
    return await service.route(course_id)


@router.post("/{course_id}/save", response_model=dto.CourseOut, responses=PROBLEMS(401, 403, 404))
async def save(course_id: str, service: CourseServiceDep, user: CurrentUser) -> dto.CourseOut:
    return await service.save(course_id, user)


@router.post("/{course_id}/feedback", response_model=Ok, responses=PROBLEMS(401, 404, 422))
async def feedback(
    course_id: str, body: dto.FeedbackRequest, service: CourseServiceDep, user: CurrentUser
) -> Ok:
    await service.feedback(course_id, body, user)
    return Ok()
