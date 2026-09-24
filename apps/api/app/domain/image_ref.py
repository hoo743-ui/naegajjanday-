"""One picture for one card, with where it came from (docs/43).

Every place card resolves to exactly one of three kinds, in this order:

1. ``actual`` — a photo of *that* place (TourAPI for attractions, parks, festivals,
   culture; operator uploads).
2. ``category`` — a free-licence mood picture of the same kind of place (Wikimedia / Openverse / Pexels /
   Unsplash, curated by hand into ``data/media/category_images.json``). The UI labels it "분위기 이미지":
   it must never pass for a photo of the business.
3. ``branded-placeholder`` — our own drawing per kind (meal · cafe · walk · activity …), no photo at all.

The response carries the whole credit (source, author, licence, ready-to-show attribution line) so no
screen has to guess it from a URL.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

ImageType = Literal["actual", "category", "branded-placeholder"]
PlaceholderKind = Literal["meal", "cafe", "walk", "activity", "sight", "bar", "night"]

# TourAPI photos are KOGL (공공누리) type 1 (출처표시) or type 3 (출처표시 + 변경금지). Both require the
# credit; type 3 also forbids edits, so actual photos are shown as they are (no tint, no blur).
TOURAPI_LICENSE = "공공누리 (출처표시)"
TOURAPI_LICENSE_BY_CODE = {
    "Type1": "공공누리 제1유형 (출처표시)",
    "Type3": "공공누리 제3유형 (출처표시·변경금지)",
}
TOURAPI_CREDIT = "사진 ⓒ한국관광공사"
TOURAPI_HOME = "https://api.visitkorea.or.kr"

SOURCE_NAMES = {
    "wikimedia": "Wikimedia Commons",
    "openverse": "Openverse",
    "pexels": "Pexels",
    "unsplash": "Unsplash",
}


class ImageRef(BaseModel):
    image_type: ImageType
    image_url: str | None = Field(default=None, description="큰 그림. branded-placeholder 면 null")
    thumbnail_url: str | None = Field(default=None, description="작은 칸용. 따로 없으면 image_url 과 같다")
    source: str = Field(
        description="tourapi | upload | wikimedia | openverse | pexels | unsplash | naegajjanday"
    )
    source_url: str | None = Field(default=None, description="원본 페이지(작가 · 라이선스 확인용)")
    photographer: str | None = None
    license: str | None = None
    attribution_text: str | None = Field(default=None, description="화면에 그대로 적는 출처 한 줄")
    is_actual_place_photo: bool
    is_fallback_image: bool
    placeholder_kind: PlaceholderKind = Field(description="브랜드 그림의 종류 (사진이 깨질 때도 쓴다)")


def placeholder_kind(code: str | None) -> PlaceholderKind:
    """업종 코드(food.korean · attraction.park …)나 역할(MEAL · WALK …) → 브랜드 그림 종류."""
    c = (code or "").lower()
    if c.startswith(("cafe", "dessert")):
        return "cafe"
    if c.startswith("food") or c == "meal":
        return "meal"
    if c.startswith("bar"):
        return "bar"
    if c.startswith("nightview") or c == "night":
        return "night"
    if c.startswith(("attraction.park", "attraction.nature", "attraction.trail")) or c in {"walk", "park"}:
        return "walk"
    if c.startswith("activity") or c in {"festival", "culture.festival"}:
        return "activity"
    return "sight"


def actual_image(url: str, *, license_code: str | None = None) -> ImageRef:
    kind_host = "visitkorea.or.kr" in url
    return ImageRef(
        image_type="actual",
        image_url=url,
        thumbnail_url=url,
        source="tourapi" if kind_host else "upload",
        source_url=TOURAPI_HOME if kind_host else None,
        photographer="한국관광공사" if kind_host else None,
        license=(TOURAPI_LICENSE_BY_CODE.get(license_code or "", TOURAPI_LICENSE) if kind_host else None),
        attribution_text=TOURAPI_CREDIT if kind_host else None,
        is_actual_place_photo=True,
        is_fallback_image=False,
        placeholder_kind="sight",
    )


def category_image(entry: dict[str, Any], kind: PlaceholderKind) -> ImageRef:
    """`category_images.json` 의 한 항목(정규화된 것) → 분위기 이미지."""
    return ImageRef(
        image_type="category",
        image_url=entry["url"],
        thumbnail_url=entry.get("thumbnail_url") or entry["url"],
        source=entry.get("source") or "wikimedia",
        source_url=entry.get("page_url"),
        photographer=entry.get("author"),
        license=entry.get("license"),
        attribution_text=entry.get("attribution_text"),
        is_actual_place_photo=False,
        is_fallback_image=True,
        placeholder_kind=kind,
    )


def branded_placeholder(kind: PlaceholderKind) -> ImageRef:
    return ImageRef(
        image_type="branded-placeholder",
        source="naegajjanday",
        is_actual_place_photo=False,
        is_fallback_image=True,
        placeholder_kind=kind,
    )


def attribution_for(entry: dict[str, Any]) -> str:
    """ "분위기 이미지 · © 작가 · 라이선스 · 출처" — 오픈 라이선스가 요구하는 표기를 한 줄로."""
    parts = ["분위기 이미지"]
    if entry.get("author"):
        parts.append(f"© {entry['author']}")
    if entry.get("license"):
        parts.append(str(entry["license"]))
    source = SOURCE_NAMES.get(entry.get("source") or "wikimedia")
    if source:
        parts.append(source)
    return " · ".join(parts)


def resolve_image(
    thumbnail_url: str | None, category: str | None, *, kind_hint: str | None = None
) -> ImageRef:
    """실제 사진 → 같은 종류의 분위기 이미지 → 브랜드 그림."""
    from app.services.media_service import get_category_images

    kind = placeholder_kind(kind_hint or category)
    if thumbnail_url:
        return actual_image(thumbnail_url).model_copy(update={"placeholder_kind": kind})
    entry = get_category_images().for_category(category or "") if category else None
    if entry:
        return category_image(entry, kind)
    return branded_placeholder(kind)
