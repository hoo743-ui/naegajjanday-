"""docs/46: 가는 길에 들를 곳(돌아가는 거리) · 확인할 수 있는 평판 신호."""

from __future__ import annotations

from app.domain.models import GeoPoint
from app.services.along_service import detour_m, detour_minutes, off_route_m
from app.services.signal_service import Signal, order, visited_signal

A = GeoPoint(37.5700, 126.9900)
B = GeoPoint(37.5700, 127.0000)  # ~880 m east


def test_a_place_on_the_line_costs_no_detour() -> None:
    mid = GeoPoint(37.5700, 126.9950)
    assert detour_m(A, B, mid) < 1
    assert off_route_m(A, B, mid) < 1


def test_a_place_off_the_line() -> None:
    side = GeoPoint(37.5720, 126.9950)  # ~220 m north of the middle
    assert 200 < off_route_m(A, B, side) < 240
    assert 90 < detour_m(A, B, side) < 120
    # beyond the ends the distance is to the nearest end, not to the infinite line
    past = GeoPoint(37.5700, 127.0030)
    assert 250 < off_route_m(A, B, past) < 290


def test_detour_minutes_are_walking_minutes_rounded_up_to_one() -> None:
    assert detour_minutes(0) == 1
    assert detour_minutes(107.2) == 2  # 107 m × 1.25 / 67 m per min


def test_visited_signal_names_the_district_rank_and_month() -> None:
    s = visited_signal({"rank": 2, "district": "성동구", "month": "202608"})
    assert s is not None
    assert s.label == "성동구에서 사람들이 찾아간 곳 2위"
    assert s.source == "티맵 내비게이션 목적지 실측 (2026년 8월)"
    top = visited_signal({"rank": 1, "district": "경주시", "month": "202608"})
    assert top is not None and top.label == "경주시에서 사람들이 가장 많이 찾아간 곳"
    assert visited_signal({}) is None
    assert visited_signal({"rank": 0, "district": "x"}) is None


def test_signals_are_ordered_and_deduplicated() -> None:
    signals = [
        Signal(kind="long_run", label="영업 신고 30년 넘은 곳", source="지자체 인허가 기록"),
        Signal(kind="designated", label="백년가게", source="중소벤처기업부 지정"),
        Signal(kind="designated", label="백년가게", source="중소벤처기업부 지정"),
        Signal(kind="visited", label="성동구에서 사람들이 찾아간 곳 2위", source="티맵"),
    ]
    assert [s.label for s in order(signals)] == [
        "성동구에서 사람들이 찾아간 곳 2위",
        "백년가게",
        "영업 신고 30년 넘은 곳",
    ]
