"""일관성 불변식 I1~I12 (docs/65 §3, docs/64 R17 ③) — 조건 하나를 바꿔 짠 두 코스의 관계를 본다.

같은 DB 스냅숏에서, 진짜 코스 서비스(`CourseService.dry_run`)로:
- `fixture`: 씨앗 DB + 작은 샘플(conftest) — CI 매 push.
- `national`: 로컬 전국 DB 를 읽기 전용으로 — `METAMORPHIC_NATIONAL=1` 일 때만 (소량 표본).

I3 · I7 의 문턱(70%)은 잣대 잠금(app/evaluation/yardstick.py › INVARIANT_THRESHOLDS,
data/eval/yardstick.lock.json › invariants)에서 읽는다 — 여기서 바꾸지 않는다.
지금 엔진에서 깨지는 불변식은 고치지 않고 xfail(strict) 로 남긴다(KNOWN) — 발견이지 고칠 거리가 아니다.
I8~I10(이동 모드 M1~M3)은 R1 · R2 · 한 구간 도보를 같은 잠금에서 읽고, 둘레 가게를 더한 `movement` DB 에서
본다(I1~I7 의 fixture 코스는 그대로). I11(아이 수, R18)은 아직 없는 입력이라 건너뛴다(맨 아래).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from datetime import date, timedelta
from typing import Any

import pytest

from app.domain.models import GeoPoint, PlaceCandidate, Slot
from app.domain.recommendation.engine import RecommendationEngine
from app.domain.recommendation.style import category_matches, extra_roles
from app.domain.routing.travel_time import haversine_m
from app.evaluation.yardstick import INVARIANT_THRESHOLDS
from tests.factories import all_week, context, place, profile, template
from tests.metamorphic.harness import (
    Base,
    Plan,
    Planner,
    closed_stops,
    kept_share,
    kind_keep_share,
    orphaned_inner,
)

# ── the sample ─────────────────────────────────────────────────────────────────────────────

WEEKDAY = "2026-10-06"  # a Tuesday
FIXTURE_BASES = [
    Base("seoul-hongdae", "date", WEEKDAY, "13:00"),
    Base("seoul-hongdae", "date", WEEKDAY, "18:00"),
    Base("seoul-hongdae", "friends", WEEKDAY, "13:00"),
    Base("seoul-seongsu", "friends", WEEKDAY, "18:00"),
    Base("busan-seomyeon", "date", WEEKDAY, "18:00"),
    Base("seoul-seongsu", "family", WEEKDAY, "11:00", party_size=3, budget_total=90000),
]
NATIONAL_BASES = [
    Base("seoul-hongdae", "date", WEEKDAY, "18:00"),
    Base("seoul-seongsu", "friends", WEEKDAY, "13:00"),
    # 롯데월드 어드벤처(입장권 구역)가 있는 동네 — I12
    Base("seoul-jamsil", "family", WEEKDAY, "11:00", party_size=3, budget_total=200000),
]
CASES = [pytest.param("fixture", b, id=f"fixture:{b.id}") for b in FIXTURE_BASES] + [
    pytest.param("national", b, id=f"national:{b.id}", marks=pytest.mark.national) for b in NATIONAL_BASES
]

# docs/65 §3 의 흔드는 크기 (잣대가 아니라 불변식의 정의 그 자체)
BUDGET_RAISE = 1.2  # I2
START_SHIFT_MIN = 10  # I3
OTHER_DAYS = ("2026-10-10", "2026-11-17")  # I4: 주말(토) · 다른 달(화). 평일은 기본 요청 그대로
OPTIONS = ("SHOP", "BAR", "MOVIE")  # I5
PARTY_FROM, PARTY_TO = 2, 3  # I7

# 지금 엔진에서 깨지는 것: (불변식, world, base.key) → 이유 + 구체적인 예. 엔진을 고치면 xfail 이 XPASS 로
# 실패한다(strict) — 그때 이 줄을 지운다. (I5 고정 + 옵션 4건은 engine._around_kept 로 풀려 지웠다.)
KNOWN: dict[tuple[str, str, str], str] = {}


@pytest.fixture
def planner(request: pytest.FixtureRequest, world: str) -> Planner:
    got: Planner = request.getfixturevalue(f"{world}_planner")
    return got


def _known(request: pytest.FixtureRequest, invariant: str, world: str, base: Base) -> None:
    reason = KNOWN.get((invariant, world, base.key))
    if reason:
        request.applymarker(pytest.mark.xfail(strict=True, reason=reason))


_plans: dict[tuple[str, str], Plan] = {}


async def _plan(planner: Planner, base: Base, **changes: Any) -> Plan:
    """dry_run is deterministic on one snapshot (I1 checks it without this cache)."""
    req = base.request(**changes)
    key = (planner.world, req.model_dump_json())
    if key not in _plans:
        _plans[key] = await planner.plan(req)
    return _plans[key]


async def _base_plan(planner: Planner, base: Base) -> Plan:
    plan = await _plan(planner, base)
    if not plan.ok:
        pytest.skip(f"기본 요청부터 코스가 없다({plan.error}) — 불변식의 전제가 없다: {base.key}")
    return plan


def test_the_thresholds_come_from_the_yardstick_lock() -> None:
    from app.evaluation.yardstick import locked_invariants

    assert locked_invariants() == INVARIANT_THRESHOLDS
    assert set(INVARIANT_THRESHOLDS) == {
        "I3_start_shift_keep_share",
        "I7_party_kind_keep_share",
        "M1_radius_m",
        "M2_radius_m",
        "M2_walk_leg_max_min",
    }


@pytest.mark.parametrize(("world", "base"), CASES)
async def test_the_sample_plans(planner: Planner, base: Base) -> None:
    """표본의 기본 요청은 코스가 있어야 한다 — 없으면 아래 불변식이 전부 건너뛰어진다."""
    plan = await _plan(planner, base)
    assert plan.ok, f"{base.key}: {plan.describe()}"


# ── I1 결정성 ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(("world", "base"), CASES)
async def test_i1_same_request_same_course(
    request: pytest.FixtureRequest, planner: Planner, world: str, base: Base
) -> None:
    """I1: 같은 요청 두 번 → 같은 장소 · 같은 순서 · 같은 금액. 대안 코스(2개)까지, 스톱마다 금액까지 본다."""
    _known(request, "I1", world, base)
    req = base.request(alternatives=2)
    first, second = await planner.plan(req), await planner.plan(req)
    assert first.error == second.error

    def shape(p: Plan) -> list[tuple[list[tuple[str, int]], int]]:
        return [([(s.place.public_id, s.est_price) for s in c.stops], c.total_price) for c in p.courses]

    assert shape(first) == shape(second), f"{base.key}\n1: {first.describe()}\n2: {second.describe()}"


# ── I2 예산 ×1.2 ───────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(("world", "base"), CASES)
async def test_i2_more_budget_stays_possible_and_within_it(
    request: pytest.FixtureRequest, planner: Planner, world: str, base: Base
) -> None:
    """I2: 예산만 올림(×1.2) → 코스가 불가능해지지 않는다 · (올린) 예산 초과 없음.
    전제: 기본 요청에 코스가 있다. 금액은 일행 전체(total_price) 대 budget_total."""
    _known(request, "I2", world, base)
    await _base_plan(planner, base)
    raised = round(base.budget_total * BUDGET_RAISE)
    more = await _plan(planner, base, budget_total=raised)
    assert more.ok, f"{base.key} → 예산 {raised:,}원: {more.describe()}"
    assert more.course.total_price <= raised, f"{base.key} → 예산 {raised:,}원: {more.describe()}"


# ── I3 출발 시각 ±10분 ─────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(("world", "base"), CASES)
@pytest.mark.parametrize("shift", [-START_SHIFT_MIN, START_SHIFT_MIN])
async def test_i3_ten_minutes_keep_most_places(
    request: pytest.FixtureRequest, planner: Planner, world: str, base: Base, shift: int
) -> None:
    """I3: 출발 시각 ±10분 → 장소의 ≥70% 유지 (문턱은 잣대 잠금).
    읽기: 기본 코스(대표 코스)의 장소 중 흔든 코스에도 있는 비율(순서 무관) ≥ 문턱, +10 · −10 각각."""
    _known(request, f"I3{shift:+d}", world, base)
    before = await _base_plan(planner, base)
    moved = before.req.start_at + timedelta(minutes=shift)  # type: ignore[operator]
    after = await _plan(planner, base, start_at=moved)
    share = kept_share(before.ids, after.ids) if after.ok else 0.0
    limit = INVARIANT_THRESHOLDS["I3_start_shift_keep_share"]
    assert share >= limit, (
        f"{base.key} 출발 {shift:+d}분: 장소 {share:.0%} 유지 (< {limit:.0%})\n"
        f"전: {before.describe()}\n후: {after.describe()}"
    )


# ── I4 날짜만 바꿈 ─────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(("world", "base"), CASES)
@pytest.mark.parametrize("day", [WEEKDAY, *OTHER_DAYS])
async def test_i4_any_day_a_course_and_nothing_closed(
    request: pytest.FixtureRequest, planner: Planner, world: str, base: Base, day: str
) -> None:
    """I4: 날짜만 바꿈(평일 · 주말 · 다른 달) → 코스 있음 · 닫힌 곳 0.
    '닫힌 곳' = 점수표의 CLOSED_AT_ARRIVAL(evaluation.harness.judge) — 도착 시각에 영업시간 밖."""
    _known(request, f"I4@{day}", world, base)
    await _base_plan(planner, base)
    plan = await _plan(planner, replace(base, day=day))
    assert plan.ok, f"{base.key} → {day}: {plan.describe()}"
    closed = closed_stops(plan)
    assert not closed, f"{base.key} → {day}: 닫힌 곳 {closed}\n{plan.describe()}"


# ── I5 옵션 켬 ─────────────────────────────────────────────────────────────────────────────


def _count_kind(plan: Plan, option: str) -> int:
    """How many stops are the option's kind: its category / family when it names one (MOVIE =
    activity.cinema, SHOP = shop.*), else its role (BAR) — style.carries, counted."""
    extra = extra_roles()[option]
    wanted = extra.get("category") or extra.get("family")
    if wanted:
        return sum(1 for s in plan.stops if category_matches(s.place.category_code, str(wanted)))
    return sum(1 for s in plan.stops if s.role == extra["role"])


# the fixture has shops and a multiplex only in 홍대 (tests/metamorphic/data); every seed area has bars
FIXTURE_HAS = {"SHOP": {"seoul-hongdae"}, "MOVIE": {"seoul-hongdae"}}


def _option_applies(world: str, base: Base, option: str) -> bool:
    """Only where the option's own hours (extra_roles.json) hold the start, not for a company that vetoes it
    by design (family: no bar), and — in the fixture — where there is such a place at all. BAR from 17:00,
    SHOP 11:00–16:00 start (browse hours), MOVIE any."""
    if world == "fixture" and option in FIXTURE_HAS and base.region not in FIXTURE_HAS[option]:
        return False
    hour = int(base.start[:2])
    if option == "BAR":
        return hour >= 17 and base.purpose != "family"
    if option == "SHOP":
        return 11 <= hour <= 16
    return True


I5_CASES = [
    pytest.param(world, base, option, id=f"{world}:{option}:{base.id}", marks=marks)
    for world, bases, marks in (
        ("fixture", FIXTURE_BASES, ()),
        ("national", NATIONAL_BASES, (pytest.mark.national,)),
    )
    for base in bases
    for option in OPTIONS
    if _option_applies(world, base, option)
]


@pytest.mark.parametrize(("world", "base", "option"), I5_CASES)
async def test_i5_an_option_adds_its_kind_and_keeps_the_pinned(
    request: pytest.FixtureRequest, planner: Planner, world: str, base: Base, option: str
) -> None:
    """I5: 옵션 켬(SHOP · BAR · MOVIE) → 그 종류 1곳 추가, 확정(고정)한 곳은 그대로.
    읽기: 기본 코스의 첫 장소를 고정하고(웹의 '옵션 칩'과 같게: keep_place_ids, 빼는 곳 없음) 옵션을 켠다.
    ① 고정한 곳이 새 코스에 있다 ② 그 종류가 1곳 이상 ③ 그 종류는 켜기 전보다 많아야 1곳 더 —
    켜기 전에 없었으면 정확히 1곳. '종류' = extra_roles.json 의 category / family, 없으면 role."""
    _known(request, f"I5:{option}", world, base)
    before = await _base_plan(planner, base)
    pinned = before.ids[0]
    after = await _plan(planner, base, extras=[option], keep_place_ids=[pinned])
    assert after.ok, f"{base.key} +{option}: {after.describe()}"
    n_before, n_after = _count_kind(before, option), _count_kind(after, option)
    detail = f"{base.key} +{option} (고정 {pinned})\n전: {before.describe()}\n후: {after.describe()}"
    assert pinned in after.ids, "고정한 곳이 빠졌다 — " + detail
    assert 1 <= n_after <= n_before + 1, f"{option} {n_before}곳 → {n_after}곳 — " + detail


# ── I6 확정 + 다시 짜기 ────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(("world", "base"), CASES)
@pytest.mark.parametrize("which", ["first", "last"])
async def test_i6_reroll_keeps_the_pinned(
    request: pytest.FixtureRequest, planner: Planner, world: str, base: Base, which: str
) -> None:
    """I6: 확정한 곳 + 다시 짜기 → 확정한 곳 유지.
    읽기: 웹의 '다시 짜기'(CourseView.onReroll)와 같게 — 고정한 곳은 keep_place_ids, 지금 코스의 장소는
    전부 exclude_place_ids. 첫 장소 · 마지막 장소를 따로 고정해 본다. 코스가 아예 안 나오면 유지 실패로 센다."""
    _known(request, f"I6:{which}", world, base)
    before = await _base_plan(planner, base)
    pinned = before.ids[0] if which == "first" else before.ids[-1]
    after = await _plan(
        planner,
        base,
        keep_place_ids=[pinned],
        preferences={"exclude_place_ids": before.ids},
    )
    assert after.ok and pinned in after.ids, (
        f"{base.key} 다시 짜기 (고정 {pinned})\n전: {before.describe()}\n후: {after.describe()}"
    )


# ── I7 인원만 바꿈 ─────────────────────────────────────────────────────────────────────────


I7_CASES = [c for c in CASES if c.values[1].party_size == PARTY_FROM]  # type: ignore[union-attr]


@pytest.mark.parametrize(("world", "base"), I7_CASES)
async def test_i7_one_more_person_keeps_the_kinds(
    request: pytest.FixtureRequest, planner: Planner, world: str, base: Base
) -> None:
    """I7: 인원만 바꿈(2→3, 1인 예산 같게) → 장소 종류 구성 유지 (문턱 70%, 잣대 잠금).
    읽기: '종류' = 스톱의 자리(course role: MEAL · CAFE · BAR …), '구성' = 그 중복 집합.
    유지율 = 두 코스 자리 중복집합의 교집합 / 더 긴 코스의 스톱 수 ≥ 문턱. 순서 · 장소는 보지 않는다."""
    _known(request, "I7", world, base)
    before = await _base_plan(planner, base)
    per_person = base.budget_total / PARTY_FROM
    after = await _plan(planner, base, party_size=PARTY_TO, budget_total=round(per_person * PARTY_TO))
    share = kind_keep_share(before.roles, after.roles) if after.ok else 0.0
    limit = INVARIANT_THRESHOLDS["I7_party_kind_keep_share"]
    assert share >= limit, (
        f"{base.key} → {PARTY_TO}명: 종류 {share:.0%} 유지 (< {limit:.0%}) "
        f"{before.roles} → {after.roles}\n전: {before.describe()}\n후: {after.describe()}"
    )


# ── I12 입장권 구역 ────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(("world", "base"), CASES)
async def test_i12_inside_a_gate_only_with_its_venue(
    request: pytest.FixtureRequest, planner: Planner, world: str, base: Base
) -> None:
    """I12: 입장권 구역 안 가게 → 그 구역이 코스에 있을 때만 (docs/64 R10).
    읽기: 코스(대표 + 대안 2)의 스톱 중 inside_venue 가 있는 곳마다, 같은 코스에 그 ticket_venue 스톱이 있다.
    씨앗 DB 에는 입장권 구역이 없어 fixture 에서는 늘 참 — 엔진 수준은 아래 합성 테스트가, 실제 구역
    (롯데월드 · 잠실)은 national 표본이 본다."""
    _known(request, "I12", world, base)
    plan = await _plan(planner, base, alternatives=2)
    if not plan.ok:
        pytest.skip(f"코스 없음({plan.error})")
    for course in plan.courses:
        assert not orphaned_inner(course), f"{base.key} [{course.label}]: {orphaned_inner(course)}"


class _Source:
    """A candidate source over a fixed list — the engine and its rules are the real ones."""

    def __init__(self, places: Sequence[PlaceCandidate]) -> None:
        self.places = list(places)

    async def fetch(
        self, role: str, origin: GeoPoint, radius_m: float, on_date: date, name_words: Sequence[str] = ()
    ) -> list[PlaceCandidate]:
        return [p for p in self.places if p.course_role == role and haversine_m(origin, p.point) <= radius_m]


def _gated_world(venue_price: int | None) -> list[PlaceCandidate]:
    """A plain street plus a gated venue: the best-rated café and restaurant of the area are behind its gate.
    `venue_price=None`: the venue is not among the candidates at all (only its shops are)."""
    hours = all_week(9 * 60, 23 * 60)
    best = {"rating_avg": 4.9, "rating_count": 3000, "sentiment_score": 0.9, "sentiment_count": 900}
    places = [
        place("MEAL", "food.korean", 11000, opening_hours=hours, dlat=0.003),
        place("MEAL", "food.noodle", 9000, opening_hours=hours, dlng=0.003),
        place("CAFE", "cafe.coffee", 5000, opening_hours=hours, dlat=-0.003),
        place("CAFE", "cafe.tea", 6000, opening_hours=hours, dlng=-0.003),
        place("ACTIVITY", "activity.arcade", 8000, opening_hours=hours, dlat=0.002, dlng=0.002),
        place("CAFE", "cafe.coffee", 5000, opening_hours=hours, inside_venue="mm-park", **best),
        place("MEAL", "food.western", 12000, opening_hours=hours, inside_venue="mm-park", **best),
    ]
    if venue_price is not None:
        places.append(
            place(
                "ACTIVITY", "activity", venue_price, opening_hours=hours, ticket_venue="mm-park", dlat=0.001
            )
        )
    return places


@pytest.mark.parametrize("venue_price", [None, 9000, 60000], ids=["no-venue", "cheap-venue", "dear-venue"])
@pytest.mark.parametrize("hour", [11, 14])
async def test_i12_the_engine_never_leaves_a_gated_shop_alone(venue_price: int | None, hour: int) -> None:
    """I12 at the engine: the real RecommendationEngine over a small made-up area whose best café and
    restaurant are behind a ticket gate. Whether the venue is missing, cheap or dear, no course (primary or
    alternative) holds a gated shop without its venue."""
    day = template(
        Slot(1, "MEAL", 0.4), Slot(2, "ACTIVITY", 0.3), Slot(3, "CAFE", 0.3), time_band="afternoon"
    )
    ctx = context(budget_total=80000, start_at=context().start_at.replace(hour=hour), alternatives=2)
    out = await RecommendationEngine(_Source(_gated_world(venue_price))).generate(ctx, [day], profile())
    assert out.courses
    for course in out.courses:
        assert not orphaned_inner(course), [
            (s.role, s.place.name, s.place.inside_venue) for s in course.stops
        ]


# ── I8 · I9 · I10 이동 모드 (docs/65 §2 · §6) ──────────────────────────────────────────────────
# 문턱(R1 · R2 · 한 구간 도보)은 잣대 잠금에서 읽는다. 거리는 엔진이 말하는 기준점이 아니라 요청에서 따로 구한
# 기준점(역 = req.origin, 동네 = DB 의 동네 중심)에서 잰다 — 그리고 엔진의 기준점이 그것과 같은지도 본다.
# `movement` DB: fixture + 홍대 둘레 0.9~2.4km 의 가게 + 서쪽 1.8km 의 허구 동네 (conftest.movement_planner).

R1 = INVARIANT_THRESHOLDS["M1_radius_m"]
R2 = INVARIANT_THRESHOLDS["M2_radius_m"]
WALK_LEG_MAX = INVARIANT_THRESHOLDS["M2_walk_leg_max_min"]
MOVEMENT_BASES = [
    Base("seoul-hongdae", "date", WEEKDAY, "13:00"),
    Base("seoul-hongdae", "date", WEEKDAY, "18:00"),
    Base("seoul-hongdae", "friends", WEEKDAY, "13:00"),
    Base("seoul-seongsu", "friends", WEEKDAY, "18:00"),
]
# 역을 고른 요청: 동네 중심에서 300m 떨어진 점 — 기준점은 그 점이어야 한다(동네 중심이 아니라)
STATION = {
    "seoul-hongdae": (37.5572, 126.9279, "홍대 샘플역"),
    "seoul-seongsu": (37.5473, 127.0559, "성수 샘플역"),
}
MODE_CASES = [
    pytest.param("movement", b, where, id=f"movement:{where}:{b.id}")
    for b in MOVEMENT_BASES
    for where in ("region", "station")
] + [
    pytest.param("national", b, "region", id=f"national:region:{b.id}", marks=pytest.mark.national)
    for b in NATIONAL_BASES
]
# M3 의 B (사용자가 고른 곳)
ONWARD_B = {
    ("movement", "seoul-hongdae"): "seoul-mm-west",
    ("national", "seoul-hongdae"): "seoul-yeonnam",
    ("national", "seoul-seongsu"): "seoul-kondae",
}
ONWARD_CASES = [
    pytest.param(world, base, id=f"{world}:{base.id}", marks=marks)
    for world, bases, marks in (
        ("movement", MOVEMENT_BASES, ()),
        ("national", NATIONAL_BASES, (pytest.mark.national,)),
    )
    for base in bases
    if (world, base.region) in ONWARD_B
]


def _where(base: Base, where: str) -> dict[str, Any]:
    if where == "region":
        return {}
    lat, lng, label = STATION[base.region]
    return {"region": None, "origin": {"lat": lat, "lng": lng}, "origin_label": label}


async def _anchor(planner: Planner, req: Any) -> GeoPoint:
    if req.origin is not None:
        return GeoPoint(req.origin.lat, req.origin.lng)
    return await planner.region_center(req.region)


def _legs(stops: Sequence[Any]) -> list[Any]:
    """The legs of the promise: every stop's leg but the first (anchor → first stop is not one, docs/65 §6)."""
    return list(stops[1:])


