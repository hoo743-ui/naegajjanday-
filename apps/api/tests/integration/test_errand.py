"""가는 김에 (docs/51 B1): the day is planned around a place the user has to go anyway."""

from __future__ import annotations

import httpx

from tests.conftest import GENERATE_BODY


async def test_spots_finds_our_places_by_name(client: httpx.AsyncClient) -> None:
    anywhere = (await client.get("/v1/places/search", params={"region": "seoul-hongdae", "limit": 1})).json()
    name = anywhere["items"][0]["name"]
    found = (await client.get("/v1/meta/spots", params={"q": name[:4]})).json()["items"]
    assert found and found[0]["source"] == "ours" and found[0]["place_id"]
    assert (await client.get("/v1/meta/spots", params={"q": "a"})).status_code == 422


async def test_an_errand_with_time_starts_the_course_after_it(client: httpx.AsyncClient) -> None:
    body = {k: v for k, v in GENERATE_BODY.items() if k != "region"}
    errand = {"name": "애플 가로수길", "lat": 37.5205, "lng": 127.0229, "minutes": 40}
    body |= {
        "budget_total": 62000,
        "alternatives": 0,
        "start_at": "2026-09-20T14:00:00+09:00",
        "errand": errand,
    }
    made = await client.post("/v1/courses/generate", json=body)
    assert made.status_code == 200, made.text
    course = made.json()["courses"][0]
    note = next(w for w in course["warnings"] if w["code"] == "ERRAND")
    assert "애플 가로수길에서 40분" in note["detail"] and "14:40" in note["detail"]
    assert course["stops"][0]["arrive_at"] >= "2026-09-20T14:40"
    detail = (await client.get(f"/v1/courses/{course['id']}")).json()["request"]
    assert detail["errand"]["name"] == "애플 가로수길" and detail["errand"]["minutes"] == 40
    assert detail["start_at"].startswith(
        "2026-09-20T14:00"
    )  # what was asked, so a reroll does not shift twice
    assert detail["origin_label"] == "애플 가로수길"


async def test_one_of_our_places_without_time_is_a_stop(client: httpx.AsyncClient) -> None:
    near = (await client.get("/v1/places/search", params={"region": "seoul-hongdae", "limit": 50})).json()[
        "items"
    ]
    target = next(p for p in near if p.get("lat") and p.get("role") == "MEAL")
    errand = {"name": target["name"], "lat": target["lat"], "lng": target["lng"], "place_id": target["id"]}
    body = {k: v for k, v in GENERATE_BODY.items() if k != "region"} | {
        "budget_total": 90000,
        "alternatives": 0,
        "errand": errand,
    }
    made = await client.post("/v1/courses/generate", json=body)
    assert made.status_code == 200, made.text
    course = made.json()["courses"][0]
    assert target["id"] in [s["place"]["id"] for s in course["stops"]]
