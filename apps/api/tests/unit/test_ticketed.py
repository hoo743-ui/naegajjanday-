"""입장권이 있어야 들어가는 곳 (recommendation.ticketed, data/recommendation/ticketed_venues.json)."""

from __future__ import annotations

from app.domain.models import GeoPoint, Slot
from app.domain.recommendation import budget as B
from app.domain.recommendation.composer import INSIDE_GATE_PULL, CourseComposer
from app.domain.recommendation.scorer import PlaceScorer
from app.domain.recommendation.ticketed import (
    drop_orphans,
    may_follow,
    orphaned,
    parse,
    ticketed_venues,
    within_gate,
)
from tests.factories import all_week, context, place, profile, template

GATE = GeoPoint(37.5113, 127.09788)
PARK = parse(
    {
        "inner_roles": ["MEAL", "CAFE", "DESSERT", "BAR"],
        "leg_cap_min": 5,
        "venues": [
            {
                "key": "park",
                "name": "테스트월드 어드벤처",
                "place_ids": [1],
                "gate": [GATE.lat, GATE.lng],
                "radius_m": 400,
                "admission": {"adult": 67000, "child": 50000, "as_of": "2026-04", "basis": "공식"},
                "inner": {
                    "address_keys": ["올림픽로 240"],
                    "require_name_words": ["어드벤처"],
                    "place_ids": [7],
                },
                "exceptions": {"name_words": ["백화점"]},
            }
        ],
    }
)


def test_the_venue_is_priced_at_its_admission() -> None:
    v = PARK.venues[0]
    park = PARK.mark(place("ACTIVITY", "activity", 12000, id=1, lat=GATE.lat, lng=GATE.lng))
    assert park.ticket_venue == "park" and park.price == 67000 and not park.price_is_estimated
    assert v.admission_line() == "입장권 1인 67,000원 (공식 요금, 2026-04 기준)"
    assert v.inside_line() == "테스트월드 어드벤처 안 · 입장권이 있어야 들어가요"


def test_inside_needs_the_address_and_the_sign_on_a_shared_address() -> None:
    at = {"lat": GATE.lat, "lng": GATE.lng, "address": "서울특별시 송파구 올림픽로 240"}
    inner = PARK.mark(place("CAFE", "cafe", 6000, id=11, name="버거 어드벤처점", **at))
    store = PARK.mark(place("MEAL", "food.korean", 11000, id=12, name="어드벤처 롯데백화점", **at))
    mall = PARK.mark(place("CAFE", "cafe", 6000, id=13, name="아무 카페 잠실점", **at))
    listed = PARK.mark(place("MEAL", "food.western", 10000, id=7, name="버거베어", **at))
    other_no = PARK.mark(
        place("CAFE", "cafe", 6000, id=14, name="어드벤처 카페", lat=GATE.lat, lng=GATE.lng,
              address="서울특별시 송파구 올림픽로 2400")
    )  # fmt: skip
    far = PARK.mark(place("CAFE", "cafe", 6000, id=15, name="어드벤처 카페", address=at["address"]))
    assert inner.inside_venue == "park" and listed.inside_venue == "park"
    assert store.inside_venue is None  # an exception word
    assert mall.inside_venue is None  # the department store's café shares the number
    assert other_no.inside_venue is None  # 2400 is another building
    assert far.inside_venue is None  # the same words across town


def test_an_inner_place_only_follows_its_venue() -> None:
    park = PARK.mark(place("ACTIVITY", "activity", 12000, id=1, lat=GATE.lat, lng=GATE.lng))
    cafe = place("CAFE", "cafe", 6000, inside_venue="park")
    meal = place("MEAL", "food.korean", 10000, inside_venue="park")
    street = place("MEAL", "food.korean", 10000)
    assert not may_follow(cafe, None) and not may_follow(cafe, street)
    assert may_follow(cafe, park) and may_follow(meal, cafe) and may_follow(street, cafe)
    assert within_gate(cafe, park) and not within_gate(street, park)
    assert orphaned([street, cafe]) == [cafe] and orphaned([park, cafe]) == []
    pools = {1: [street, cafe], 2: [meal]}
    assert drop_orphans(pools) == {1: [street], 2: []}
    assert drop_orphans({**pools, 3: [park]})[1] == [street, cafe]
    assert drop_orphans(pools, kept=[park])[2] == [meal]