def _promise_notes(plan: Plan) -> list[Any]:
    return [w for c in plan.courses for w in c.warnings if w.get("code") == "MOVEMENT_PROMISE"]


@pytest.mark.parametrize(("world", "base", "where"), MODE_CASES)
async def test_i8_m1_all_within_r1_on_foot(planner: Planner, base: Base, where: str) -> None:
    """I8: M1 → 모든 장소 R1(800m) 안 · 도보만 (한 구간 ≤ 20분, M1 ⊂ M2). 대표 + 대안 2 코스 모두."""
    plan = await _plan(planner, base, movement="inside", alternatives=2, **_where(base, where))
    assert plan.ok, f"{base.key} M1: {plan.describe()}"
    anchor = await _anchor(planner, plan.req)
    assert plan.ctx is not None and plan.ctx.promise is not None and plan.ctx.promise.center == anchor
    for course in plan.courses:
        for s in course.stops:
            far = haversine_m(anchor, s.place.point)
            assert far <= R1, f"{base.key} [{course.label}] {s.place.name} {far:.0f}m > {R1:.0f}m"
        for s in _legs(course.stops):
            assert s.leg_mode is None, f"{base.key} [{course.label}] {s.place.name}: {s.leg_mode} — 도보만"
            assert s.travel_min_from_prev <= WALK_LEG_MAX, f"{s.place.name} 도보 {s.travel_min_from_prev}분"
    assert not _promise_notes(plan)


