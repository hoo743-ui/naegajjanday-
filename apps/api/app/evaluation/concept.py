"""Concept scorecard — `python -m app.cli eval-concept` (docs/58).

`eval-courses` asks "is this course broken?" (closed doors, long walks, over budget). This asks the question
the product is built on: **is it the day the concept promises?** Does a course in a hotspot carry what people
come there for (docs/51), do dates and trips avoid national chains, does a solo night get its bar, does a
family day with the kids end early, does an anniversary spend on one table (docs/48), is the money used
(docs/49)?

Each metric has a target and a direction. One run goes through the production pipeline
(`CourseService.dry_run`, nothing written — the connection is `PRAGMA query_only`) on a fixed sample, saves
its result locally (`%LOCALAPPDATA%/naegajjanday/eval/concept/`, it needs the nationwide DB) and compares it
with the previous one. The report lists the metrics furthest from their target first, with example courses,
so an automated improvement loop can pick the worst one and fix it.

The per-course judgement (`concept_flags`, the metrics) works on plain records, so it is tested without a DB.
"""

from __future__ import annotations

import asyncio
import json
import math
import os
import subprocess
import time as _time
from collections.abc import Awaitable, Callable, Iterable, Sequence
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, time, timedelta
from functools import partial
from itertools import pairwise
from pathlib import Path
from typing import Any, cast
from zoneinfo import ZoneInfo

from app.core.config import API_ROOT

REPO_ROOT = API_ROOT.parent.parent
LOG_PATH = REPO_ROOT / "docs" / "58-concept-scorecard-log.md"

FOOD_ROLES = frozenset({"MEAL", "CAFE", "DESSERT", "BAR"})
CHAIN_TAG, UNMANNED_TAG = "체인점", "무인매장"
# the only tags the concept rules read — a record keeps these and nothing else
KEPT_TAGS = (CHAIN_TAG, UNMANNED_TAG, "단체석", "키즈프렌들리", "술자리", "매운맛", "간편식")
NOISY_FOR_PARENTS = ("activity.karaoke", "activity.arcade", "activity.escape")
KIDS_END_MIN = 21 * 60  # docs/48 §2: a day with the kids is over by eight or nine
FAMILY_LEG_MIN = 20  # docs/48 §2: 아이와 · 부모님과 — short legs
SPLURGE_SHARE = 0.35  # docs/48 §1 anniversary: "half the budget on one table"; flagged when under 35 %

# flag families (docs/58 §2): a metric counts the courses that carry one of these codes
DATE_FLAGS = frozenset(
    {
        "DATE_GROUP_SPOT",
        "DATE_KIDS_SPOT",
        "DATE_UNMANNED",
        "ANNIV_NO_SPLURGE",
        "ANNIV_SNACK_MEAL",
        "NEW_KARAOKE",
    }
)
FAMILY_FLAGS = frozenset(
    {
        "FAMILY_DRINK",
        "FAMILY_BAR",
        "KIDS_SPICY",
        "KIDS_LATE",
        "PARENTS_NOISY",
        "LONG_LEG_KIDS",
        "LONG_LEG_PARENTS",
    }
)
NIGHT_FLAGS = frozenset(
    {"CLOSED_AT_ARRIVAL", "NIGHT_TRAIL", "TOO_EARLY", "NIGHT_NO_DRINK", "DATE_UNMANNED", "FAMILY_DRINK"}
)
SCHEDULE_FLAGS = frozenset({"CLOSED_AT_ARRIVAL", "TOO_EARLY", "NIGHT_TRAIL"})


# ── records: what one course was, in plain data ───────────────────────────────────────────────


@dataclass(slots=True)
class Case:
    """One request of the sample."""

    region: str
    purpose: str
    party: int
    budget: int
    start: str  # "HH:MM"
    scene: str | None = None
    group: str = "hotspot"  # hotspot | solo_night | date_scene | family_scene | night

    @property
    def key(self) -> str:
        who = f"{self.purpose}/{self.scene}" if self.scene else self.purpose
        return f"{self.region}|{who}|{self.start}|{self.budget}"

    @property
    def night(self) -> bool:
        """The engine's own night (budget.is_night): from 21:00 to 05:00."""
        hour = int(self.start.split(":")[0])
        return hour >= 21 or hour < 5


