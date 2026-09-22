"""Route Intelligence (docs/27): NAVER Directions parsing/chunking, route validation, and the route service."""

from __future__ import annotations

from datetime import datetime, timedelta
from itertools import pairwise
from typing import Any

import httpx
import pytest

from app.core.cache import MemoryCache
from app.core.config import Settings
from app.domain.models import GeoPoint, OpeningPeriod
from app.domain.routing.route_check import CheckLeg, CheckStop, check_route
from app.infra.routing.naver_maps import NaverMapsClient, NaverMapsError, chunk_points, split_route
from app.services.directions_service import DirectionsService
from app.services.route_service import RouteInputStop, RouteService

T0 = datetime(2026, 9, 25, 18, 0)
HONGDAE = [(37.5563, 126.9236), (37.5547, 126.9215), (37.5530, 126.9190), (37.5512, 126.9160)]


def settings(**kw: Any) -> Settings:
    base: dict[str, Any] = {"_env_file": None, "app_env": "test", "jwt_secret": "x" * 40, "osrm_foot_url": ""}
    return Settings(**{**base, **kw})


def naver_settings() -> Settings:
    return settings(naver_map_client_id="id", naver_map_client_secret="secret")


def fake_naver_route(points: list[tuple[float, float]]) -> dict[str, Any]:
    """A NAVER Directions body for start, waypoints…, goal: 400 m and 2 minutes per leg, 3 path points per leg."""
    path: list[list[float]] = []
    waypoints = []
    for i, (lat, lng) in enumerate(points):
        if i > 0:
            plat, plng = points[i - 1]
            path.append([(plng + lng) / 2, (plat + lat) / 2])
        path.append([lng, lat])
        if 0 < i < len(points) - 1:
            waypoints.append(
                {"location": [lng, lat], "distance": 400, "duration": 120_000, "pointIndex": len(path) - 1}
            )
    legs = len(points) - 1
    return {
        "code": 0,
        "route": {
            "traoptimal": [
                {
                    "summary": {"distance": 400 * legs, "duration": 120_000 * legs, "waypoints": waypoints},
                    "path": path,
                }
            ]
        },
    }


def parse_points(request: httpx.Request) -> list[tuple[float, float]]:
    q = request.url.params

    def one(s: str) -> tuple[float, float]:
        lng, lat = s.split(",")
        return float(lat), float(lng)

    pts = [one(q["start"])]
    if q.get("waypoints"):
        pts += [one(w) for w in q["waypoints"].split("|")]
    pts.append(one(q["goal"]))
    return pts


# --- NAVER Directions ------------------------------------------------------------------------------


def test_chunks_share_their_boundary_and_keep_every_leg() -> None:
    pts = [GeoPoint(37.5 + i * 0.001, 127.0) for i in range(20)]
    chunks = chunk_points(pts)
    assert [len(c) for c in chunks] == [17, 4]  # start + 15 waypoints + goal, then the rest
    assert chunks[0][-1] == chunks[1][0]
    assert sum(len(c) - 1 for c in chunks) == len(pts) - 1
    assert chunk_points(pts[:1]) == []


def test_split_route_cuts_the_path_at_each_waypoint() -> None:
    route = fake_naver_route(HONGDAE)["route"]["traoptimal"][0]
    legs = split_route(route, 3)
    assert [leg.distance_m for leg in legs] == [400, 400, 400]
    assert [leg.duration_min for leg in legs] == [2, 2, 2]
    assert legs[0].path[0] == HONGDAE[0] and legs[0].path[-1] == HONGDAE[1]
    assert legs[2].path[-1] == HONGDAE[3]


def test_split_route_rejects_a_summary_without_the_waypoints() -> None:
    route = fake_naver_route(HONGDAE)["route"]["traoptimal"][0]
    route["summary"]["waypoints"] = []
    with pytest.raises(NaverMapsError):
        split_route(route, 3)


async def test_driving_uses_directions5_then_directions15_and_sends_keys_from_the_server() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=fake_naver_route(parse_points(request)))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        naver = NaverMapsClient(naver_settings(), client)
        five = [GeoPoint(37.55 + i * 0.001, 126.92) for i in range(7)]  # 5 waypoints
        legs = await naver.driving(five)
        assert len(legs) == 6 and seen[-1].url.path == "/map-direction/v1/driving"
        eight = [GeoPoint(37.55 + i * 0.001, 126.92) for i in range(8)]  # 6 waypoints
        legs = await naver.driving(eight)
        assert len(legs) == 7 and seen[-1].url.path == "/map-direction-15/v1/driving"
        twenty = [GeoPoint(37.55 + i * 0.001, 126.92) for i in range(20)]
        legs = await naver.driving(twenty)
        assert len(legs) == 19  # two requests joined into one itinerary
    assert seen[0].headers["x-ncp-apigw-api-key-id"] == "id"
    assert seen[0].headers["x-ncp-apigw-api-key"] == "secret"
    assert seen[0].url.params["option"] == "traoptimal"


