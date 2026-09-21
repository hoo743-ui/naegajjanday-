from __future__ import annotations

import json
from pathlib import Path

from app.services.media_service import CategoryImages

PHOTO = {"url": "https://example.org/a.jpg", "author": "someone", "license": "CC BY-SA 4.0"}


def test_category_image_falls_back_to_the_parent_category(tmp_path: Path) -> None:
    path = tmp_path / "category_images.json"
    path.write_text(
        json.dumps({"food": {**PHOTO, "title": "food"}, "food.korean": {**PHOTO, "title": "korean"}})
    )
    images = CategoryImages(path)

    assert images.for_category("food.korean")["title"] == "korean"  # type: ignore[index]
    assert images.for_category("food.korean.bbq")["title"] == "korean"  # type: ignore[index]
    assert images.for_category("food.noodle")["title"] == "food"  # type: ignore[index]
    assert images.for_category("bar.pub") is None


def test_missing_file_means_no_images(tmp_path: Path) -> None:
    images = CategoryImages(tmp_path / "nope.json")
    assert images.all() == {}
    assert images.for_category("food") is None