@dataclass(slots=True)
class Stop:
    position: int
    role: str
    name: str
    category: str
    at: str  # "HH:MM"
    leave_min: int  # minutes since midnight, the small hours counted as the evening before
    price: int
    leg: int  # minutes from the previous stop
    kind: str | None = None  # day_score.experience_kind
    tags: dict[str, float] = field(default_factory=dict)
    draw: bool = False  # one of the things people come to this neighbourhood for (draws.json, curated)

    @property
    def chain(self) -> bool:
        return bool(self.tags.get(CHAIN_TAG))

    @property
    def unmanned(self) -> bool:
        return bool(self.tags.get(UNMANNED_TAG))


@dataclass(slots=True)
class Record:
    case: Case
    error: str | None = None
    price: int = 0
    stops: list[Stop] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)  # "CODE" or "CODE:detail"
    draw_eligible: bool = False  # the neighbourhood really has a draw within reach

    @property
    def ok(self) -> bool:
        return self.error is None and bool(self.stops)

    @property
    def codes(self) -> frozenset[str]:
        return frozenset(f.split(":", 1)[0] for f in self.flags)

    def line(self, codes: Iterable[str] = ()) -> str:
        c = self.case
        head = f"{c.key} → {self.price:,}"
        if self.error:
            return f"{c.key} → 코스 없음 ({self.error})"
        path = " → ".join(
            f"{s.at} {s.role} {s.name}" + ("ⓒ" if s.chain else "") + ("★" if s.draw else "")
            for s in self.stops
        )
        wanted = set(codes)
        shown = [f for f in self.flags if f.split(":", 1)[0] in wanted]
        return f"{head} | {path}" + (f"  [{', '.join(shown)}]" if shown else "")


# ── the concept's own rules (docs/48), on records ─────────────────────────────────────────────


def concept_flags(case: Case, stops: Sequence[Stop], total_price: int) -> list[str]:
    """What a course breaks of its purpose's and scene's promise (docs/48 §1–§5), beyond the harness judge."""
    out: list[str] = []
    purpose, scene = case.purpose, case.scene
    if purpose == "date":
        for s in stops:
            if s.role in ("MEAL", "BAR") and s.tags.get("단체석", 0) >= 0.8:
                out.append(f"DATE_GROUP_SPOT:{s.name}")
            if s.tags.get("키즈프렌들리", 0) >= 0.9:
                out.append(f"DATE_KIDS_SPOT:{s.name}")
            if s.unmanned:
                out.append(f"DATE_UNMANNED:{s.name}")
        if scene == "anniversary":
            splurge = max(
                (s.price for s in stops if s.role in ("MEAL", "BAR")), default=0
            )  # at night: the bar
            if total_price and splurge < SPLURGE_SHARE * total_price:
                out.append(f"ANNIV_NO_SPLURGE:{splurge:,}/{total_price:,}")
            if any(
                s.role == "MEAL" and (s.category.startswith("food.snack") or s.tags.get("간편식"))
                for s in stops
            ):
                out.append("ANNIV_SNACK_MEAL")
        if scene == "new" and any(s.category.startswith("activity.karaoke") for s in stops):
            out.append("NEW_KARAOKE")
    if purpose == "family":
        effective = scene or "kids"  # docs/48 §9: the family default is 아이와
        for s in stops:
            if s.role == "BAR" or (s.tags.get("술자리") and effective != "adults"):
                out.append(f"FAMILY_DRINK:{s.name}")
            if effective == "kids" and s.role == "MEAL" and s.tags.get("매운맛", 0) >= 0.7:
                out.append(f"KIDS_SPICY:{s.name}")
            if effective == "parents" and s.category.startswith(NOISY_FOR_PARENTS):
                out.append(f"PARENTS_NOISY:{s.name}")
            if effective in ("kids", "parents") and s.position > 1 and s.leg > FAMILY_LEG_MIN:
                out.append(f"LONG_LEG_{effective.upper()}:{s.name} {s.leg}분")
        if effective == "kids" and stops and stops[-1].leave_min > KIDS_END_MIN:
            out.append(f"KIDS_LATE:{stops[-1].name}")
    # docs/48 §1 · §3: the night of a date or of friends is a drink first (한잔 → 걷기 / 한잔 → 놀기)
    if case.night and purpose in ("date", "friends") and stops and not any(s.role == "BAR" for s in stops):
        out.append("NIGHT_NO_DRINK")
    # docs/48 §0-1: the day does not end on its weakest place
    if stops and (stops[-1].chain or stops[-1].unmanned):
        out.append(f"WEAK_ENDING:{stops[-1].name}")
    if any(a.kind == b.kind == "CAFE" for a, b in pairwise(stops)):
        out.append("CAFE_CAFE")
    return out


# ── metrics ───────────────────────────────────────────────────────────────────────────────────

