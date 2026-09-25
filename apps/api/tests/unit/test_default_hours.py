from __future__ import annotations

from datetime import datetime

from app.domain.recommendation.features import is_open
from app.infra.default_hours import DefaultHours, get_default_hours

MON_2030 = datetime(2026, 9, 21, 20, 30)  # 월요일
TUE_1400 = datetime(2026, 9, 22, 14, 0)
TUE_2030 = datetime(2026, 9, 22, 20, 30)
WED_0030 = datetime(2026, 9, 23, 0, 30)


def test_most_specific_category_wins_and_unknown_means_no_restriction() -> None:
    hours = DefaultHours(
        {
            "culture": {"open": "10:00", "close": "18:00"},
            "culture.cinema": {"open": "10:00", "close": "23:30"},
        }
    )
    assert is_open(hours.for_category("culture.cinema"), TUE_2030)
    assert not is_open(hours.for_category("culture.museum"), TUE_2030)  # falls back to "culture"
    assert hours.for_category("attraction.park") == ()  # nothing known → always open


def test_shipped_table_blocks_the_evening_museum_but_not_the_street() -> None:
    table = get_default_hours()
    museum, street, market = (
        table.for_category(c) for c in ("culture.museum", "attraction.street", "attraction.market")
    )
    assert is_open(museum, TUE_1400) and not is_open(museum, TUE_2030)
    assert not is_open(museum, MON_2030.replace(hour=14))  # 월요일 휴관
    assert is_open(street, TUE_2030) and is_open(table.for_category("attraction.park"), WED_0030)
    assert not is_open(market, TUE_2030)


def test_bar_hours_run_past_midnight() -> None:
    bar = get_default_hours().for_category("bar.pub")
    assert not is_open(bar, TUE_1400) and is_open(bar, TUE_2030) and is_open(bar, WED_0030)


def test_an_always_open_place_with_a_floor_is_inside_a_building() -> None:
    # 2026-09-25: '풍월당'(음반 매장, 4층)이 '거리'로 들어와 밤 11시 코스에 나왔다
    hours = get_default_hours()
    shop = hours.for_place("attraction.street", "풍월당", "서울특별시 강남구 도산대로53길 39 (신사동) 4층")
    assert shop and shop[0].close_min == 21 * 60
    tower = hours.for_place("nightview.observatory", "롯데월드타워 서울스카이", "올림픽로 300 (신천동) 117~123층")
    assert tower and tower[0].close_min == 22 * 60
    # an underground road number is not a floor: a plaza above a subway station stays open
    assert hours.for_place("attraction.park", "서울광장", "서울특별시 중구 을지로 지하12 (을지로1가)") == ()
    assert hours.for_place("attraction.street", "홍대걷고싶은거리", None) == ()
    # a mall filed as a street closes with the mall
    mall = hours.for_place("attraction.street", "센트럴시티", "서울특별시 서초구 신반포로 176 (반포동)")
    assert mall and mall[0].close_min == 22 * 60
