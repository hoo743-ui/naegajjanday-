from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.api.v1.responses import PROBLEMS
from app.core.deps import ContainerDep, SessionDep, rate_limit
from app.schemas import meta as dto
from app.services.factory import MetaServiceDep
from app.services.spot_service import SpotService

router = APIRouter(prefix="/meta", tags=["meta"], dependencies=[Depends(rate_limit("read"))])


@router.get("/regions", response_model=dto.RegionList, summary="활성 지역 트리/검색")
async def regions(service: MetaServiceDep, parent: str | None = None, q: str | None = None) -> dto.RegionList:
    return await service.regions(parent, q)


@router.get(
    "/regions/{slug}",
    response_model=dto.RegionOut,
    responses=PROBLEMS(404),
    summary="지역 하나 (동 · 읍 · 면은 전체 목록에 없으므로 이름은 여기서 읽는다)",
)
async def region(slug: str, service: MetaServiceDep) -> dto.RegionOut:
    return await service.region(slug)


@router.get(
    "/regions/{slug}/signature",
    response_model=dto.LocalSignature,
    summary="이 동네가 무엇으로 알려져 있는지 (명물 · 보러 오는 곳)",
)
async def region_signature(slug: str, service: MetaServiceDep) -> dto.LocalSignature:
    return await service.signature(slug)


@router.get(
    "/regions/{slug}/hot",
    response_model=dto.HotPlaces,
    responses=PROBLEMS(404),
    summary="이 지역에서 사람들이 실제로 많이 가는 곳 (내비게이션 실측 순위)",
)
async def region_hot_places(
    slug: str, service: MetaServiceDep, limit: int = Query(default=8, ge=1, le=30)
) -> dto.HotPlaces:
    return await service.hot_places(slug, limit)


@router.get("/purposes", response_model=dto.PurposeList, summary="목적 목록 + 추천 예산 범위")
async def purposes(
    service: MetaServiceDep,
    context: str | None = Query(default=None, description="university: 대학교를 고른 하루의 목적 (docs/34)"),
) -> dto.PurposeList:
    return await service.purposes(context)


@router.get("/universities", response_model=dto.UniversityList, summary="하루의 중심이 될 대학교 검색")
async def universities(
    service: MetaServiceDep,
    q: str | None = Query(default=None, max_length=30),
    limit: int = Query(default=20, ge=1, le=50),
) -> dto.UniversityList:
    return await service.universities(q, limit)


@router.get("/categories", response_model=dto.CategoryList, summary="카테고리 트리")
async def categories(service: MetaServiceDep) -> dto.CategoryList:
    return await service.categories()


@router.get("/tags", response_model=dto.TagList, summary="선호 태그 칩")
async def tags(service: MetaServiceDep, group: str | None = None) -> dto.TagList:
    return await service.tags(group)


@router.get("/banners", response_model=dto.BannerList, summary="노출 중 배너")
async def banners(
    service: MetaServiceDep, placement: str | None = None, region: str | None = None
) -> dto.BannerList:
    return await service.banners(placement, region)


@router.get("/features", response_model=dto.Features, summary="이 환경에서 쓸 수 있는 기능")
async def features(container: ContainerDep) -> dto.Features:
    # the same switch `ChatService.ensure_available` uses, so the flag and the 503 can never disagree
    return dto.Features(
        chat=container.llm.available, performances=bool(container.settings.kopis_api_key.strip())
    )


@router.get(
    "/spots",
    response_model=dto.SpotList,
    summary="가는 김에: 꼭 들를 곳 검색 (우리 장소 + 카카오 검색, 저장하지 않음)",
)
async def spots(
    session: SessionDep,
    container: ContainerDep,
    q: str = Query(
        min_length=2, max_length=40, description="가게 · 매장 · 랜드마크 이름 (예: 애플 가로수길)"
    ),
    limit: int = Query(default=8, ge=1, le=15),
) -> dto.SpotList:
    found = await SpotService(session, container.settings, container.cache).lookup(q, limit)
    return dto.SpotList(items=[dto.SpotOut.model_validate(f) for f in found])
