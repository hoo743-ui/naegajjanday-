"""오늘 지나갈 길을 사진으로 (2026-09-26): only real, credited photos, in the order the day is walked."""

from __future__ import annotations

import httpx

from app.domain.models import GeoPoint
from app.services.scenery_service import progress_on
from tests.conftest import GENERATE_BODY


def test_progress_along_a_leg_and_distance_off_it() -> None:
    a, b = GeoPoint(37.5, 127.0), GeoPoint(37.5, 127.01)
    t, off = progress_on(a, b, GeoPoint(37.5009, 127.005))
    assert 0.45 < t < 0.55 and 90 < off < 110
    assert progress_on(a, b, GeoPoint(37.5, 126.99))[0] == 0.0  # behind the start: clamped


async def test_scenery_lists_only_real_photos_with_their_credit(client: httpx.AsyncClient) -> None:
    made = await client.post("/v1/courses/generate", json={**GENERATE_BODY, "alternatives": 0})
    assert made.status_code == 200, made.text
    course_id = made.json()["courses"][0]["id"]
    resp = await client.get(f"/v1/courses/{course_id}/scenery")
    assert resp.status_code == 200, resp.text
    for item in resp.json()["items"]:
        assert item["image"]["image_type"] == "actual" and item["image"]["is_actual_place_photo"]
        assert item["caption"]
    assert (await client.get("/v1/courses/nope/scenery")).status_code == 404