def test_the_composer_keeps_the_cafe_behind_the_gate_after_the_venue() -> None:
    hours = all_week(9 * 60, 23 * 60)
    park = place("ACTIVITY", "activity", 20000, opening_hours=hours, ticket_venue="park", dlat=0.01)
    inner = place("CAFE", "cafe", 5000, opening_hours=hours, inside_venue="park", dlat=0.012)
    ctx, prof = context(budget_total=100000, start_at=context().start_at.replace(hour=11)), profile()
    composer = CourseComposer(PlaceScorer(prof, ctx), ctx)
    alone = B.allocate(template(Slot(1, "CAFE", 1.0)), ctx.budget_per_person)
    assert composer.extend(composer.empty(), inner, alone[0]) is None  # no ticket, no café

    sbs = B.allocate(template(Slot(1, "ACTIVITY", 0.7), Slot(2, "CAFE", 0.3)), ctx.budget_per_person)
    first = composer.extend(composer.empty(), park, sbs[0])
    assert first is not None
    second = composer.extend(first, inner, sbs[1])
    assert second is not None
    assert second.stops[-1].leg.minutes <= 5  # the walk inside the gate
    assert second.stops[-1].score.breakdown["inside_gate"] == INSIDE_GATE_PULL


def test_a_pinned_venue_comes_after_the_first_stop_and_may_take_most_of_the_money() -> None:
    from app.domain.recommendation.style import with_kept

    day = template(Slot(1, "MEAL", 0.5), Slot(2, "CAFE", 0.2), Slot(3, "MEAL", 0.3))
    park = place("ACTIVITY", "activity", 67000, ticket_venue="park")
    [out] = with_kept([day], [park], 100000 / 3)
    assert [s.course_role for s in out.slots] == ["MEAL", "ACTIVITY", "CAFE", "MEAL"]
    assert [s.position for s in out.slots] == [1, 2, 3, 4]
    assert out.slots[1].budget_share == 0.9  # 67,000 of 33,333 per person: capped at 90 %
    [plain] = with_kept([day], [place("ACTIVITY", "activity", 10000)], 100000 / 3)
    assert plain.slots[-1].course_role == "ACTIVITY"  # any other pinned place still goes last


def test_the_shipped_data_file_reads() -> None:
    venues = ticketed_venues()
    keys = [v.key for v in venues.venues]
    assert len(keys) == len(set(keys)) and "lotteworld-adventure" in keys and "everland" in keys
    for v in venues.venues:
        assert v.admission.adult > 0 and v.admission.basis in {"공식", "추정"} and v.admission.source
        assert len(v.admission.as_of) == 7  # YYYY-MM
    # 롯데월드몰 (올림픽로 300) is not behind the gate
    mall = venues.inside_of(
        52668,
        "경주황남빵롯데월드몰",
        "DESSERT",
        "서울특별시 송파구 올림픽로 300",
        GeoPoint(37.51375, 127.10445),
    )
    assert mall is None
    burger = venues.inside_of(
        85451,
        "버거베어롯데월드어드벤쳐점",
        "MEAL",
        "서울특별시 송파구 올림픽로 240",
        GeoPoint(37.51131, 127.09814),
    )
    assert burger is not None and burger.key == "lotteworld-adventure"
    dept = venues.inside_of(
        69674, "강강술래롯데 잠실점", "MEAL", "서울특별시 송파구 올림픽로 240", GeoPoint(37.51131, 127.09814)
    )
    assert dept is None