async def test_driving_raises_with_the_naver_reason() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"code": 2, "message": "no road"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(NaverMapsError) as err:
            await NaverMapsClient(naver_settings(), client).driving(
                [GeoPoint(37.5, 127.0), GeoPoint(37.6, 127.1)]
            )
    assert err.value.code == 2 and "도로" in str(err.value)


async def test_geocode_reads_x_as_longitude() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/map-geocode/v2/geocode"
        return httpx.Response(200, json={"status": "OK", "addresses": [{"x": "126.9236", "y": "37.5563"}]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        point = await NaverMapsClient(naver_settings(), client).geocode("서울 마포구 양화로 160")
    assert point == GeoPoint(37.5563, 126.9236)


async def test_without_keys_nothing_is_called() -> None:
    naver = NaverMapsClient(settings())
    assert not naver.configured
    with pytest.raises(NaverMapsError):
        await naver.driving([GeoPoint(37.5, 127.0), GeoPoint(37.6, 127.1)])


# --- validation ------------------------------------------------------------------------------------


def stop(
    seq: int, name: str, lat: float | None, lng: float | None, arrive: int, leave: int, **kw: Any
) -> CheckStop:
    return CheckStop(
        seq,
        kw.pop("pid", f"p{seq}"),
        name,
        lat,
        lng,
        T0 + timedelta(minutes=arrive),
        T0 + timedelta(minutes=leave),
        **kw,
    )


def codes(result: Any) -> list[str]:
    return [i.code for i in result.issues]


def test_a_walkable_day_has_no_issues() -> None:
    stops = [stop(1, "카페", *HONGDAE[0], 0, 60), stop(2, "산책", *HONGDAE[1], 70, 100)]
    result = check_route(stops, [CheckLeg(1, 2, "walk", 8, 650, "osrm")])
    assert result.issues == [] and result.feasible


def test_missing_and_foreign_coordinates_are_errors() -> None:
    stops = [stop(1, "어딘가", None, None, 0, 60), stop(2, "도쿄", 35.68, 139.76, 70, 100)]
    result = check_route(stops, [CheckLeg(1, 2, "walk", None, None, "unavailable")])
    assert {"NO_COORDINATES", "BAD_COORDINATES", "ROUTE_UNAVAILABLE"} <= set(codes(result))
    assert not result.feasible


def test_the_same_place_twice_and_a_broken_order() -> None:
    stops = [stop(1, "카페", *HONGDAE[0], 0, 60, pid="a"), stop(2, "카페", *HONGDAE[0], 50, 90, pid="a")]
    result = check_route(stops, [CheckLeg(1, 2, "walk", 1, 10, "osrm")])
    assert "DUPLICATE_STOP" in codes(result) and "ORDER_BROKEN" in codes(result)


def test_seoul_to_busan_in_an_hour_breaks_the_day() -> None:
    stops = [
        stop(1, "성수 카페", 37.5445, 127.0557, 0, 60),
        stop(2, "해운대 점심", 35.1587, 129.1604, 120, 180),
    ]
    result = check_route(stops, [CheckLeg(1, 2, "car", 260, 400_000, "estimate")])
    assert "LEG_TOO_FAR" in codes(result) and "UNREALISTIC_LEG" in codes(result)
    assert not result.feasible


def test_a_slow_leg_makes_the_next_stop_late_then_closed() -> None:
    museum = [OpeningPeriod(dow, 600, 19 * 60) for dow in range(7)]  # 10:00-19:00
    stops = [
        stop(1, "카페", *HONGDAE[0], 0, 45),  # 18:00-18:45
        stop(2, "전시", *HONGDAE[1], 55, 50 + 5 + 0, opening_hours=museum),  # 18:55 (open till 19:00)
    ]
    result = check_route(stops, [CheckLeg(1, 2, "walk", 40, 2_500, "osrm")])
    assert "LEG_TOO_LONG" in codes(result)
    assert "SCHEDULE_BREAKS" in codes(result) and not result.feasible


def test_a_stop_closed_at_its_visit_time_is_flagged() -> None:
    lunch_only = [OpeningPeriod(dow, 11 * 60, 15 * 60) for dow in range(7)]
    stops = [stop(1, "점심집", *HONGDAE[0], 0, 60, opening_hours=lunch_only)]
    assert codes(check_route(stops, [])) == ["CLOSED_AT_VISIT"]


def test_a_quicker_leg_absorbs_an_earlier_delay() -> None:
    stops = [
        stop(1, "A", *HONGDAE[0], 0, 30),
        stop(2, "B", *HONGDAE[1], 40, 70),
        stop(3, "C", *HONGDAE[2], 100, 130),
    ]
    legs = [
        CheckLeg(1, 2, "walk", 25, 1_500, "osrm"),
        CheckLeg(2, 3, "walk", 5, 300, "osrm"),
    ]  # +15, then -25
    result = check_route(stops, legs)
    assert codes(result) == ["LEG_TOO_LONG"] and result.feasible


# --- the service -----------------------------------------------------------------------------------


def inp(seq: int, lat: float | None, lng: float | None, mode: str = "walk", **kw: Any) -> RouteInputStop:
    return RouteInputStop(
        sequence=seq,
        place_id=f"p{seq}",
        name=f"장소{seq}",
        address=kw.get("address"),
        lat=lat,
        lng=lng,
        arrive_at=T0 + timedelta(minutes=seq * 60),
        leave_at=T0 + timedelta(minutes=seq * 60 + 40),
        price=10_000,
        opening_hours=[],
        mode=mode,  # type: ignore[arg-type]
        hop_to=None,
        est_minutes=7,
        est_distance_m=500,
    )


def osrm_body(points: list[tuple[float, float]]) -> dict[str, Any]:
    legs = [
        {
            "distance": 480,
            "duration": 360,
            "steps": [{"geometry": {"coordinates": [[a[1], a[0]], [b[1], b[0]]]}}],
        }
        for a, b in pairwise(points)
    ]
    coords = [[lng, lat] for lat, lng in points]
    return {
        "routes": [
            {
                "distance": 480 * len(legs),
                "duration": 360 * len(legs),
                "geometry": {"coordinates": coords},
                "legs": legs,
            }
        ]
    }


async def test_walking_course_is_measured_by_the_foot_router() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raw = request.url.path.rsplit("/", 1)[-1]
        pts = [(float(x.split(",")[1]), float(x.split(",")[0])) for x in raw.split(";")]
        return httpx.Response(200, json=osrm_body(pts))

    s = settings(osrm_foot_url="http://osrm.test")
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        service = RouteService(s, MemoryCache(), directions=DirectionsService(s, client))
        route = await service.build("c1", "walk", [inp(i + 1, *HONGDAE[i]) for i in range(4)])
    assert [leg.source for leg in route.legs] == ["osrm"] * 3
    assert [leg.duration_min for leg in route.legs] == [6, 6, 6]
    assert route.totals.measured and route.totals.travel_min == 18
    assert route.legs[0].geometry == "road" and len(route.legs[0].path) >= 2
    assert route.providers.walk == "osrm" and route.providers.car == "estimate"


async def test_car_without_naver_keys_keeps_the_engine_estimate_and_says_so() -> None:
    route = await RouteService(settings(), MemoryCache()).build(
        "c1", "car", [inp(i + 1, *HONGDAE[i], "car") for i in range(3)]
    )
    assert [leg.source for leg in route.legs] == ["estimate", "estimate"]
    assert [leg.geometry for leg in route.legs] == ["straight", "straight"]
    assert not route.totals.measured


async def test_car_with_naver_keys_uses_directions_and_caches_the_result() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json=fake_naver_route(parse_points(request)))

    cache = MemoryCache()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        s = naver_settings()
        service = RouteService(s, cache, naver=NaverMapsClient(s, client))
        stops = [inp(i + 1, *HONGDAE[i], "car") for i in range(4)]
        first = await service.build("c1", "car", stops)
        second = await service.build("c1", "car", stops)
    assert [leg.source for leg in first.legs] == ["naver"] * 3
    assert first.providers.car == "naver"
    assert calls == 1 and second.legs[0].distance_m == 400  # the second one came from the cache


async def test_naver_failure_falls_back_to_the_estimate() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        s = naver_settings()
        route = await RouteService(s, MemoryCache(), naver=NaverMapsClient(s, client)).build(
            "c1", "car", [inp(1, *HONGDAE[0], "car"), inp(2, *HONGDAE[1], "car")]
        )
    assert route.legs[0].source == "estimate" and route.legs[0].duration_min == 7


async def test_a_stop_without_coordinates_is_geocoded_once_or_marked_unavailable() -> None:
    no_keys = await RouteService(settings(), MemoryCache()).build(
        "c1", "walk", [inp(1, *HONGDAE[0]), inp(2, None, None)]
    )
    assert no_keys.legs[0].source == "unavailable" and not no_keys.feasible
    assert "NO_COORDINATES" in [i.code for i in no_keys.issues]

    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"status": "OK", "addresses": [{"x": "126.9215", "y": "37.5547"}]})

    cache = MemoryCache()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        s = naver_settings()
        service = RouteService(s, cache, naver=NaverMapsClient(s, client))
        stops = [inp(1, *HONGDAE[0]), inp(2, None, None, address="서울 마포구 홍익로 10")]
        for _ in range(2):
            route = await service.build("c1", "walk", stops)
    assert route.stops[1].lat == 37.5547 and route.legs[0].source == "estimate"
    assert calls == 1  # geocoded once, then from the cache
