"""docs/34: the anchor strategy's rules — data, not code."""

from __future__ import annotations

from dataclasses import replace
from datetime import date

from app.domain.anchors import AnchoredEvent, campus_first, event_window, pick_festival, plan_for
from app.domain.models import Slot, Template
from app.domain.recommendation.style import wanted_events, wanted_places
from tests.factories import place


def ev(id: int, *, anchored: bool, priority: int = 0, distance_m: float = 100.0) -> AnchoredEvent:
    day = date(2026, 9, 20)
    return AnchoredEvent(id, f"e{id}", day, day, "18:00", "22:00", priority, anchored, distance_m)


def test_reach_grows_with_the_transport_and_the_purpose() -> None:
    food_walk = plan_for("campus_food", "walk")
    assert food_walk.campus_stop == "none" and food_walk.radius_m == 1000
    assert plan_for("campus_food", "transit").radius_m > food_walk.radius_m
    assert plan_for("date", "walk").radius_m > food_walk.radius_m  # a date reaches further than lunch
    campus = plan_for("campus", "walk")
    assert campus.campus_stop == "required" and "CAMPUS_WALK" in campus.intents
    assert plan_for("festival", "walk").festival == "core"
    assert plan_for("solo", "walk").campus_stop == "optional"  # any other purpose: the defaults


def test_the_campus_own_festival_beats_a_nearby_one() -> None:
    assert pick_festival([]) is None
    nearby, own = ev(1, anchored=False, priority=50, distance_m=10), ev(2, anchored=True)
    assert pick_festival([nearby, own]) is own
    assert pick_festival([ev(3, anchored=True, priority=1), ev(4, anchored=True, priority=9)]).id == 4  # type: ignore[union-attr]


def test_event_hours_become_an_opening_window() -> None:
    assert event_window("18:00", "22:00") == (18 * 60, 22 * 60)
    assert event_window("20:00", "02:00") == (20 * 60, 26 * 60)  # past midnight
    assert event_window(None, "22:00") is None and event_window("x", "y") is None


def test_event_ids_and_place_ids_never_answer_for_each_other() -> None:
    shop = place("CULTURE", "culture.museum", 0, id=7)
    festival = place("CULTURE", "culture.festival", 0, id=7, is_event=True)
    pools = {1: [shop, festival]}
    assert wanted_places(pools, frozenset({7}))[1] == [shop]
    assert wanted_events(pools, frozenset({7}))[1] == [festival]
    assert wanted_events(pools, frozenset())[1] == [shop, festival]


def test_the_campus_walk_opens_the_day() -> None:
    lunch = Template(
        id=1,
        code="x-lunch",
        purpose_code="x",
        time_band="lunch",
        min_budget_per_person=5000,
        party_min=1,
        party_max=8,
        slots=(Slot(1, "MEAL", 0.7), Slot(2, "CAFE", 0.3)),
    )
    (opened,) = campus_first([lunch])
    assert [s.course_role for s in sorted(opened.slots, key=lambda s: s.position)] == [
        "ATTRACTION",
        "MEAL",
        "CAFE",
    ]
    assert abs(sum(s.budget_share for s in opened.slots) - 1.0) < 1e-9
    sight = replace(
        lunch,
        slots=(Slot(1, "MEAL", 0.6), Slot(2, "ATTRACTION", 0.1, is_optional=True), Slot(3, "CAFE", 0.3)),
    )
    (kept,) = campus_first([sight])  # a sight slot already there: it stays where it is, now certain
    assert [s.course_role for s in kept.slots] == ["MEAL", "ATTRACTION", "CAFE"] and not kept.slots[
        1
    ].is_optional