Count = Callable[[Record], tuple[float, float] | None]  # (numerator, denominator); None = not counted


@dataclass(frozen=True, slots=True)
class Metric:
    id: str
    label: str
    direction: str  # "higher" | "lower": which way is better
    target: float
    count: Count
    codes: frozenset[str] = frozenset()  # the flags that make a course an example of this metric
    kind: str = "rate"  # rate (0..1) | mean
    scale: float = 0.25  # the miss that counts as 1.0 in the ranking (25 points for a rate)
    weight: float = 1.0

    def bad(self, value: float) -> float:
        """How far `value` is past the target, in the metric's own units (≤ 0: on target)."""
        return self.target - value if self.direction == "higher" else value - self.target


def _course(applies: Callable[[Record], bool], hit: Callable[[Record], bool]) -> Count:
    return lambda r: (1.0 if hit(r) else 0.0, 1.0) if applies(r) else None


def _has(codes: frozenset[str]) -> Callable[[Record], bool]:
    return lambda r: bool(r.codes & codes)


def _ok(r: Record) -> bool:
    return r.ok


def _day(r: Record) -> bool:
    return r.ok and not r.case.night


def _full_length(r: Record) -> bool:
    """A course not cut short on purpose: an evening with the kids ends by 20:30 (scenes.json › end_by),
    so its two stops are the scene working, not too few (docs/48 §2 · §6)."""
    kids = r.case.purpose == "family" and (r.case.scene or "kids") == "kids"
    return r.ok and not (kids and int(r.case.start.split(":")[0]) >= 17)


def _chains(purpose: str) -> Count:
    def count(r: Record) -> tuple[float, float] | None:
        if not r.ok or r.case.purpose != purpose:
            return None
        paid = [s for s in r.stops if s.role in FOOD_ROLES]
        return (float(sum(1 for s in paid if s.chain)), float(len(paid))) if paid else None

    return count


def _mean_stops(r: Record) -> tuple[float, float] | None:
    return (float(len(r.stops)), 1.0) if _day(r) else None


def _code(*codes: str) -> frozenset[str]:
    return frozenset(codes)


