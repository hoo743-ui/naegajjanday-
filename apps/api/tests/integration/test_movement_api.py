"""이동 모드 through the API (docs/65 §2 · §6): the request, the echo, re-plans that keep the promise."""

from __future__ import annotations

import math
from typing import Any

import httpx
from sqlalchemy import select

from app.core.deps import Container
from app.domain.models import GeoPoint
from app.domain.routing.travel_time import haversine_m
from app.evaluation.yardstick import locked_invariants
from app.infra.db.models import Course
from tests.conftest import GENERATE_BODY

LOCK = locked_invariants()
HONGDAE = GeoPoint(37.5572, 126.9245)  # data/seed/regions.json
# a "station" 600 m east of 홍대's centre: M1's 800 m around it leaves the west half of the sample out
STATION = GeoPoint(HONGDAE.lat, HONGDAE.lng + 600 / (111_195 * math.cos(math.radians(HONGDAE.lat))))


def body(**changes: Any) -> dict[str, Any]:
    return (
        GENERATE_BODY
        | {"alternatives": 0, "budget_total": 60000, "start_at": "2026-09-22T13:00:00+09:00"}
        | changes
    )


def at_station(**changes: Any) -> dict[str, Any]:
    out = body(**changes)
    out.pop("region")
    return out | {"origin": {"lat": STATION.lat, "lng": STATION.lng}, "origin_label": "샘플역"}


