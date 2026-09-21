"""A day across several neighbourhoods: budget and time are handed forward, the ride is a leg like any other."""

from __future__ import annotations

from datetime import datetime, timedelta

from app.domain.models import CourseResult, GeoPoint, StopResult
from app.domain.recommendation.itinerary import (
    Hop,
    hop_between,
    itinerary_rules,
    leg_budget,
    leg_minutes,
    merge_legs,
)
from tests.factories import ORIGIN, place

RULES = itinerary_rules()
NOON = datetime(2026, 9, 26, 12, 0)


def _stop(position: int, at: datetime, price: int, walk_min: int = 5) -> StopResult:
    return StopResult(
        position=position,
        role="MEAL",
        place=place("MEAL", price=price // 2),
        arrive_at=at,
        leave_at=at + timedelta(minutes=60),
        est_price=price,
        travel_min_from_prev=walk_min,
        distance_m_from_prev=walk_min * 70,
        score=0.5,
        score_breakdown={},
        congestion=None,
        slot_budget=float(price),
    )


def _leg(start: datetime, prices: list[int]) -> CourseResult:
    stops = [_stop(i + 1, start + timedelta(minutes=70 * i), p) for i, p in enumerate(prices)]
    return CourseResult(
        label="x",
        template_id=1,
        stops=stops,
        total_price=sum(prices),
        total_travel_min=5 * len(prices),
        total_distance_m=350 * len(prices),
        duration_min=70 * len(prices),
        score=0.5,
        objective=1.0,
        optimizer="beam",
    )


def test_what_one_neighbourhood_does_not_spend_is_the_next_ones_to_use() -> None:
    assert leg_budget(100_000, 2, RULES) == 50_000
    assert leg_budget(100_000 - 32_000, 1, RULES) == 68_000  # the first leg under-spent: the second gets more
    assert (
        leg_budget(500, 3, RULES) == RULES["budget_round"]
    )  # never zero: the engine needs a floor to say "too low"


def test_time_is_split_evenly_and_defaults_when_the_user_gave_none() -> None:
    assert leg_minutes(360, 2, RULES) == 180
    assert leg_minutes(None, 2, RULES) == RULES["leg_default_min"]
    assert leg_minutes(60, 3, RULES) == RULES["leg_min_min"]  # a leg shorter than this is not a visit


def test_a_short_hop_is_walked_and_a_long_one_is_ridden() -> None:
    near = GeoPoint(ORIGIN.lat + 0.005, ORIGIN.lng)  # ~550 m
    far = GeoPoint(ORIGIN.lat + 0.05, ORIGIN.lng)  # ~5.5 km
    assert hop_between(ORIGIN, near, "walk", RULES).mode == "walk"
    ride = hop_between(ORIGIN, far, "walk", RULES)
    assert ride.mode == RULES["hop_mode"] and ride.minutes > RULES["hop_overhead_min"][ride.mode]
    assert hop_between(ORIGIN, far, "car", RULES).mode == "car"  # someone who drives keeps driving


def test_legs_are_joined_in_order_and_the_ride_counts_like_any_other_move() -> None:
    first, second = _leg(NOON, [20_000, 8_000]), _leg(NOON + timedelta(hours=3), [30_000])
    merged, hop_at = merge_legs([first, second], [Hop("transit", 18, 5200)])

    assert [s.position for s in merged.stops] == [1, 2, 3]
    assert hop_at == {3: Hop("transit", 18, 5200)}
    assert merged.stops[2].travel_min_from_prev == 18 + 5  # the ride, then the walk to the door
    assert merged.total_price == 58_000
    assert merged.total_travel_min == 5 + 5 + 23
    assert merged.duration_min >= 180  # from the first arrival to the last goodbye, the ride included
