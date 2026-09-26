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
    assert course["errand_leg"] is None  # the errand is a stop: no leg of its own


# founder (2026-09-26): the place one has to go and the place one plays are often not the same —
# Apple 가로수길 first, then a day in 홍대. The errand is an option of the course, not its region.
FAR_ERRAND = {"name": "애플 가로수길", "lat": 37.5205, "lng": 127.0229, "minutes": 60}


async def test_an_errand_far_before_the_day_starts_it_after_the_ride_over(client: httpx.AsyncClient) -> None:
    body = GENERATE_BODY | {
        "budget_total": 62000,
        "alternatives": 0,
        "start_at": "2026-09-20T13:00:00+09:00",
        "errand": FAR_ERRAND | {"when": "before"},
    }
    made = await client.post("/v1/courses/generate", json=body)
    assert made.status_code == 200, made.text
    course = made.json()["courses"][0]
    note = next(w for w in course["warnings"] if w["code"] == "ERRAND")
    travel = note["meta"]["travel_min"]
    assert travel >= 10 and note["meta"]["when"] == "before"
    assert f"애플 가로수길에 먼저 들렀다가 약 {travel}분 이동해" in note["detail"]
    starts = f"2026-09-20T{14 + travel // 60:02d}:{travel % 60:02d}"
    assert course["stops"][0]["arrive_at"] >= starts  # after the errand and the ride, not from 13:00
    # docs/59 #7: the ride from the errand to the first stop is a leg of the course the map draws
    leg = course["errand_leg"]
    assert leg["when"] == "before" and leg["name"] == "애플 가로수길" and leg["minutes"] == 60
    assert leg["travel_min"] >= 10 and leg["distance_m"] > 3000 and leg["mode"] == "transit"
    assert (leg["lat"], leg["lng"]) == (FAR_ERRAND["lat"], FAR_ERRAND["lng"])
    echo = (await client.get(f"/v1/courses/{course['id']}")).json()["request"]
    assert echo["region"]["slug"] == "seoul-hongdae"  # the day stays where they want to play
    assert echo["origin"] is None
    assert echo["errand"]["when"] == "before" and echo["errand"]["minutes"] == 60
    assert echo["start_at"].startswith("2026-09-20T13:00")  # a reroll does not shift twice


async def test_an_errand_far_after_the_day_ends_it_in_time(client: httpx.AsyncClient) -> None:
    body = GENERATE_BODY | {
        "budget_total": 62000,
        "alternatives": 0,
        "start_at": "2026-09-20T13:00:00+09:00",
        "duration_min": 360,
        "errand": FAR_ERRAND | {"when": "after"},
    }
    made = await client.post("/v1/courses/generate", json=body)
    assert made.status_code == 200, made.text
    course = made.json()["courses"][0]
    note = next(w for w in course["warnings"] if w["code"] == "ERRAND")
    travel = note["meta"]["travel_min"]
    assert f"끝나고 애플 가로수길까지 약 {travel}분" in note["detail"]
    assert course["stops"][0]["arrive_at"] < "2026-09-20T14:00"  # it starts when asked
    ends_by = 13 * 60 + 360 - 60 - travel
    last = course["stops"][-1]["leave_at"][11:16]
    assert int(last[:2]) * 60 + int(last[3:]) <= ends_by + 15  # the stay rounding may run a little over
    detail = (await client.get(f"/v1/courses/{course['id']}")).json()
    echo = detail["request"]
    assert echo["duration_min"] == 360 and echo["errand"]["when"] == "after"  # as asked
    # docs/59 #7: the ride from the last stop to the errand, on the saved course too
    leg = detail["course"]["errand_leg"]
    assert leg["when"] == "after" and leg["travel_min"] >= 10 and leg["distance_m"] > 3000


async def test_an_errand_in_the_region_is_where_the_day_starts(client: httpx.AsyncClient) -> None:
    region = (await client.get("/v1/meta/regions/seoul-hongdae")).json()
    near = {
        "name": "홍대 친구네",
        "lat": region["center"]["lat"] + 0.002,
        "lng": region["center"]["lng"],
        "minutes": 30,
        "when": "after",  # near it, an errand after is only time left at the end — no ride
    }
    body = GENERATE_BODY | {"budget_total": 62000, "alternatives": 0, "duration_min": 240, "errand": near}
    made = await client.post("/v1/courses/generate", json=body)
    assert made.status_code == 200, made.text
    course = made.json()["courses"][0]
    note = next(w for w in course["warnings"] if w["code"] == "ERRAND")
    assert "travel_min" not in note["meta"] and "30분 볼일 볼 시간" in note["detail"]
    echo = (await client.get(f"/v1/courses/{course['id']}")).json()["request"]
    assert echo["origin_label"] == "홍대 친구네"  # the day is planned around it, as before
    assert echo["origin"] is not None and echo["region"]["slug"] == "seoul-hongdae"
