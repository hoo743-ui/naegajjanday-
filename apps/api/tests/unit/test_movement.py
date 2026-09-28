"""이동 모드 M1 · M2 · M3 (docs/65 §2 · §6, app/domain/recommendation/movement.py)."""

from __future__ import annotations

import json
import math
from collections.abc import Sequence
from datetime import date
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.domain.models import GeoPoint, PlaceCandidate, Slot, StopResult
from app.domain.recommendation import movement as M
from app.domain.recommendation.budget import SlotBudget
from app.domain.recommendation.composer import CourseComposer
from app.domain.recommendation.engine import RecommendationEngine
from app.domain.recommendation.scorer import PlaceScorer
from app.domain.routing.travel_time import HaversineEstimator, Leg, haversine_m
from app.evaluation.yardstick import locked_invariants
from app.schemas import course as dto
from tests.factories import ORIGIN, all_week, context, place, profile, template

LOCK = locked_invariants()
HOURS = all_week(9 * 60, 24 * 60)
M_PER_DEG_LAT = 111_195.0


def at(metres: float, bearing_deg: float) -> tuple[float, float]:
    """(dlat, dlng) of a point `metres` from ORIGIN towards `bearing_deg` (0 = north, 90 = east)."""
    b = math.radians(bearing_deg)
    dlat = metres * math.cos(b) / M_PER_DEG_LAT
    dlng = metres * math.sin(b) / (M_PER_DEG_LAT * math.cos(math.radians(ORIGIN.lat)))
    return dlat, dlng


def placed(role: str, category: str, metres: float, bearing: float, **kw: object) -> PlaceCandidate:
    dlat, dlng = at(metres, bearing)
    return place(role, category, 10000, dlat=dlat, dlng=dlng, opening_hours=HOURS, **kw)


class _Source:
    def __init__(self, places: Sequence[PlaceCandidate]) -> None:
        self.places = list(places)

    async def fetch(
        self, role: str, origin: GeoPoint, radius_m: float, on_date: date, name_words: Sequence[str] = ()
    ) -> list[PlaceCandidate]:
        return [p for p in self.places if p.course_role == role and haversine_m(origin, p.point) <= radius_m]


class _StandoutSource(_Source):
    async def fetch_standouts(
        self,
        role: str,
        origin: GeoPoint,
        radius_m: float,
        *,
        min_popularity: float,
        name_words: Sequence[str] = (),
        place_ids: Sequence[int] = (),
    ) -> list[PlaceCandidate]:
        return await self.fetch(role, origin, radius_m, date(2026, 9, 20))


# ── the numbers come from the yardstick lock only ───────────────────────────────────────────


def test_the_promise_numbers_are_the_locked_ones() -> None:
    inside, around = M.make_promise(M.INSIDE, ORIGIN), M.make_promise(M.AROUND, ORIGIN)
    assert inside.radius_m == LOCK["M1_radius_m"] == 800
    assert around.radius_m == LOCK["M2_radius_m"] == 2000
    assert inside.walk_leg_max_min == around.walk_leg_max_min == LOCK["M2_walk_leg_max_min"] == 20
    assert inside.walk_only and inside.max_transit_legs == 0
    assert not around.walk_only and around.max_transit_legs == M.movement_rules()["max_transit_legs"] == 1
    onward = M.make_promise(M.ONWARD, ORIGIN)  # each cluster of M3 keeps M2
    assert (onward.radius_m, onward.max_transit_legs) == (around.radius_m, around.max_transit_legs)


def test_a_lock_without_the_numbers_fails_loudly(tmp_path: Path) -> None:
    lock = tmp_path / "lock.json"
    lock.write_text(json.dumps({"invariants": {"M1_radius_m": 800}}), encoding="utf-8")
    with pytest.raises(RuntimeError, match="M2_radius_m"):
        M.promise_numbers.__wrapped__(lock)
    with pytest.raises(RuntimeError):
        M.promise_numbers.__wrapped__(tmp_path / "missing.json")