METRICS: tuple[Metric, ...] = (
    Metric("no_course_rate", "코스를 못 만든 요청", "lower", 0.02,
           _course(lambda r: True, lambda r: not r.ok), weight=1.5),
    Metric("draw_rate", "명소 동네 코스에 '그 동네에 오는 이유'(먹거리 · 볼거리)", "higher", 0.70,
           _course(lambda r: r.ok and r.draw_eligible and r.case.group == "hotspot",
                   lambda r: any(s.draw for s in r.stops))),
    Metric("chain_rate_date", "데이트의 식사 · 카페 · 술집 중 체인", "lower", 0.10, _chains("date")),
    Metric("chain_rate_friends", "친구 모임의 식사 · 카페 · 술집 중 체인", "lower", 0.25, _chains("friends")),
    Metric("chain_rate_travel", "여행의 식사 · 카페 · 술집 중 체인", "lower", 0.05, _chains("travel")),
    Metric("chain_ending_rate", "체인 · 무인 매장으로 끝나는 코스", "lower", 0.05,
           _course(_ok, _has(_code("WEAK_ENDING"))), _code("WEAK_ENDING")),
    Metric("solo_night_bar_rate", "혼자의 밤에 한잔할 곳", "higher", 0.80,
           _course(lambda r: r.ok and r.case.purpose == "solo" and r.case.night,
                   lambda r: any(s.role == "BAR" for s in r.stops))),
    Metric("date_scene_flag_rate", "데이트의 '절대 안 됨'(단체석 · 키즈 · 무인 · 힘 안 준 기념일)", "lower",
           0.05, _course(lambda r: r.ok and r.case.purpose == "date", _has(DATE_FLAGS)), DATE_FLAGS),
    Metric("family_scene_flag_rate", "가족의 '절대 안 됨'(술 · 매운맛 · 늦은 끝 · 긴 구간 · 소음)", "lower",
           0.05, _course(lambda r: r.ok and r.case.purpose == "family", _has(FAMILY_FLAGS)), FAMILY_FLAGS),
    Metric("night_violation_rate", "밤 규칙 위반(닫힌 곳 · 밤 산길 · 한잔 없는 밤 · 무인)", "lower",
           0.03, _course(lambda r: r.ok and r.case.night, _has(NIGHT_FLAGS)), NIGHT_FLAGS),
    Metric("cafe_cafe_rate", "카페 → 카페(디저트) 연달아", "lower", 0.03,
           _course(_ok, _has(_code("CAFE_CAFE"))), _code("CAFE_CAFE")),
    Metric("low_budget_use_rate", "낮 코스가 예산을 절반도 못 씀", "lower", 0.10,
           _course(_day, _has(_code("LOW_BUDGET_USE"))), _code("LOW_BUDGET_USE")),
    Metric("over_budget_rate", "예산을 넘은 코스", "lower", 0.0,
           _course(_ok, _has(_code("OVER_BUDGET"))), _code("OVER_BUDGET"), weight=1.5),
    Metric("mean_stops_day", "낮 코스의 평균 장소 수", "higher", 3.0, _mean_stops, kind="mean", scale=1.0),
    Metric("few_stops_rate", "들르는 곳이 너무 적은 코스", "lower", 0.05,
           _course(_full_length, _has(_code("FEW_STOPS"))), _code("FEW_STOPS")),
    Metric("empty_slot_rate", "템플릿 자리를 못 채운 코스", "lower", 0.10,
           _course(_ok, _has(_code("EMPTY_SLOT"))), _code("EMPTY_SLOT")),
    Metric("day_schedule_conflict_rate", "낮 코스의 닫힌 곳 · 이른 술집", "lower", 0.03,
           _course(_day, _has(SCHEDULE_FLAGS)), SCHEDULE_FLAGS),
    Metric("long_walk_rate", "한 구간을 너무 오래 걷는 코스", "lower", 0.10,
           _course(_ok, _has(_code("LONG_WALK"))), _code("LONG_WALK")),
    Metric("snack_as_meal_rate", "데이트 · 가족의 식사가 분식 · 간식", "lower", 0.03,
           _course(lambda r: r.ok and r.case.purpose in ("date", "family"), _has(_code("SNACK_AS_MEAL"))),
           _code("SNACK_AS_MEAL")),
    Metric("repeated_kind_rate", "같은 경험을 되풀이하는 코스", "lower", 0.05,
           _course(_ok, _has(_code("REPEATED_KIND"))), _code("REPEATED_KIND")),
    Metric("same_kind_twice_rate", "같은 업종을 두 번 가는 코스", "lower", 0.10,
           _course(_ok, _has(_code("SAME_KIND_TWICE"))), _code("SAME_KIND_TWICE")),
    Metric("naming_rate", "모호한 명소 이름 · 간판 아닌 법인 상호", "lower", 0.02,
           _course(_ok, _has(_code("VAGUE_SIGHT", "NOT_A_SIGN"))), _code("VAGUE_SIGHT", "NOT_A_SIGN")),
    Metric("clean_rate", "어떤 규칙에도 걸리지 않은 코스", "higher", 0.50,
           _course(_ok, lambda r: not r.flags), kind="rate", weight=0.5),
)  # fmt: skip
METRIC_BY_ID = {m.id: m for m in METRICS}


@dataclass(slots=True)
class Result:
    id: str
    value: float | None
    n: int  # courses counted
    units: float  # the denominator (stops for a stop-level rate, courses otherwise)
    target: float
    direction: str
    passed: bool
    gap: float | None  # weighted distance past the target in units of `scale` (≤ 0: on target)
    noise: float
    examples: list[str] = field(default_factory=list)


def noise_band(metric: Metric, value: float | None, units: float, spread: float = 0.0) -> float:
    """How much this number moves when one or two courses of the sample change: 1.5 standard errors,
    at least 2 points for a rate (0.1 for a mean). A change inside the band is not a regression."""
    if value is None or units <= 0:
        return 0.0
    if metric.kind == "mean":
        return round(max(0.1, 1.5 * spread / math.sqrt(units)), 3)
    p = min(max(value, 0.05), 0.95)
    return round(max(0.02, 1.5 * math.sqrt(p * (1 - p) / units)), 3)


def evaluate(metric: Metric, records: Sequence[Record], *, examples: int = 4) -> Result:
    counted = [(r, c) for r in records if (c := metric.count(r)) is not None]
    num = sum(c[0] for _r, c in counted)
    den = sum(c[1] for _r, c in counted)
    value = num / den if den else None
    spread = 0.0
    if metric.kind == "mean" and counted and value is not None:
        spread = math.sqrt(sum((c[0] / c[1] - value) ** 2 for _r, c in counted) / len(counted))
    bad = metric.bad(value) if value is not None else None
    passed = bad is not None and bad <= 1e-9
    result = Result(
        id=metric.id,
        value=round(value, 4) if value is not None else None,
        n=len(counted),
        units=den,
        target=metric.target,
        direction=metric.direction,
        passed=passed,
        gap=round(metric.weight * bad / metric.scale, 4) if bad is not None else None,
        noise=noise_band(metric, value, den, spread),
    )
    if not passed:
        # a course whose own share is on the wrong side of the target, spread over regions
        worst = [r for r, c in counted if c[1] and metric.bad(c[0] / c[1]) > 1e-9]
        result.examples = [r.line(metric.codes) for r in _spread(worst, examples)]
    return result


