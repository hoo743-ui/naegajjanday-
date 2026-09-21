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