@pytest.mark.parametrize(("world", "base", "where"), MODE_CASES)
async def test_i9_m2_all_within_r2_and_short_legs(planner: Planner, base: Base, where: str) -> None:
    """I9: M2 → 모든 장소 R2(2km) 안 · 한 구간 ≤ 20분 도보(또는 대중교통 표시, 코스당 한 번).
    movement 를 생략한 요청은 M2 와 같은 코스다(기본값)."""
    plan = await _plan(planner, base, movement="around", alternatives=2, **_where(base, where))
    assert plan.ok, f"{base.key} M2: {plan.describe()}"
    anchor = await _anchor(planner, plan.req)
    assert plan.ctx is not None and plan.ctx.promise is not None and plan.ctx.promise.center == anchor
    for course in plan.courses:
        for s in course.stops:
            far = haversine_m(anchor, s.place.point)
            assert far <= R2, f"{base.key} [{course.label}] {s.place.name} {far:.0f}m > {R2:.0f}m"
        rides = [s for s in _legs(course.stops) if s.leg_mode == "transit"]
        assert len(rides) <= 1, f"{base.key} [{course.label}] 대중교통 {len(rides)}번"
        for s in _legs(course.stops):
            if s.leg_mode is None:
                assert s.travel_min_from_prev <= WALK_LEG_MAX, (
                    f"{s.place.name} 도보 {s.travel_min_from_prev}분"
                )
    assert not _promise_notes(plan)
    omitted = await _plan(planner, base, alternatives=2, **_where(base, where))
    assert [c.place_ids for c in omitted.courses] == [c.place_ids for c in plan.courses]