def _spread(records: Sequence[Record], k: int) -> list[Record]:
    """Up to k records, one per region first — five examples from one street teach little."""
    seen: set[str] = set()
    first: list[Record] = []
    rest: list[Record] = []
    for r in records:
        (rest if r.case.region in seen else first).append(r)
        seen.add(r.case.region)
    return [*first, *rest][:k]


def evaluate_all(records: Sequence[Record], *, examples: int = 4) -> list[Result]:
    return rank([evaluate(m, records, examples=examples) for m in METRICS])


def rank(results: Iterable[Result]) -> list[Result]:
    """Failing first, the furthest from target (normalized) first; then passing ones, closest to failing
    first; metrics with nothing to count last."""
    return sorted(results, key=lambda r: (r.gap is None, r.passed, -(r.gap or 0.0)))


# ── comparing runs ────────────────────────────────────────────────────────────────────────────


@dataclass(slots=True)
class Delta:
    id: str
    before: float | None
    after: float | None
    change: float | None
    status: str  # better | worse | same (within noise) | new


def compare(results: Sequence[Result], previous: dict[str, Any] | None) -> dict[str, Delta]:
    before = (previous or {}).get("metrics") or {}
    out: dict[str, Delta] = {}
    for r in results:
        old = before.get(r.id)
        if not old or old.get("value") is None or r.value is None:
            out[r.id] = Delta(r.id, (old or {}).get("value"), r.value, None, "new")
            continue
        change = r.value - float(old["value"])
        good = change if r.direction == "higher" else -change
        band = max(r.noise, float(old.get("noise") or 0.0))
        status = "same" if abs(change) <= band else "better" if good > 0 else "worse"
        out[r.id] = Delta(r.id, float(old["value"]), r.value, round(change, 4), status)
    return out


def verdict(results: Sequence[Result], deltas: dict[str, Delta], focus: str) -> tuple[bool, str]:
    """Ship a fix only if the metric it was for improved and nothing else regressed past its noise band."""
    d = deltas.get(focus)
    if d is None or d.change is None:
        return False, f"HOLD: {focus} 를 이전 실행과 비교할 수 없어요"
    direction = METRIC_BY_ID[focus].direction if focus in METRIC_BY_ID else "higher"
    improved = (d.change > 0) if direction == "higher" else (d.change < 0)
    worse = [x.id for x in deltas.values() if x.status == "worse" and x.id != focus]
    if not improved:
        return False, f"HOLD: {focus} 가 나아지지 않았어요 ({_fmt_change(focus, d.change)})"
    if worse:
        return False, f"HOLD: {focus} 는 나아졌지만 다른 지표가 나빠졌어요: {', '.join(worse)}"
    return True, f"SHIP: {focus} {_fmt_change(focus, d.change)}, 다른 지표는 잡음 범위 안"


# ── the sample ────────────────────────────────────────────────────────────────────────────────

SAMPLE_PATH = API_ROOT / "data" / "eval" / "concept.json"


def scene_regions(sample: str, path: Path = SAMPLE_PATH) -> list[str]:
    """The neighbourhoods of the scene and night groups (data/eval/concept.json — no slugs in code)."""
    data = json.loads(path.read_text(encoding="utf-8"))
    return list(data["scene_regions"][sample])


def hotspots() -> list[str]:
    """The neighbourhoods with hand-written draws (data/regions/draws.json), in file order."""
    from app.domain.region_draws import region_draws

    return [slug for slug, d in region_draws().items() if d.eat or d.see]


