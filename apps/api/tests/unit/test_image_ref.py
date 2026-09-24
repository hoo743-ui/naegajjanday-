"""docs/43: one picture per card — actual photo → mood picture → branded drawing, always with its credit."""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

from app.domain.image_ref import placeholder_kind, resolve_image
from app.schemas.course import PlaceBrief
from app.services.media_service import CategoryImages

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"


def test_actual_tourapi_photo_carries_the_kogl_credit() -> None:
    ref = resolve_image(
        "https://tong.visitkorea.or.kr/cms/resource/06/3556706_image2_1.jpg", "attraction.park"
    )
    assert ref.image_type == "actual"
    assert ref.is_actual_place_photo and not ref.is_fallback_image
    assert ref.source == "tourapi"
    assert ref.attribution_text == "사진 ⓒ한국관광공사"
    assert ref.license and ref.license.startswith("공공누리")
    assert ref.placeholder_kind == "walk"  # still known, for when the photo fails to load


def test_no_photo_falls_back_to_a_labelled_mood_picture() -> None:
    ref = resolve_image(None, "food.korean.bbq")  # nearest curated parent
    assert ref.image_type == "category"
    assert not ref.is_actual_place_photo and ref.is_fallback_image
    assert ref.image_url and ref.photographer and ref.license
    assert ref.attribution_text and ref.attribution_text.startswith("분위기 이미지")
    assert ref.placeholder_kind == "meal"


def test_nothing_at_all_is_our_own_drawing() -> None:
    ref = resolve_image(None, "zzz.unknown")
    assert ref.image_type == "branded-placeholder"
    assert ref.image_url is None and ref.source == "naegajjanday"
    assert ref.is_fallback_image and not ref.is_actual_place_photo


@pytest.mark.parametrize(
    ("code", "kind"),
    [
        ("food.noodle", "meal"),
        ("MEAL", "meal"),
        ("cafe.roastery", "cafe"),
        ("dessert.bakery", "cafe"),
        ("attraction.park", "walk"),
        ("WALK", "walk"),
        ("activity.karaoke", "activity"),
        ("culture.festival", "activity"),
        ("bar.wine", "bar"),
        ("nightview", "night"),
        ("culture.museum", "sight"),
        (None, "sight"),
    ],
)
def test_placeholder_kind(code: str | None, kind: str) -> None:
    assert placeholder_kind(code) == kind


def test_place_brief_serialises_the_image() -> None:
    brief = PlaceBrief(id="x", name="어느 카페", category="cafe", lat=37.5, lng=127.0)
    out = brief.model_dump()
    assert out["image"]["image_type"] == "category"
    # a stored snapshot that already has "image" still loads (computed, not an input)
    assert PlaceBrief.model_validate(out).image.image_type == "category"


def test_old_wikimedia_entries_are_normalised(tmp_path: Path) -> None:
    path = tmp_path / "category_images.json"
    path.write_text(
        json.dumps(
            {
                "cafe": {
                    "url": "https://u/x.jpg",
                    "page_url": "https://p",
                    "title": "t",
                    "author": "A",
                    "license": "CC BY 2.0",
                }
            }
        ),
        "utf-8",
    )
    entry = CategoryImages(path).for_category("cafe.roastery")
    assert entry is not None
    assert entry["source"] == "wikimedia"
    assert entry["thumbnail_url"] == "https://u/x.jpg"
    assert entry["attribution_text"] == "분위기 이미지 · © A · CC BY 2.0 · Wikimedia Commons"


@pytest.fixture(scope="module")
def curate():  # type: ignore[no-untyped-def]
    sys.path.insert(0, str(SCRIPTS))
    try:
        yield importlib.import_module("curate_mood_images")
    finally:
        sys.path.remove(str(SCRIPTS))


def test_openverse_drops_noncommercial_and_no_derivatives(curate) -> None:  # type: ignore[no-untyped-def]
    ok = curate.from_openverse(
        {
            "id": "a1",
            "url": "https://live.staticflickr.com/1.jpg",
            "thumbnail": "https://api.openverse.org/t/a1",
            "creator": "kim",
            "license": "by-sa",
            "license_version": "2.0",
            "foreign_landing_url": "https://flickr.com/p/1",
        }
    )
    assert ok["license"] == "CC BY-SA 2.0"
    assert ok["attribution_text"] == "분위기 이미지 · © kim · CC BY-SA 2.0 · Openverse"
    for lic in ("by-nc", "by-nd", "by-nc-sa"):
        assert (
            curate.from_openverse({"id": "b", "url": "https://x", "license": lic, "license_version": "4.0"})
            is None
        )
    assert curate.from_openverse({"id": "c", "url": "https://x", "license": "cc0"})["license"] == "CC0"


def test_pexels_and_unsplash_credit_their_photographer(curate) -> None:  # type: ignore[no-untyped-def]
    p = curate.from_pexels(
        {
            "id": 7,
            "url": "https://www.pexels.com/photo/7/",
            "photographer": "Lee",
            "alt": "coffee",
            "src": {
                "large": "https://images.pexels.com/7-l.jpeg",
                "medium": "https://images.pexels.com/7-m.jpeg",
            },
        }
    )
    assert (p["id"], p["license"], p["thumbnail_url"]) == (
        "pexels:7",
        "Pexels License",
        "https://images.pexels.com/7-m.jpeg",
    )
    assert p["attribution_text"] == "분위기 이미지 · © Lee · Pexels License · Pexels"
    u = curate.from_unsplash(
        {
            "id": "u9",
            "urls": {"regular": "https://images.unsplash.com/r", "small": "https://images.unsplash.com/s"},
            "user": {"name": "Park"},
            "links": {
                "html": "https://unsplash.com/photos/u9",
                "download_location": "https://api.unsplash.com/d",
            },
        }
    )
    assert u["page_url"].endswith("utm_source=naegajjanday&utm_medium=referral")  # Unsplash attribution rule
    assert u["download_location"] and u["license"] == "Unsplash License"