@pytest.mark.parametrize(("world", "base"), ONWARD_CASES)
async def test_i10_m3_one_hop_no_return(planner: Planner, world: str, base: Base) -> None:
    """I10: M3 → 무리 A, 이동 1회, 무리 B · 역방향 없음 (docs/65 §6: 이동 뒤 장소는 모두 A 보다 B 에 가깝다).
    읽기: 두 무리는 각자 기준점의 M2 를 지킨다(R2 안 · 무리 안 한 구간 ≤ 20분 도보 또는 대중교통 한 번),
    장소마다 'A 쪽 · B 쪽'(더 가까운 기준점)을 붙이면 A…A B…B — 바뀌는 곳이 정확히 한 번(이동)."""
    b_slug = ONWARD_B[(world, base.region)]
    plan = await _plan(planner, base, movement="onward", onward_to={"region": b_slug})
    assert plan.ok, f"{base.key} M3 → {b_slug}: {plan.describe()}"
    assert plan.ctx is not None and plan.ctx.promise is not None and plan.ctx.onward_promise is not None
    a, b = await _anchor(planner, plan.req), await planner.region_center(b_slug)
    assert plan.ctx.promise.center == a and plan.ctx.onward_promise.center == b
    stops = plan.stops
    sides = ["A" if haversine_m(a, s.place.point) < haversine_m(b, s.place.point) else "B" for s in stops]
    detail = f"{base.key} → {b_slug}: {sides}\n{plan.describe()}"
    assert sides[0] == "A" and sides[-1] == "B", detail
    hops = [i for i in range(1, len(sides)) if sides[i] != sides[i - 1]]
    assert len(hops) == 1, "이동은 한 번, 돌아오지 않는다 — " + detail
    hop = hops[0]
    assert [seg["from_position"] for seg in plan.ctx.segments] == [1, hop + 1], detail
    for anchor, cluster in ((a, stops[:hop]), (b, stops[hop:])):
        for s in cluster:
            assert haversine_m(anchor, s.place.point) <= R2, f"{s.place.name} — " + detail
        rides = [s for s in _legs(cluster) if s.leg_mode == "transit"]
        assert len(rides) <= 1, detail
        for s in _legs(cluster):
            if s.leg_mode is None:
                assert s.travel_min_from_prev <= WALK_LEG_MAX, f"{s.place.name} — " + detail
    assert not _promise_notes(plan)


