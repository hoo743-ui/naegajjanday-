"""Representative image per category, shown when a business has no photo of its own.

The images are a small curated set from Wikimedia Commons under open licences
(`data/media/category_images.json`, produced by `scripts/curate_category_images.py`), so every
entry carries author / licence / source-page fields and the UI must show them.

We deliberately do NOT present a category image as a photo *of that business*: the web labels it
as an example ("예시"). Real per-business photos need an owner/user upload path or a licensed
provider (TourAPI for attractions).

Scenery photos around a route are fetched by the visitor's browser straight from the Commons API
(its documented anonymous CORS mode). Server-to-server calls would fall under Wikimedia's robot
policy, which requires an identified client with contact details — see the curation script.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.core.config import get_settings


class CategoryImages:
    """category code -> one curated free-licence image (docs/43: Wikimedia/Openverse/Pexels/Unsplash)."""

    def __init__(self, path: Path) -> None:
        self._items: dict[str, dict[str, Any]] = {}
        if path.exists():
            raw = json.loads(path.read_text(encoding="utf-8"))
            self._items = {code: _normalize(entry) for code, entry in raw.items()}

    def all(self) -> dict[str, dict[str, Any]]:
        return self._items

    def for_category(self, code: str) -> dict[str, Any] | None:
        # "food.korean.bbq" -> "food.korean" -> "food"
        parts = code.split(".")
        while parts:
            hit = self._items.get(".".join(parts))
            if hit:
                return hit
            parts.pop()
        return None


def _normalize(entry: dict[str, Any]) -> dict[str, Any]:
    """Older entries are Wikimedia-only and carry no source / thumbnail / credit line: fill them in."""
    from app.domain.image_ref import attribution_for

    out = dict(entry)
    out.setdefault("source", "wikimedia")
    out.setdefault("thumbnail_url", out["url"])
    out.setdefault("attribution_text", attribution_for(out))
    return out


@lru_cache(maxsize=1)
def get_category_images() -> CategoryImages:
    return CategoryImages(get_settings().media_dir / "category_images.json")