def build_sample(sample: str, hotspot_slugs: Sequence[str] | None = None) -> list[Case]:
    """quick ≈ 80 courses (about 6 minutes on the nationwide DB), full ≈ 350 (about 25 minutes).

    hotspot   — per hotspot: date lunch · friends evening · travel morning (+ date dinner in full)
    solo_night — one person, 30,000 won, 21:30 (+ 23:00 in full): does the night get its bar
    date_scene — 설레는 사이 · 오래 만난 사이 · 기념일, day and night
    family_scene — 아이와 · 부모님과 · 어른끼리, including an evening with the kids
    night     — a date and friends at 21:30 without a scene
    """
    if sample not in ("quick", "full"):
        raise ValueError(f"sample must be quick or full, not {sample!r}")
    full = sample == "full"
    spots = list(hotspot_slugs if hotspot_slugs is not None else hotspots())
    picked = spots if full else spots[::4]
    cases: list[Case] = []
    hot = [("date", 2, 60000, "12:00"), ("friends", 4, 108000, "19:00"), ("travel", 2, 78000, "11:00")]
    if full:
        hot.append(("date", 2, 80000, "18:00"))
    for region in picked:
        cases += [Case(region, p, n, b, t, group="hotspot") for p, n, b, t in hot]
    solo_regions = spots[::3] if full else spots[::7]
    for region in solo_regions:
        for start in ("21:30", "23:00") if full else ("21:30",):
            cases.append(Case(region, "solo", 1, 30000, start, group="solo_night"))
    scene_slugs = scene_regions(sample)
    date_scenes = (
        [
            (s, b, t)
            for s in ("new", "steady", "anniversary")
            for b, t in ((100000, "18:30"), (60000, "21:30"))
        ]
        if full
        else [("new", 60000, "21:30"), ("steady", 60000, "15:00"), ("anniversary", 100000, "18:30")]
    )
    family_scenes = [("kids", "18:30"), ("parents", "12:00"), ("adults", "21:30")]
    if full:
        family_scenes.append(("kids", "12:00"))
    night = [("date", 2, 60000), ("friends", 4, 108000)] + ([("travel", 2, 78000)] if full else [])
    for region in scene_slugs:
        cases += [Case(region, "date", 2, b, t, scene=s, group="date_scene") for s, b, t in date_scenes]
        cases += [
            Case(region, "family", 3, 120000, t, scene=s, group="family_scene") for s, t in family_scenes
        ]
        cases += [Case(region, p, n, b, "21:30", group="night") for p, n, b in night]
    return cases


def sample_day(today: date) -> date:
    """The next Saturday at least two days ahead — a weekend day, the same weekday every run."""
    days = (5 - today.weekday()) % 7
    return today + timedelta(days=days + 7 if days < 2 else days)


# ── running it on the local DB ────────────────────────────────────────────────────────────────


def readonly_database(settings: Any) -> Any:
    """The app's Database, but SQLite connections refuse writes and wait for a lock instead of failing."""
    from sqlalchemy import event

    from app.infra.db.session import Database

    db = Database(settings)
    if db.dialect == "sqlite":

        @event.listens_for(db.engine.sync_engine, "connect")
        def _readonly(dbapi_conn, _record):  # type: ignore[no-untyped-def]
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA busy_timeout=30000")
            cur.execute("PRAGMA query_only=ON")
            cur.close()

    return db


def _locked(exc: BaseException) -> bool:
    text = str(exc).lower()
    return "database is locked" in text or "database is busy" in text or "database table is locked" in text


async def with_retries[T](make: Callable[[], Awaitable[T]], session: Any, *, tries: int = 6) -> T:
    """Other jobs may be writing the local DB right now: wait and try again on "database is locked"."""
    from sqlalchemy.exc import OperationalError

    for attempt in range(tries):
        try:
            return await make()
        except OperationalError as exc:
            if not _locked(exc) or attempt == tries - 1:
                raise
            await session.rollback()
            await asyncio.sleep(min(30.0, 2.0 * 2**attempt))
    raise AssertionError("unreachable")


def _compact(text: str) -> str:
    from app.domain.signature import compact

    return compact(text)


def record_from(case: Case, region: Any, ctx: Any, course: Any, rules: dict[str, Any]) -> Record:
    from app.domain.recommendation.budget import evening_minute
    from app.domain.recommendation.day_score import experience_kind
    from app.evaluation.harness import Scenario, judge

    words = [w for w in (_compact(w) for w in ctx.draw_words) if w]
    stops = []
    for s in course.stops:
        p = s.place
        draw = not p.is_event and (
            p.id in ctx.draw_ids or (s.role in FOOD_ROLES and any(w in _compact(p.name) for w in words))
        )
        stops.append(
            Stop(
                position=s.position,
                role=s.role,
                name=p.name,
                category=p.category_code,
                at=f"{s.arrive_at:%H:%M}",
                leave_min=evening_minute(s.leave_at),
                price=s.est_price,
                leg=s.travel_min_from_prev,
                kind=experience_kind(p),
                tags={k: float(v) for k, v in p.tags.items() if k in KEPT_TAGS and v},
                draw=draw,
            )
        )
    scenario = Scenario(case.region, case.purpose, case.start, "efficient", case.party, case.budget)
    names = frozenset({region.name, region.name.removesuffix("입구").removesuffix("역")})
    found = [
        f.code + (f":{f.detail}" if f.detail else "") for f in judge(course, ctx, scenario, rules, names)
    ]
    found += concept_flags(case, stops, course.total_price)
    return Record(
        case=case,
        price=course.total_price,
        stops=stops,
        flags=found,
        draw_eligible=bool(ctx.draw_words or ctx.draw_ids),
    )