@pytest.mark.parametrize("movement", ["inside", "around", "onward"])
async def test_each_mode_plans_and_the_ring_is_there(movement_planner: Planner, movement: str) -> None:
    """I8 · I9 · I10 이 빈 말이 아니다: 모드마다 코스가 나오고, `movement` DB 에는 R1 · R2 밖의 가게가 있으며,
    M2 코스 중에는 R1 밖 장소를 쓰는 것이 있다(그래서 M1 의 800m 가 실제로 무언가를 막는다)."""
    extra = {"onward_to": {"region": "seoul-mm-west"}} if movement == "onward" else {}
    for base in MOVEMENT_BASES:
        if movement == "onward" and base.region != "seoul-hongdae":
            continue
        plan = await _plan(movement_planner, base, movement=movement, **extra)
        assert plan.ok, f"{base.key} {movement}: {plan.describe()}"
    hongdae = await movement_planner.region_center("seoul-hongdae")
    beyond = [
        s.place.name
        for base in MOVEMENT_BASES
        if base.region == "seoul-hongdae"
        for c in (await _plan(movement_planner, base, movement="around", alternatives=2)).courses
        for s in c.stops
        if haversine_m(hongdae, s.place.point) > R1
    ]
    assert beyond, "M2 코스가 R1 밖을 한 번도 쓰지 않으면 I8 이 아무것도 보지 않는다"
    pool = await ring_pool(movement_planner, hongdae)
    assert any(d > R2 for d in pool), "R2 밖 가게가 DB 에 없으면 I9 가 아무것도 보지 않는다"


async def ring_pool(planner: Planner, center: GeoPoint) -> list[float]:
    from sqlalchemy import select

    from app.infra.db.models import Place

    async with planner.db.sessionmaker() as session:
        rows = (await session.execute(select(Place.lat, Place.lng))).all()
    return [haversine_m(center, GeoPoint(float(lat), float(lng))) for lat, lng in rows]


# ── 아직 없는 입력 (docs/65 §2 · docs/64 R18) ────────────────────────────────────────────────


@pytest.mark.skip(reason="TODO(docs/65 I11): 아이 수 입력 `children`(R18)은 wip/r18-children 브랜치에 있다")
def test_i11_children_no_bar() -> None:
    """I11: children > 0 → 술집 · `술자리` 태그 0."""
