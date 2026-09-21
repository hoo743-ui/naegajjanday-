from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.deps import ContainerDep, rate_limit
from app.schemas import meta as dto
from app.services.factory import MetaServiceDep

router = APIRouter(prefix="/meta", tags=["meta"], dependencies=[Depends(rate_limit("read"))])


@router.get("/regions", response_model=dto.RegionList, summary="활성 지역 트리/검색")
async def regions(service: MetaServiceDep, parent: str | None = None, q: str | None = None) -> dto.RegionList:
    return await service.regions(parent, q)


@router.get(
    "/regions/{slug}/signature",
    response_model=dto.LocalSignature,
    summary="이 동네가 무엇으로 알려져 있는지 (명물 · 보러 오는 곳)",
)
async def region_signature(slug: str, service: MetaServiceDep) -> dto.LocalSignature:
    return await service.signature(slug)


@router.get("/purposes", response_model=dto.PurposeList, summary="목적 목록 + 추천 예산 범위")
async def purposes(service: MetaServiceDep) -> dto.PurposeList:
    return await service.purposes()


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
    return dto.Features(chat=container.llm.available)
