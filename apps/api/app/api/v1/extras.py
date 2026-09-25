"""Read-only additions around a finished course (docs/46). Nothing here changes a course."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.v1.responses import PROBLEMS
from app.core.deps import ContainerDep, SessionDep, rate_limit
from app.services.along_service import AlongList, AlongService
from app.services.scenery_service import Scenery, SceneryService
from app.services.signal_service import SignalMap, SignalService

router = APIRouter(tags=["extras"], dependencies=[Depends(rate_limit("read"))])


@router.get(
    "/courses/{course_id}/along-the-way",
    response_model=AlongList,
    responses=PROBLEMS(404),
    summary="가는 길에 들를 만한 곳: 두 장소 사이, 조금만 돌아가면 되는 인기 장소 (티맵 실측)",
)
async def along_the_way(course_id: str, session: SessionDep, container: ContainerDep) -> AlongList:
    return await AlongService(session, container.cache).for_course(course_id)


@router.get(
    "/courses/{course_id}/scenery",
    response_model=Scenery,
    responses=PROBLEMS(404),
    summary="오늘 지나갈 길을 사진으로: 코스 장소와 길가 볼거리의 실제 사진(출처 포함), 걷는 순서대로",
)
async def scenery(course_id: str, session: SessionDep, container: ContainerDep) -> Scenery:
    return await SceneryService(session, container.cache).for_course(course_id)


@router.get(
    "/places/signals",
    response_model=SignalMap,
    summary="확인할 수 있는 평판 신호: 실측 인기 순위 · 공공 지정 · 오래된 가게 · 블로그 후기 수",
)
async def signals(
    session: SessionDep,
    container: ContainerDep,
    ids: Annotated[str, Query(max_length=400, description="장소 id 를 쉼표로 (최대 10개)")],
) -> SignalMap:
    wanted = [x.strip() for x in ids.split(",") if x.strip()][:10]
    return await SignalService(session, container.settings, container.cache).for_places(wanted)