async def collect(
    db: Any,
    settings: Any,
    cases: Sequence[Case],
    day: date,
    *,
    progress: Callable[[int, int], None] | None = None,
) -> list[Record]:
    """Every case through `CourseService.dry_run` — one session, one service for the whole sample."""
    from app.core import errors
    from app.core.cache import MemoryCache
    from app.evaluation.harness import load_spec
    from app.infra.analytics.base import NoopTracker
    from app.schemas import course as dto
    from app.services.course_service import CourseService
    from app.services.narrative_service import NarrativeService

    tz = ZoneInfo(settings.timezone)
    rules = load_spec()["rules"]
    records: list[Record] = []
    async with db.sessionmaker() as session:
        service = CourseService(
            settings=settings,
            session=session,
            cache=MemoryCache(),
            narrative=cast(NarrativeService, None),  # dry_run never narrates
            tracker=NoopTracker(),
        )
        for i, case in enumerate(cases, 1):
            h, m = (int(x) for x in case.start.split(":"))
            req = dto.CourseGenerateRequest(
                region=case.region,
                purpose=case.purpose,
                party_size=case.party,
                budget_total=case.budget,
                start_at=datetime.combine(day, time(h, m), tzinfo=tz),
                alternatives=0,
                scene=case.scene,
            )
            try:
                region, ctx, out = await with_retries(partial(service.dry_run, req), session)
                records.append(record_from(case, region, ctx, out.courses[0], rules))
            except errors.AppError as exc:
                records.append(Record(case, error=exc.code))
            except Exception as exc:  # a broken case is a finding of the run, not the end of it
                await session.rollback()
                records.append(Record(case, error=f"{type(exc).__name__}: {str(exc)[:80]}"))
            if progress:
                progress(i, len(cases))
    return records


# ── history · report ──────────────────────────────────────────────────────────────────────────


def history_dir() -> Path:
    """Local only (the numbers need the nationwide DB): %LOCALAPPDATA%/naegajjanday/eval/concept."""
    if override := os.environ.get("NAEGAJJANDAY_EVAL_DIR"):
        return Path(override)
    base = os.environ.get("LOCALAPPDATA")
    root = Path(base) if base else Path.home() / ".local" / "share"
    return root / "naegajjanday" / "eval" / "concept"


def load_previous(name: str | None = None, directory: Path | None = None) -> dict[str, Any] | None:
    """A named run (`--save NAME`) or, without a name, the last run."""
    folder = directory or history_dir()
    path = folder / "named" / f"{name}.json" if name else folder / "latest.json"
    if not path.exists():
        return None
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def save_run(payload: dict[str, Any], name: str | None = None, directory: Path | None = None) -> list[Path]:
    folder = directory or history_dir()
    folder.mkdir(parents=True, exist_ok=True)
    stamp = datetime.fromisoformat(payload["run_at"]).strftime("%Y%m%d-%H%M%S")
    text = json.dumps(payload, ensure_ascii=False, indent=1)
    paths = [folder / f"{stamp}.json", folder / "latest.json"]
    if name:
        (folder / "named").mkdir(exist_ok=True)
        paths.append(folder / "named" / f"{name}.json")
    for path in paths:
        path.write_text(text, encoding="utf-8")
    return paths


def git_revision() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], cwd=API_ROOT, capture_output=True, text=True, timeout=10
        )
        return out.stdout.strip() or "?"
    except (OSError, subprocess.SubprocessError):
        return "?"


def build_payload(
    *,
    sample: str,
    day: date,
    records: Sequence[Record],
    results: Sequence[Result],
    runtime_s: float,
    note: str | None = None,
) -> dict[str, Any]:
    return {
        "version": 1,
        "run_at": datetime.now().isoformat(timespec="seconds"),
        "sample": sample,
        "day": day.isoformat(),
        "git": git_revision(),
        "runtime_s": round(runtime_s, 1),
        "courses": len(records),
        "note": note,
        "passed": sum(1 for r in results if r.passed),
        "metrics": {r.id: {k: v for k, v in asdict(r).items() if k != "id"} for r in results},
        "records": [
            {"key": r.case.key, "group": r.case.group, "error": r.error, "flags": r.flags, "line": r.line()}
            for r in records
        ],
    }