async def generated(
    client: httpx.AsyncClient, payload: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    made = await client.post("/v1/courses/generate", json=payload)
    assert made.status_code == 200, made.text
    course = made.json()["courses"][0]
    detail = (await client.get(f"/v1/courses/{course['id']}")).json()
    return course, detail


def point(stop: dict[str, Any]) -> GeoPoint:
    return GeoPoint(stop["place"]["lat"], stop["place"]["lng"])


async def test_an_omitted_mode_is_around_and_echoed(client: httpx.AsyncClient) -> None:
    course, detail = await generated(client, body())
    echo = detail["request"]
    assert echo["movement"] == "around"
    anchor = echo["movement_anchor"]
    assert (anchor["lat"], anchor["lng"], anchor["radius_m"]) == (
        HONGDAE.lat,
        HONGDAE.lng,
        LOCK["M2_radius_m"],
    )
    assert anchor["label"] == "홍대입구"
    assert echo["onward_to"] is None and echo["onward_anchor"] is None
    for stop in course["stops"]:
        assert haversine_m(HONGDAE, point(stop)) <= LOCK["M2_radius_m"]
        assert stop["from_prev"]["mode"] in ("walk", "transit")


async def test_m1_around_a_station_and_its_replacements(client: httpx.AsyncClient) -> None:
    course, detail = await generated(client, at_station(movement="inside"))
    echo = detail["request"]
    assert echo["movement"] == "inside" and echo["origin_label"] == "샘플역"
    anchor = echo["movement_anchor"]
    assert (anchor["lat"], anchor["lng"], anchor["radius_m"]) == (
        STATION.lat,
        STATION.lng,
        LOCK["M1_radius_m"],
    )
    for stop in course["stops"]:
        assert haversine_m(STATION, point(stop)) <= LOCK["M1_radius_m"]
        assert stop["from_prev"]["mode"] == "walk"
    for stop in course["stops"][1:]:
        assert stop["from_prev"]["travel_min"] <= LOCK["M2_walk_leg_max_min"]
    # a replacement keeps the promise of the course (docs/65 §6)
    for position in range(1, len(course["stops"]) + 1):
        found = await client.get(
            f"/v1/courses/{course['id']}/stops/{position}/candidates", params={"limit": 5}
        )
        assert found.status_code == 200, found.text
        for item in found.json()["items"]:
            far = haversine_m(STATION, GeoPoint(item["place"]["lat"], item["place"]["lng"]))
            assert far <= LOCK["M1_radius_m"], item["place"]["name"]


async def test_a_course_from_before_the_modes_is_not_held_to_one(
    client: httpx.AsyncClient, container: Container
) -> None:
    course, _detail = await generated(client, at_station(movement="inside"))
    async with container.db.sessionmaker() as session:
        row = (await session.execute(select(Course).where(Course.public_id == course["id"]))).scalar_one()
        row.request = {k: v for k, v in (row.request or {}).items() if k != "movement"}
        await session.commit()
    detail = (await client.get(f"/v1/courses/{course['id']}")).json()
    assert detail["request"]["movement"] is None and detail["request"]["movement_anchor"] is None
    beyond = []
    for position in range(1, len(course["stops"]) + 1):
        found = await client.get(
            f"/v1/courses/{course['id']}/stops/{position}/candidates", params={"limit": 5}
        )
        beyond += [
            i["place"]["name"]
            for i in found.json()["items"]
            if haversine_m(STATION, GeoPoint(i["place"]["lat"], i["place"]["lng"])) > LOCK["M1_radius_m"]
        ]
    assert beyond  # the old course's replacements reach as far as they always did


async def test_a_pinned_place_outside_the_range_is_left_out_and_said(client: httpx.AsyncClient) -> None:
    far = (await client.get("/v1/places/search", params={"region": "seoul-seongsu", "limit": 1})).json()[
        "items"
    ][0]
    course, _detail = await generated(client, body(movement="inside", keep_place_ids=[far["id"]]))
    assert far["id"] not in [s["place"]["id"] for s in course["stops"]]
    note = next(w for w in course["warnings"] if w["code"] == "KEPT_PLACE_DROPPED")
    assert note["meta"]["reason"] == "outside_movement" and note["meta"]["movement"] == "inside"
    assert "이 범위 밖이라 뺐어요" in note["detail"]


async def test_several_neighbourhoods_make_no_promise(client: httpx.AsyncClient) -> None:
    _course, detail = await generated(
        client, body(regions=["seoul-hongdae", "seoul-seongsu"], movement="inside")
    )
    assert detail["request"]["movement"] is None  # ignored there (docs/65 §6), the mode line is hidden


async def test_m3_to_a_named_neighbourhood(client: httpx.AsyncClient) -> None:
    course, detail = await generated(
        client, body(movement="onward", onward_to={"region": "seoul-seongsu", "label": "성수"})
    )
    echo = detail["request"]
    assert echo["movement"] == "onward"
    assert echo["onward_to"] == {"region": "seoul-seongsu", "origin": None, "label": "성수"}
    b = echo["onward_anchor"]
    assert (b["lat"], b["lng"], b["radius_m"]) == (37.5446, 127.0559, LOCK["M2_radius_m"])
    hop = [s for s in course["stops"] if s["from_prev"]["hop_to"]]
    assert len(hop) == 1 and hop[0]["from_prev"]["mode"] == "transit"
    at = course["stops"].index(hop[0])
    seongsu = GeoPoint(b["lat"], b["lng"])
    for i, stop in enumerate(course["stops"]):
        anchor = HONGDAE if i < at else seongsu
        assert haversine_m(anchor, point(stop)) <= LOCK["M2_radius_m"]


async def test_m3_without_a_neighbourhood_near_enough_stays_around(client: httpx.AsyncClient) -> None:
    """The seed has no neighbourhood with draws within a 15-minute ride of 홍대 (성수 is 35): M2, and said."""
    course, detail = await generated(client, body(movement="onward"))
    assert course["warnings"][0]["code"] == "ONWARD_NONE"
    assert detail["request"]["movement"] == "around" and detail["request"]["onward_to"] is None


async def test_the_request_is_checked(client: httpx.AsyncClient) -> None:
    for bad in ({"movement": "far"}, {"onward_to": {"region": "seoul-seongsu"}}):
        resp = await client.post("/v1/courses/generate", json=body(**bad))
        assert resp.status_code == 422, resp.text
    missing = await client.post(
        "/v1/courses/generate", json=body(movement="onward", onward_to={"region": "seoul-nowhere"})
    )
    assert missing.status_code == 404