def test_movement_module_has_no_numbers_of_its_own() -> None:
    source = Path(M.__file__).read_text(encoding="utf-8")
    for number in ("800", "2000", "2_000"):
        assert number not in source


# ── the choke point: every candidate the engine reads ───────────────────────────────────────


async def test_the_wrapper_filters_fetch_and_standouts() -> None:
    near, far = placed("MEAL", "food.korean", 500, 0), placed("MEAL", "food.noodle", 1000, 0)
    promise = M.make_promise(M.INSIDE, ORIGIN)
    wrapped = M.within_promise(_StandoutSource([near, far]), promise)
    got = await wrapped.fetch("MEAL", ORIGIN, 5000, date(2026, 9, 20))
    assert [p.id for p in got] == [near.id]
    standouts = await wrapped.fetch_standouts("MEAL", ORIGIN, 5000, min_popularity=0.0)
    assert [p.id for p in standouts] == [near.id]
    assert await wrapped.opened_on([near.id]) == {}
    # a source without standouts stays without them (the engine falls back to fetch)
    plain = M.within_promise(_Source([near]), promise)
    assert getattr(plain, "fetch_standouts", None) is None
    assert M.within_promise(plain, None) is plain


def test_holds_keeps_a_cluster_on_its_own_side() -> None:
    other = GeoPoint(ORIGIN.lat, ORIGIN.lng - 1800 / (M_PER_DEG_LAT * math.cos(math.radians(ORIGIN.lat))))
    promise = M.make_promise(M.ONWARD, ORIGIN, away_from=other)
    east, west = placed("MEAL", "food.korean", 800, 90), placed("MEAL", "food.korean", 1000, 270)
    assert M.holds(promise, east.point)
    assert not M.holds(promise, west.point)  # 1 km west = 800 m from the other anchor


# ── legs ────────────────────────────────────────────────────────────────────────────────────


def test_settle_leg() -> None:
    around, inside = M.make_promise(M.AROUND, ORIGIN), M.make_promise(M.INSIDE, ORIGIN)
    a = ORIGIN
    b = GeoPoint(ORIGIN.lat + 1800 / M_PER_DEG_LAT, ORIGIN.lng)
    walk = HaversineEstimator().estimate(a, b, "walk")
    assert walk.minutes > 20
    short = Leg(12.0, 900.0)
    assert M.settle_leg(around, "walk", short, a, b, 0) == (short, None)
    ridden = M.settle_leg(around, "walk", walk, a, b, 0)
    assert ridden is not None and ridden[1] == M.TRANSIT and ridden[0].minutes < walk.minutes
    assert M.settle_leg(around, "walk", walk, a, b, 1) is None  # a second one: that combination is out
    assert M.settle_leg(inside, "walk", walk, a, b, 0) is None  # M1: on foot only
    # by car the walk rule does not apply (docs/65 §6), and without a promise nothing changes
    assert M.settle_leg(around, "car", walk, a, b, 5) == (walk, None)
    assert M.settle_leg(None, "walk", walk, a, b, 5) == (walk, None)


def test_the_composer_rides_one_long_walk_and_refuses_a_second() -> None:
    ctx = context(budget_total=90000)
    ctx.promise = M.make_promise(M.AROUND, ORIGIN)
    composer = CourseComposer(PlaceScorer(profile(), ctx), ctx)
    north = placed("MEAL", "food.korean", 1900, 0)
    south = placed("CAFE", "cafe.coffee", 1900, 180)
    north2 = placed("ATTRACTION", "attraction.park", 1850, 10)
    roles = ("MEAL", "CAFE", "ATTRACTION")
    sbs = [SlotBudget(Slot(i + 1, r, 0.25), 0.25, 20000) for i, r in enumerate(roles)]
    one = composer.extend(composer.empty(), north, sbs[0])
    assert one is not None and one.transit_legs == 0  # the first leg is not a leg of the promise
    two = composer.extend(one, south, sbs[1])
    assert two is not None and two.transit_legs == 1 and two.stops[-1].mode == M.TRANSIT
    three = composer.extend(two, north2, sbs[2])
    assert three is None  # 3.7 km back north: a second ride
    # M1 never rides
    ctx.promise = M.make_promise(M.INSIDE, ORIGIN)
    m1 = CourseComposer(PlaceScorer(profile(), ctx), ctx)
    first = m1.extend(m1.empty(), north, sbs[0])
    assert first is not None and m1.extend(first, south, sbs[1]) is None
    assert m1.leg_limit() <= LOCK["M2_walk_leg_max_min"]


