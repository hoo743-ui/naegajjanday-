"""입장권이 있어야 들어가는 곳 (recommendation.ticketed, data/recommendation/ticketed_venues.json)."""

from __future__ import annotations

from datetime import date

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


# ── docs/59 #13: a short day after a long venue · child prices · dated prices ──────────────────

DATED = parse(
    {
        "venues": [
            {
                "key": "land",
                "name": "테스트랜드",
                "place_ids": [2],
                "gate": [GATE.lat, GATE.lng],
                "stay_min": 240,
                "admission": {
                    "adult": 68000,
                    "child": 58000,
                    "as_of": "2026-09",
                    "basis": "공식",
                    "source": "https://example.test/price",
                    "changes": [
                        {"from": "2026-11-01", "adult": 65000, "child": 55000},
                        {
                            "from": "2026-10-06",
                            "adult": 71000,
                            "child": 61000,
                            "source": "https://example.test/up",
                        },
                    ],
                },
            }
        ],
    }
)


def test_an_announced_price_switches_on_its_day() -> None:
    land = DATED.venues[0]
    assert land.admission_on(date(2026, 10, 5)).adult == 68000
    up = land.admission_on(date(2026, 10, 6))
    assert (up.adult, up.child, up.as_of, up.basis) == (71000, 61000, "2026-10", "공식")
    assert up.source == "https://example.test/up"
    later = land.admission_on(date(2026, 11, 2))  # what a change does not restate carries over
    assert (later.adult, later.child, later.source) == (65000, 55000, "https://example.test/price")
    assert land.admission_line(date(2026, 10, 6)) == "입장권 1인 71,000원 (공식 요금, 2026-10 기준)"
    kids_line = land.admission_line(date(2026, 10, 6), children=1)
    assert kids_line == "입장권 어른 71,000 · 어린이 61,000원(공식 2026-10)"


def test_children_pay_the_child_price() -> None:
    assert DATED.party_of("family", "kids", 3) == (2, 1)
    assert DATED.party_of("family", "kids", 2) == (1, 1)
    assert DATED.party_of("family", "kids", 1) == (1, 0)
    assert DATED.party_of("family", "parents", 3) == (3, 0)  # 부모님과: all adults
    assert DATED.party_of("date", None, 2) == (2, 0)

    at = context().start_at.replace(month=10, day=10)  # after the rise
    ctx = context(budget_total=300000, party_size=3, purpose_code="family", scene="kids", start_at=at)
    land = DATED.mark(place("ACTIVITY", "activity", 12000, id=2, lat=GATE.lat, lng=GATE.lng))
    DATED.price([land], ctx)
    total = 2 * 71000 + 61000
    assert land.price == -(-total // 3) and DATED.party_price(land, 3) == total
    assert DATED.line(land) == "입장권 어른 71,000 · 어린이 61,000원(공식 2026-10)"
    DATED.price([land], ctx)  # the same answer however often it runs
    assert DATED.party_price(land, 3) == total

    couple = DATED.mark(place("ACTIVITY", "activity", 12000, id=2, lat=GATE.lat, lng=GATE.lng))
    DATED.price([couple], context(budget_total=300000, party_size=2, start_at=at))
    assert couple.price == 71000 and DATED.party_price(couple, 2) == 142000


def test_after_a_long_venue_one_stop_near_the_gate_then_the_day_is_over() -> None:
    hours = all_week(9 * 60, 23 * 60)
    park = place(
        "ACTIVITY", "activity", 20000, opening_hours=hours, ticket_venue="park", default_stay_min=240
    )
    near = place("CAFE", "cafe", 5000, opening_hours=hours, dlat=0.004)
    far = place("MEAL", "food.western", 15000, opening_hours=hours, dlat=0.03)
    sight = place("ATTRACTION", "attraction.park", 0, opening_hours=hours, dlat=0.003)
    ctx = context(budget_total=200000, start_at=context().start_at.replace(hour=11))
    composer = CourseComposer(PlaceScorer(profile(), ctx), ctx)
    day = template(
        Slot(1, "ACTIVITY", 0.5), Slot(2, "CAFE", 0.1), Slot(3, "ATTRACTION", 0.1), Slot(4, "MEAL", 0.3)
    )
    sbs = B.allocate(day, ctx.budget_per_person)
    first = composer.extend(composer.empty(), park, sbs[0])
    assert first is not None
    assert composer.extend(first, far, sbs[3]) is None  # a long leg after four hours in the park
    assert composer.extend(first, sight, sbs[2]) is None  # a second outing, not a meal or a café
    wrapped = composer.extend(first, near, sbs[1])
    assert wrapped is not None
    assert composer.extend(wrapped, sight, sbs[2]) is None  # nothing after the one stop

    finals, unfilled = composer.search(sbs, {1: [park], 2: [near], 3: [sight], 4: [far]})
    assert unfilled == []  # the slots after it are not holes: the day ended on purpose
    assert finals and all(p.stops[0].place is park for p in finals)
    assert all(s.place is not sight and s.place is not far for p in finals for s in p.stops)


def test_with_the_kids_the_stop_after_the_park_ends_by_the_scene_hour() -> None:
    hours = all_week(9 * 60, 23 * 60)
    park = place(
        "ACTIVITY", "activity", 20000, opening_hours=hours, ticket_venue="park", default_stay_min=240
    )
    near = place("CAFE", "cafe", 5000, opening_hours=hours, dlat=0.004)
    start = context().start_at.replace(hour=16)
    ctx = context(budget_total=200000, start_at=start, soft_end_min=20 * 60 + 30)
    composer = CourseComposer(PlaceScorer(profile(), ctx), ctx)
    sbs = B.allocate(template(Slot(1, "ACTIVITY", 0.8), Slot(2, "CAFE", 0.2)), ctx.budget_per_person)
    first = composer.extend(composer.empty(), park, sbs[0])  # 16:00 → 20:00
    assert first is not None
    assert composer.extend(first, near, sbs[1]) is None  # a café after 20:00 runs past 20:45
