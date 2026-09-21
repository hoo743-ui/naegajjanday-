from __future__ import annotations

from fastapi import APIRouter, Response

from app.api.v1.admin.events import Svc
from app.api.v1.responses import PROBLEMS
from app.core import errors
from app.schemas import admin as dto

router = APIRouter(tags=["admin:banners"])


@router.get("/banners", response_model=dto.AdminBannerList)
async def list_banners(svc: Svc) -> dto.AdminBannerList:
    return await svc.list_banners()


@router.post("/banners", response_model=dto.AdminBannerOut, status_code=201, responses=PROBLEMS(404, 422))
async def create_banner(body: dto.BannerIn, svc: Svc) -> dto.AdminBannerOut:
    return await svc.create_banner(body)


@router.patch("/banners/{banner_id}", response_model=dto.AdminBannerOut, responses=PROBLEMS(404, 422))
async def patch_banner(banner_id: int, body: dto.BannerPatch, svc: Svc) -> dto.AdminBannerOut:
    return await svc.patch_banner(banner_id, body)


@router.delete("/banners/{banner_id}", status_code=204, responses=PROBLEMS(404))
async def delete_banner(banner_id: int, svc: Svc) -> Response:
    await svc.delete_banner(banner_id)
    return Response(status_code=204)


@router.post("/uploads/presign", responses=PROBLEMS(501), summary="S3 presigned URL (미구현)")
async def presign(body: dto.PresignRequest) -> None:
    # Needs an object-storage client (boto3 + bucket policy); banners accept any https image_url meanwhile.
    raise errors.NotImplementedYet(
        "업로드 저장소(S3)가 아직 연결되지 않았어요. image_url 에 외부 URL을 넣어 주세요."
    )