def test_violations_reads_a_finished_course() -> None:
    promise = M.make_promise(M.AROUND, ORIGIN)

    def stop(pos: int, p: PlaceCandidate, minutes: int, mode: str | None = None) -> StopResult:
        t = context().start_at
        return StopResult(pos, p.course_role, p, t, t, 0, minutes, 0, 0.0, {}, None, 0.0, leg_mode=mode)

    near, mid, far = placed("MEAL", "a", 300, 0), placed("CAFE", "b", 1500, 90), placed("BAR", "c", 2300, 180)
    assert M.violations([stop(1, near, 40), stop(2, mid, 18)], promise, "walk") == []
    found = M.violations(
        [stop(1, near, 5), stop(2, mid, 25), stop(3, far, 30, M.TRANSIT), stop(4, near, 30, M.TRANSIT)],
        promise,
        "walk",
    )
    assert any(v.startswith("OUTSIDE:3") for v in found)
    assert "LONG_WALK:2:25min" in found and "TRANSIT_LEGS:2" in found
    inside = M.make_promise(M.INSIDE, ORIGIN)
    assert "TRANSIT_LEG:2" in M.violations([stop(1, near, 5), stop(2, near, 9, M.TRANSIT)], inside, "walk")


# ── the real engine over a made-up area: 0.5 · 1.0 · 1.9 · 2.4 km ────────────────────────────


def _rings() -> list[PlaceCandidate]:
    """Each role at 0.5, 1.0, 1.9 and 2.4 km — the far ones the best rated, so only the promise keeps them
    out. The 1.9 km ones stand on opposite sides (north · south): between them only a ride will do."""
    best = {"rating_avg": 4.9, "rating_count": 3000, "sentiment_score": 0.9, "sentiment_count": 900}
    out: list[PlaceCandidate] = []
    kinds = {
        "MEAL": ("food.korean", "food.noodle", "food.western", "food.japanese", "food.bbq"),
        "CAFE": ("cafe.coffee", "cafe.tea", "cafe.view", "cafe.book", "cafe.roastery"),
        "ATTRACTION": (
            "attraction.park",
            "attraction.street",
            "attraction.market",
            "attraction.a",
            "attraction.b",
        ),
    }
    for role, cats in kinds.items():
        offset = {"MEAL": 0, "CAFE": 25, "ATTRACTION": 50}[role]
        out += [
            placed(role, cats[0], 500, offset),
            placed(role, cats[1], 1000, 120 + offset),
            placed(role, cats[2], 1900, 0 + offset / 5),
            placed(role, cats[3], 1900, 180 + offset / 5),
            placed(role, cats[4], 2400, 90 + offset / 5, **best),
        ]
    return out


