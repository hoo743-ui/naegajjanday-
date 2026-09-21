from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.core.deps import rate_limit
from app.services.media_service import get_category_images

router = APIRouter(prefix="/media", tags=["media"])


class Photo(BaseModel):
    url: str
    page_url: str | None = None
    title: str = ""
    author: str
    license: str


class CategoryImageMap(BaseModel):
    items: dict[str, Photo]


@router.get(
    "/categories",
    response_model=CategoryImageMap,
    dependencies=[Depends(rate_limit("read"))],
    summary="업종 대표 이미지 (가게 실사진이 없을 때 '예시'로 표시)",
)
async def categories() -> CategoryImageMap:
    return CategoryImageMap(
        items={k: Photo.model_validate(v) for k, v in get_category_images().all().items()}
    )