def _fmt(metric_id: str, value: float | None) -> str:
    if value is None:
        return "–"
    m = METRIC_BY_ID.get(metric_id)
    return f"{value:.2f}" if m is not None and m.kind == "mean" else f"{value:.1%}"


def _fmt_change(metric_id: str, change: float | None) -> str:
    if change is None:
        return ""
    m = METRIC_BY_ID.get(metric_id)
    return f"{change:+.2f}" if m is not None and m.kind == "mean" else f"{change * 100:+.1f}p"


def render(
    results: Sequence[Result], deltas: dict[str, Delta] | None = None, *, examples: bool = True
) -> str:
    deltas = deltas or {}
    mark = {"better": "▲", "worse": "▼", "same": "·", "new": ""}
    head = f"    {'metric':<27} {'value':>7} {'target':>9} {'Δ':>10} {'n':>5}"
    lines = [head, "    " + "-" * (len(head) - 4)]
    for r in results:
        m = METRIC_BY_ID[r.id]
        sign = "≥" if r.direction == "higher" else "≤"
        d = deltas.get(r.id)
        delta = (
            f"{_fmt_change(r.id, d.change)} {mark[d.status]}".strip() if d and d.change is not None else ""
        )
        ok = "–" if r.value is None else "✓" if r.passed else "✗"
        lines.append(
            f" {ok}  {r.id:<27} {_fmt(r.id, r.value):>7} {sign + _fmt(r.id, m.target):>9}"
            f" {delta:>10} {r.n:>5}"
        )
    if examples:
        failing = [r for r in results if not r.passed and r.value is not None]
        if failing:
            lines += ["", "고칠 곳 (목표에서 먼 순서 · 예시 코스):"]
        for r in failing:
            m = METRIC_BY_ID[r.id]
            lines.append(f"  ✗ {r.id} — {m.label}: {_fmt(r.id, r.value)} (목표 {_fmt(r.id, m.target)})")
            lines += [f"      - {x}" for x in r.examples]
    return "\n".join(lines)


LOG_HEADER = (
    "# 58 · 개념 점수표 기록\n\n"
    "`eval-concept` 한 번 = 한 줄 (docs/58-concept-scorecard.md).\n"
    "자동으로 덧붙는다 — 손으로 고치지 않는다.\n\n"
    "| 실행 | 표본 | 커밋 | 코스 | 통과 | 가장 먼 지표 (값 / 목표) | 이전 대비 | 메모 |\n"
    "|---|---|---|---|---|---|---|---|\n"
)


def log_line(payload: dict[str, Any], results: Sequence[Result], deltas: dict[str, Delta]) -> str:
    worst = [r for r in results if not r.passed and r.value is not None][:3]
    worst_text = ", ".join(
        f"{r.id} {_fmt(r.id, r.value)} / {_fmt(r.id, METRIC_BY_ID[r.id].target)}" for r in worst
    )
    better = [d.id for d in deltas.values() if d.status == "better"]
    worse = [d.id for d in deltas.values() if d.status == "worse"]
    moved = " ".join([*(f"▲{x}" for x in better), *(f"▼{x}" for x in worse)]) or "–"
    run_at = payload["run_at"].replace("T", " ")[:16]
    return (
        f"| {run_at} | {payload['sample']} | {payload['git']} | {payload['courses']} | "
        f"{payload['passed']}/{len(results)} | {worst_text or '–'} | {moved} | {payload.get('note') or ''} |"
    )


def append_log(line: str, path: Path = LOG_PATH) -> Path:
    if not path.exists():
        path.write_text(LOG_HEADER, encoding="utf-8", newline="\n")  # LF on Windows too
    with path.open("a", encoding="utf-8", newline="\n") as f:
        f.write(line + "\n")
    return path


async def run(
    settings: Any, sample: str, *, progress: Callable[[int, int], None] | None = None
) -> tuple[date, list[Record], float]:
    cases = build_sample(sample)
    day = sample_day(datetime.now(ZoneInfo(settings.timezone)).date())
    db = readonly_database(settings)
    started = _time.perf_counter()
    try:
        records = await collect(db, settings, cases, day, progress=progress)
    finally:
        await db.dispose()
    return day, records, _time.perf_counter() - started
