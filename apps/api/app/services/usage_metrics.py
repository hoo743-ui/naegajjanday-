"""사용 지표 — are the courses we make actually used? (docs/61 §6, docs/62)

North star: of the times someone made a course (one `recommendation_log` row = one generate, main course and
its alternatives together), the share where within 7 days any of those courses was saved, shared, had
directions / a place page / an outbound link opened, or was confirmed / marked visited.

Sources: `recommendation_log` (the courses of each generate — `course` itself loses never-saved courses
after 24 h), `app_event` (the web's first-party events), `course.status` (saved · shared · completed: the
save time is not kept, so a saved course counts whenever it was saved), `course_feedback` (visited ·
actual spend) and `visit` (who opened a shared course). `compute()` is pure: the definitions are unit-tested.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infra.db.base import as_utc, utcnow
from app.infra.db.models import (
    AppEvent,
    Category,
    Course,
    CourseFeedback,
    Place,
    RecommendationLog,
    Visit,
)
from app.schemas import admin as dto
from app.services.event_catalog import (
    CONFIRM_EVENTS,
    OUTBOUND_EVENTS,
    REGENERATE_EVENTS,
    SAVE_EVENTS,
    SHARE_EVENTS,
    SWAP_EVENTS,
)

WEEKS = 8
USED_WITHIN = timedelta(days=7)
REROLL_LOOKBACK = timedelta(
    minutes=30
)  # a generate this soon after "다시 짜기" on the same browser is not a first
MAX_ROWS = 200_000
SAVED = ("saved", "shared", "completed")
CHUNK = 500


@dataclass(frozen=True, slots=True)
class Gen:
    at: datetime
    courses: tuple[str, ...]
    places: dict[str, tuple[str, ...]] = field(default_factory=dict)  # course → place public ids by position


@dataclass(frozen=True, slots=True)
class Ev:
    name: str
    course_id: str | None
    device: str
    at: datetime
    props: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Feedback:
    course_id: str
    at: datetime
    visited: bool
    actual_spend: int | None
    total_price: int


@dataclass(slots=True)
class Inputs:
    gens: list[Gen]
    events: list[Ev]
    owned: set[str] = field(default_factory=set)  # course ids saved · shared · completed
    feedback: list[Feedback] = field(default_factory=list)
    place_category: dict[str, str] = field(default_factory=dict)  # place public id → top category code
    category_names: dict[str, str] = field(default_factory=dict)
    course_openers: dict[str, set[str]] = field(
        default_factory=dict
    )  # course id → visitor hashes (/course/{id})


def _rate(count: int, total: int) -> dto.RateCount:
    return dto.RateCount(count=count, total=total, rate=round(count / total, 4) if total else None)


def monday_of(at: datetime, tz: ZoneInfo) -> date:
    d = (as_utc(at) or at).astimezone(tz).date()
    return d - timedelta(days=d.weekday())


def compute(data: Inputs, *, now: datetime, days: int, tz: ZoneInfo) -> dto.UsageMetrics:
    by_course: dict[str, list[Ev]] = defaultdict(list)
    for e in data.events:
        if e.course_id:
            by_course[e.course_id].append(e)
    visited_courses = {f.course_id for f in data.feedback if f.visited}

    def gen_events(g: Gen) -> list[Ev]:
        return [e for c in g.courses for e in by_course.get(c, ())]

    def signals(g: Gen) -> set[str]:
        until = g.at + USED_WITHIN
        found: set[str] = set()
        for e in gen_events(g):
            if not g.at - timedelta(minutes=5) <= e.at <= until:
                continue
            if e.name in SAVE_EVENTS:
                found.add("saved")
            elif e.name in SHARE_EVENTS:
                found.add("shared")
            elif e.name in OUTBOUND_EVENTS:
                found.add("outbound")
            elif e.name in CONFIRM_EVENTS:
                found.add("confirmed")
        if any(c in data.owned for c in g.courses):
            found.add("saved")
        if any(c in visited_courses for c in g.courses):
            found.add("confirmed")
        return found

    # --- north star, week by week ---
    this_monday = monday_of(now, tz)
    mondays = [this_monday - timedelta(weeks=i) for i in range(WEEKS - 1, -1, -1)]
    weekly: dict[date, list[set[str]]] = {m: [] for m in mondays}
    for g in data.gens:
        m = monday_of(g.at, tz)
        if m in weekly:
            weekly[m].append(signals(g))
    north_star = []
    for m in mondays:
        rows = weekly[m]
        used = sum(1 for s in rows if s)
        week_end = datetime.combine(m + timedelta(days=7), time.min, tzinfo=tz)
        north_star.append(
            dto.NorthStarWeek(
                week=m,
                generated=len(rows),
                used=used,
                rate=round(used / len(rows), 4) if rows else None,
                signals=dto.UsedSignals(
                    **{k: sum(1 for s in rows if k in s) for k in dto.UsedSignals.model_fields}
                ),
                complete=week_end + USED_WITHIN <= now,
            )
        )

    # --- the window ---
    start = now - timedelta(days=days)
    gens = [g for g in data.gens if g.at >= start]
    used_gens = [g for g in gens if signals(g)]
    with_events = [g for g in gens if gen_events(g)]

    # first course accepted: used, not reached by "다시 짜기" on the same browser, nothing swapped
    regen_at: dict[str, list[datetime]] = defaultdict(list)
    for e in data.events:
        if e.name in REGENERATE_EVENTS:
            regen_at[e.device].append(e.at)

    def device_of(g: Gen) -> str | None:
        return next((e.device for e in gen_events(g) if e.name == "course_generated"), None)

    def accepted_first(g: Gen) -> bool:
        evs = gen_events(g)
        if any(e.name in SWAP_EVENTS or e.name in REGENERATE_EVENTS for e in evs):
            return False
        device = device_of(g)
        return not (device and any(g.at - REROLL_LOOKBACK <= t <= g.at for t in regen_at.get(device, ())))

    first = sum(1 for g in used_gens if accepted_first(g))
    outbound = sum(1 for g in gens if any(e.name in OUTBOUND_EVENTS for e in gen_events(g)))

    # swaps per category: stops on courses someone looked at (any event), each swap mapped to the place
    # that stood at that spot when the course was made
    stops: Counter[str] = Counter()
    swaps: Counter[str] = Counter()
    for g in gens:
        for c in g.courses:
            evs = by_course.get(c)
            places = g.places.get(c, ())
            if not evs or not places:
                continue
            for p in places:
                stops[data.place_category.get(p, "?")] += 1
            for e in evs:
                pos = e.props.get("position")
                if e.name in SWAP_EVENTS and isinstance(pos, int) and 1 <= pos <= len(places):
                    swaps[data.place_category.get(places[pos - 1], "?")] += 1
    swap_by_category = [
        dto.CategorySwap(
            category=cat,
            name=data.category_names.get(cat, "알 수 없음" if cat == "?" else cat),
            stops=n,
            swaps=swaps[cat],
            rate=round(swaps[cat] / n, 4) if n else None,
        )
        for cat, n in stops.most_common()
    ]

    recent = [e for e in data.events if e.at >= start]
    options: dict[str, Counter[str]] = defaultdict(Counter)
    parsed = matched = 0
    for e in recent:
        if e.name == "course_option_toggled":
            o = options[str(e.props.get("option") or "?")]
            o["on" if e.props.get("on") else "off"] += 1
            o[str(e.props.get("via") or "chip")] += 1
        elif e.name == "course_option_text_parsed":
            parsed += 1
            matched += 1 if (e.props.get("matched") or 0) > 0 else 0

    # shared → opened by another browser (the sharer's own page views do not count)
    sharers: dict[str, set[str]] = defaultdict(set)
    for e in recent:
        if e.course_id and e.name in SHARE_EVENTS:
            sharers[e.course_id].add(e.device)
    opened = sum(1 for c, who in sharers.items() if data.course_openers.get(c, set()) - who)

    feedback = [f for f in data.feedback if f.at >= start]
    spent = [f for f in feedback if f.actual_spend is not None and f.total_price > 0]
    within = sum(1 for f in spent if abs((f.actual_spend or 0) - f.total_price) <= 0.2 * f.total_price)

    devices: dict[str, set[str]] = defaultdict(set)
    counts: Counter[str] = Counter()
    for e in recent:
        counts[e.name] += 1
        devices[e.name].add(e.device)

    return dto.UsageMetrics(
        days=days,
        generated_at=now,
        collecting_since=min((e.at for e in data.events), default=None),
        north_star=north_star,
        generated=len(gens),
        used=_rate(len(used_gens), len(gens)),
        with_events=_rate(len(with_events), len(gens)),
        first_course_accepted=_rate(first, len(used_gens)),
        outbound=_rate(outbound, len(gens)),
        swap_by_category=swap_by_category,
        options=[
            dto.OptionUsage(
                option=name, on=c["on"], off=c["off"], chip=c["chip"], text=c["text"], settings=c["settings"]
            )
            for name, c in sorted(options.items(), key=lambda kv: -(kv[1]["on"] + kv[1]["off"]))
        ],
        option_text=_rate(matched, parsed),
        share_opened=_rate(opened, len(sharers)),
        visited=_rate(sum(1 for f in feedback if f.visited), len(feedback)),
        spend_within_20=_rate(within, len(spent)),
        events=[dto.EventCount(name=n, count=k, devices=len(devices[n])) for n, k in counts.most_common(40)],
    )


def _pct(r: dto.RateCount | float | None) -> str:
    value = r.rate if isinstance(r, dto.RateCount) else r
    return "-" if value is None else f"{value:.0%}"


def _frac(r: dto.RateCount) -> str:
    return f"{r.count:,}/{r.total:,} ({_pct(r)})"


def format_report(m: dto.UsageMetrics) -> list[str]:
    """What `python -m app.cli usage-report` prints — the same numbers as the admin 사용 지표 page."""
    since = m.collecting_since.date().isoformat() if m.collecting_since else "아직 없음"
    lines = [
        f"사용 지표 · 최근 {m.days}일 · 1자 이벤트 수집 시작 {since}",
        "",
        "쓰인 코스 비율 (주간, 7일 안)",
    ]
    for w in m.north_star:
        s = w.signals
        lines.append(
            f"  {w.week}  만든 {w.generated:>5,}  쓰인 {w.used:>5,}  {_pct(w.rate):>5}"
            f"  (저장 {s.saved} · 공유 {s.shared} · 길찾기/링크 {s.outbound} · 확정 {s.confirmed})"
            + ("" if w.complete else "  집계 중")
        )
    lines += [
        "",
        f"만든 번 {m.generated:,} · 쓰인 {m.used.count:,} ({_pct(m.used)})"
        f" · 이벤트가 잡힌 {m.with_events.count:,} ({_pct(m.with_events)})",
        f"첫 코스 채택 {_frac(m.first_course_accepted)}",
        f"바깥 링크 · 길찾기 {_frac(m.outbound)}",
        f"공유 → 다른 브라우저에서 열림 {_frac(m.share_opened)}",
        f"다녀옴 {_frac(m.visited)} · 지출 ±20% {_frac(m.spend_within_20)}",
        f"한 줄 말 알아들음 {_frac(m.option_text)}",
    ]
    if m.swap_by_category:
        lines += ["", "업종별 바꾸기 (칸 → 바꾼 수)"]
        lines += [f"  {c.name:<10} {c.stops:>5,} → {c.swaps:>4,}  {_pct(c.rate)}" for c in m.swap_by_category]
    if m.options:
        lines += ["", "옵션 칩 (켬/끔 · 칩/말/설정)"]
        lines += [f"  {o.option:<10} {o.on}/{o.off} · {o.chip}/{o.text}/{o.settings}" for o in m.options]
    if m.events:
        lines += ["", "이벤트 (건수 · 브라우저)"]
        lines += [f"  {e.name:<28} {e.count:>6,}  {e.devices:>5,}" for e in m.events]
    return lines


def _chunks(items: Sequence[str]) -> Iterable[Sequence[str]]:
    for i in range(0, len(items), CHUNK):
        yield items[i : i + CHUNK]


class UsageMetricsService:
    def __init__(self, session: AsyncSession, timezone: str = "Asia/Seoul") -> None:
        self._s = session
        self._tz = ZoneInfo(timezone)

    async def report(self, days: int = 28, *, now: datetime | None = None) -> dto.UsageMetrics:
        now = now or utcnow()
        weeks_start = datetime.combine(
            monday_of(now, self._tz) - timedelta(weeks=WEEKS - 1), time.min, tzinfo=self._tz
        )
        start = min(weeks_start, now - timedelta(days=days))
        # events from a little earlier: a regenerate just before the first generate of the range
        since = start - REROLL_LOOKBACK

        gens: list[Gen] = []
        for at, selected in (
            await self._s.execute(
                select(RecommendationLog.created_at, RecommendationLog.selected_courses)
                .where(RecommendationLog.created_at >= start)
                .order_by(RecommendationLog.created_at)
                .limit(MAX_ROWS)
            )
        ).all():
            items = [c for c in (selected or []) if isinstance(c, dict) and c.get("course_id")]
            if not items:
                continue  # a generate that failed after logging made no course
            gens.append(
                Gen(
                    at=as_utc(at) or now,
                    courses=tuple(str(c["course_id"]) for c in items),
                    places={str(c["course_id"]): tuple(str(p) for p in c.get("places") or []) for c in items},
                )
            )

        events = [
            Ev(name=n, course_id=c, device=d, at=as_utc(at) or now, props=p or {})
            for n, c, d, at, p in (
                await self._s.execute(
                    select(
                        AppEvent.name,
                        AppEvent.course_id,
                        AppEvent.device,
                        AppEvent.created_at,
                        AppEvent.props,
                    )
                    .where(AppEvent.created_at >= since)
                    .order_by(AppEvent.created_at)
                    .limit(MAX_ROWS)
                )
            ).all()
        ]
        first_event = await self._s.scalar(select(AppEvent.created_at).order_by(AppEvent.created_at).limit(1))

        owned = set(
            (
                await self._s.scalars(
                    select(Course.public_id).where(Course.status.in_(SAVED), Course.created_at >= start)
                )
            ).all()
        )
        feedback = [
            Feedback(
                course_id=cid, at=as_utc(at) or now, visited=bool(v), actual_spend=spend, total_price=price
            )
            for cid, at, v, spend, price in (
                await self._s.execute(
                    select(
                        Course.public_id,
                        CourseFeedback.created_at,
                        CourseFeedback.visited,
                        CourseFeedback.actual_spend,
                        Course.total_price,
                    )
                    .join(Course, Course.id == CourseFeedback.course_id)
                    .where(CourseFeedback.created_at >= start)
                )
            ).all()
        ]

        # categories of the places on courses someone looked at
        looked = {e.course_id for e in events if e.course_id}
        place_ids = sorted({p for g in gens for c in g.courses if c in looked for p in g.places.get(c, ())})
        place_category: dict[str, str] = {}
        for part in _chunks(place_ids):
            for pid, code in (
                await self._s.execute(
                    select(Place.public_id, Category.code)
                    .join(Category, Category.id == Place.category_id)
                    .where(Place.public_id.in_(part))
                )
            ).all():
                place_category[str(pid)] = str(code).split(".")[0]
        tops = sorted(set(place_category.values()))
        category_names = {
            str(code): str(name)
            for code, name in (
                await self._s.execute(select(Category.code, Category.name).where(Category.code.in_(tops)))
            ).all()
        }

        openers: dict[str, set[str]] = defaultdict(set)
        shared = sorted({e.course_id for e in events if e.course_id and e.name in SHARE_EVENTS})
        for part in _chunks(shared):
            paths = [f"/course/{c}" for c in part]
            for path, visitor in (
                await self._s.execute(
                    select(Visit.path, Visit.visitor).where(Visit.path.in_(paths), Visit.created_at >= since)
                )
            ).all():
                openers[str(path).removeprefix("/course/")].add(str(visitor))

        data = Inputs(
            gens=gens,
            events=events,
            owned=owned,
            feedback=feedback,
            place_category=place_category,
            category_names=category_names,
            course_openers=dict(openers),
        )
        out = compute(data, now=now, days=days, tz=self._tz)
        if first_event is not None:
            out.collecting_since = as_utc(first_event)
        return out
