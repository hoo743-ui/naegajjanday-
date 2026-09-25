"""누구와 (docs/48): the scene a day is planned for — offered by the purpose, kept by the course."""

from __future__ import annotations

import httpx

from app.domain.recommendation.style import resolve_scene
from tests.conftest import GENERATE_BODY


async def test_purposes_offer_their_scenes(client: httpx.AsyncClient) -> None:
    items = {p["code"]: p for p in (await client.get("/v1/meta/purposes")).json()["items"]}
    date = items["date"]
    assert [s["code"] for s in date["scenes"]] == ["new", "steady", "anniversary"] and date[
        "default_scene"
    ] is None
    assert date["scene_question"]
    if "family" in items:
        assert items["family"]["default_scene"] == "kids"
    assert items.get("friends", {}).get("scenes", []) == []


async def test_a_course_keeps_its_scene_and_names_it(client: httpx.AsyncClient) -> None:
    body = {**GENERATE_BODY, "budget_total": 60000, "scene": "anniversary", "alternatives": 0}
    made = await client.post("/v1/courses/generate", json=body)
    assert made.status_code == 200, made.text
    detail = (await client.get(f"/v1/courses/{made.json()['courses'][0]['id']}")).json()
    assert detail["request"]["scene"] == "anniversary" and detail["request"]["scene_label"] == "기념일"


async def test_a_scene_the_purpose_does_not_have_is_ignored(client: httpx.AsyncClient) -> None:
    body = {**GENERATE_BODY, "budget_total": 61000, "scene": "parents", "alternatives": 0}
    made = await client.post("/v1/courses/generate", json=body)
    assert made.status_code == 200, made.text
    detail = (await client.get(f"/v1/courses/{made.json()['courses'][0]['id']}")).json()
    assert detail["request"]["scene"] is None and detail["request"]["scene_label"] is None


def test_family_defaults_to_kids_and_parents_keep_away_from_karaoke() -> None:
    assert resolve_scene("family", None)[0] == "kids"
    assert resolve_scene("family", "nonsense")[0] == "kids"
    key, parents = resolve_scene("family", "parents")
    assert key == "parents" and "activity.karaoke" in parents["blocked_categories"]
    assert resolve_scene("date", None) == (None, {})
    assert resolve_scene("friends", "kids") == (None, {})


async def test_with_children_a_night_is_planned_for_that_evening(client: httpx.AsyncClient) -> None:
    # 창업자 결정 (2026-09-25): 아이와의 밤 코스는 만들지 않고 그날 저녁으로 당긴다 — 그렇게 했다고 말한다
    night = {**GENERATE_BODY, "purpose": "family", "party_size": 3, "budget_total": 90000,
             "start_at": "2026-09-26T22:00:00+09:00", "alternatives": 0}  # fmt: skip
    kids = await client.post("/v1/courses/generate", json=night)
    assert kids.status_code == 200, kids.text
    course = kids.json()["courses"][0]
    assert course["stops"][0]["arrive_at"].startswith("2026-09-26T17:") or course["stops"][0][
        "arrive_at"
    ].startswith("2026-09-26T18:")
    notes = [w for w in course["warnings"] if w["code"] == "SCENE_EARLIER"]
    assert notes and "17시 30분" in notes[0]["detail"]
    detail = (await client.get(f"/v1/courses/{course['id']}")).json()
    assert detail["request"]["start_at"].startswith("2026-09-26T17:30")

    parents = await client.post(
        "/v1/courses/generate", json={**night, "scene": "parents", "budget_total": 91000}
    )
    assert parents.status_code == 200, parents.text
    assert not [w for w in parents.json()["courses"][0]["warnings"] if w["code"] == "SCENE_EARLIER"]