@pytest.mark.parametrize("mode", [M.INSIDE, M.AROUND])
@pytest.mark.parametrize("algorithm", ["v1", "v2"])
async def test_the_engine_keeps_the_promise(mode: str, algorithm: str) -> None:
    day = template(
        Slot(1, "MEAL", 0.4), Slot(2, "ATTRACTION", 0.2), Slot(3, "CAFE", 0.4), time_band="afternoon"
    )
    ctx = context(
        budget_total=80000, start_at=context().start_at.replace(hour=13), alternatives=2, radius_m=3000
    )
    ctx.algorithm = algorithm
    ctx.promise = M.make_promise(mode, ORIGIN)
    source = M.within_promise(_StandoutSource(_rings()), ctx.promise)
    out = await RecommendationEngine(source).generate(ctx, [day], profile())
    assert out.courses
    limit = LOCK["M1_radius_m"] if mode == M.INSIDE else LOCK["M2_radius_m"]
    for course in out.courses:
        assert course.stops
        for s in course.stops:
            assert haversine_m(ORIGIN, s.place.point) <= limit, (mode, s.place.name)
        legs = course.stops[1:]
        rides = [s for s in legs if s.leg_mode == M.TRANSIT]
        assert len(rides) <= (0 if mode == M.INSIDE else 1)
        assert all(s.travel_min_from_prev <= LOCK["M2_walk_leg_max_min"] for s in legs if s.leg_mode is None)
        assert M.violations(course.stops, ctx.promise, "walk") == []


async def test_without_a_promise_the_far_places_are_taken() -> None:
    """The control for the test above: the made-up area does pull the course past 2 km without a promise."""
    day = template(
        Slot(1, "MEAL", 0.4), Slot(2, "ATTRACTION", 0.2), Slot(3, "CAFE", 0.4), time_band="afternoon"
    )
    ctx = context(
        budget_total=80000, start_at=context().start_at.replace(hour=13), alternatives=2, radius_m=3000
    )
    ctx.algorithm = "v2"
    out = await RecommendationEngine(_StandoutSource(_rings())).generate(ctx, [day], profile())
    far = [
        s for c in out.courses for s in c.stops if haversine_m(ORIGIN, s.place.point) > LOCK["M2_radius_m"]
    ]
    assert far


# ── M3's B ──────────────────────────────────────────────────────────────────────────────────


def test_rank_onward_is_deterministic() -> None:
    def pt(metres: float, bearing: float) -> GeoPoint:
        dlat, dlng = at(metres, bearing)
        return GeoPoint(ORIGIN.lat + dlat, ORIGIN.lng + dlng)

    candidates = [
        ("b-slug", "B", pt(2000, 0), 3.0),
        ("a-slug", "A2", pt(2000, 180), 3.0),  # same strength, same distance: the slug decides
        ("near", "N", pt(1000, 90), 2.0),
        ("strong-far", "F", pt(20000, 90), 9.0),  # beyond the 15-minute ride
        ("here", "H", ORIGIN, 9.0),  # A itself
    ]
    ranked = M.rank_onward(ORIGIN, candidates, exclude="here")
    assert [c[0] for c in ranked] == ["a-slug", "b-slug", "near"]
    assert M.rank_onward(ORIGIN, list(reversed(candidates)), exclude="here") == ranked
    assert M.ride_minutes(ORIGIN, pt(20000, 90)) > M.movement_rules()["onward_ride_max_min"]
    assert M.rank_onward(ORIGIN, candidates, exclude="here", max_ride_min=1) == []


# ── the request ─────────────────────────────────────────────────────────────────────────────

BODY = {"region": "seoul-hongdae", "purpose": "date", "party_size": 2, "budget_total": 40000}


def test_the_request_fields() -> None:
    assert dto.CourseGenerateRequest.model_validate(BODY).movement is None  # the service reads it as around
    ok = dto.CourseGenerateRequest.model_validate(
        BODY | {"movement": "onward", "onward_to": {"region": "seoul-yeonnam", "label": "연남"}}
    )
    assert ok.onward_to is not None and ok.onward_to.region == "seoul-yeonnam"
    for bad in (
        {"movement": "far"},
        {"movement": "around", "onward_to": {"region": "seoul-yeonnam"}},  # B only for onward
        {"onward_to": {"region": "seoul-yeonnam"}},
        {"movement": "onward", "onward_to": {}},  # region or origin
        {"movement": "onward", "onward_to": {"region": "x", "origin": {"lat": 37.5, "lng": 127.0}}},
        {"movement": "onward", "onward_to": {"region": "x", "extra": 1}},
    ):
        with pytest.raises(ValidationError):
            dto.CourseGenerateRequest.model_validate(BODY | bad)
