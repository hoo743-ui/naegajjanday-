"""Recommendation quality harness — `python -m app.cli eval-courses`.

Why it exists: checking recommendation quality by clicking through the site (or firing a few HTTP
requests and reading them) is slow and cannot be repeated. This runs a whole matrix of real scenarios
(region × purpose × start time × style) through the *production pipeline* (`CourseService.dry_run`:
same templates, same scoring profile, same candidates) with nothing written to the DB, scores every
course against explicit quality rules, and prints one scorecard. `--save` stores it as a baseline and
`--compare` shows what a change to a rule file or weight actually did — so an idea can be tried and
judged in a minute instead of argued about.

The rules and scenarios are data (`data/eval/scenarios.json`).
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, time, timedelta
from pathlib import Path
from typing import Any, cast
from zoneinfo import ZoneInfo

from app.core import errors
from app.core.cache import MemoryCache
from app.core.config import API_ROOT, Settings
from app.domain.models import CourseResult, RequestContext
from app.infra.analytics.base import NoopTracker
from app.infra.db.session import Database
from app.infra.tagging import get_tag_rules
from app.schemas import course as dto
from app.services.course_service import CourseService
from app.services.narrative_service import NarrativeService

SCENARIOS_PATH = API_ROOT / "data" / "eval" / "scenarios.json"
BASELINE_DIR = API_ROOT / "data" / "eval" / "baselines"

# (code, what it means to a user). Order = how bad it is.
CHECKS: dict[str, str] = {
    "NO_COURSE": "코스를 만들지 못했다",
    "FEW_STOPS": "들르는 곳이 너무 적다",
    "EMPTY_SLOT": "템플릿의 단계를 채우지 못해 건너뛰었다",
    "CLOSED_AT_ARRIVAL": "도착 시각에 문 닫았을 곳(밤의 박물관·시장·유적)",
    "TOO_EARLY": "그 시각에 가기엔 이른 곳(낮술·낮의 야경)",
    "LONG_WALK": "한 구간을 너무 오래 걷는다",
    "LOW_BUDGET_USE": "예산을 절반도 못 썼다",
    "OVER_BUDGET": "예산을 넘었다",
    "FAMILY_BAR": "가족 코스에 술집",
    "DATE_CHAIN": "데이트 식사·카페가 체인점",
    "NOT_A_SIGN": "간판이 아닌 법인 상호",
    "SAME_KIND_TWICE": "같은 종류를 두 번 간다",
    "SNACK_AS_MEAL": "데이트·가족의 식사 자리가 분식·간식",
    "VAGUE_SIGHT": "명소 이름이 지역명 그대로거나 너무 모호하다",
}


@dataclass(slots=True)
class Scenario:
    region: str
    purpose: str
    start: str
    style: str
    party_size: int
    budget_total: int

    @property
    def key(self) -> str:
        return f"{self.region}|{self.purpose}|{self.start}|{self.style}"


@dataclass(slots=True)
class Finding:
    code: str
    detail: str


@dataclass(slots=True)
class Outcome:
    scenario: Scenario
    stops: list[dict[str, Any]] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    price: int = 0
    walk_min: int = 0
    real_photos: int = 0
    has_specialty: bool = False  # the neighbourhood has a clear specialty (domain.signature)
    local_stops: int = 0  # stops that stand for the neighbourhood: a specialty shop or a landmark
    error: str | None = None


def load_spec(path: Path = SCENARIOS_PATH) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def build_scenarios(
    spec: dict[str, Any], scope: str, only: dict[str, list[str]], budget_scale: float = 1.0
) -> list[Scenario]:
    """`budget_scale` multiplies every budget: 3.0 asks what a generous budget buys, the case the
    service exists for (a bigger budget must become a fuller day, not the same course with change)."""
    regions = only.get("region") or spec["regions"][scope]

    def per_person(p: dict[str, Any]) -> int:
        return round(int(p["budget_per_person"]) * budget_scale / 1000) * 1000

    out = []
    for region in regions:
        for purpose, p in spec["purposes"].items():
            if only.get("purpose") and purpose not in only["purpose"]:
                continue
            for start in only.get("start") or spec["starts"]:
                for style in only.get("style") or spec["styles"]:
                    out.append(
                        Scenario(
                            region, purpose, start, style, int(p["party_size"]),
                            per_person(p) * int(p["party_size"]),
                        )
                    )  # fmt: skip
    return out


def _hm(value: str) -> time:
    h, m = value.split(":")
    return time(int(h), int(m))


def _prefix_lookup(table: dict[str, str], code: str) -> str | None:
    """'culture.museum' → its own entry, else 'culture', else nothing."""
    parts = code.split(".")
    for depth in range(len(parts), 0, -1):
        if hit := table.get(".".join(parts[:depth])):
            return None if hit == "always" else hit
    return None


def judge(
    course: CourseResult,
    ctx: RequestContext,
    scenario: Scenario,
    rules: dict[str, Any],
    region_names: frozenset[str] = frozenset(),
) -> list[Finding]:
    found: list[Finding] = []
    tag_rules = get_tag_rules()
    stops = course.stops
    if len(stops) < int(rules["min_stops"]) and not ctx.duration_min:
        found.append(Finding("FEW_STOPS", f"{len(stops)}곳"))
    for w in course.warnings:
        if w.get("code") == "SLOT_EMPTY":
            found.append(Finding("EMPTY_SLOT", str((w.get("meta") or {}).get("role"))))
    closed_after = {k: v for k, v in rules["closed_after"].items() if not k.startswith("_")}
    seen_kinds: Counter[str] = Counter()
    for s in stops:
        code, name, at = s.place.category_code, s.place.name, s.arrive_at.time()
        no_door = any(word in name for word in rules.get("no_door_names", ()))  # a beach never closes
        if (
            not s.place.is_event
            and not no_door
            and (limit := _prefix_lookup(closed_after, code))
            and at >= _hm(limit)
        ):
            found.append(Finding("CLOSED_AT_ARRIVAL", f"{name} [{code}] {at:%H:%M} 도착 (≥{limit})"))
        if (floor := _prefix_lookup(rules["not_before"], code)) and at < _hm(floor):
            found.append(Finding("TOO_EARLY", f"{name} [{code}] {at:%H:%M}"))
        if s.position > 1 and s.travel_min_from_prev > int(rules["max_walk_leg_min"]):
            found.append(Finding("LONG_WALK", f"→ {name} {s.travel_min_from_prev}분"))
        if scenario.purpose == "family" and s.role in rules["family_avoid_roles"]:
            found.append(Finding("FAMILY_BAR", name))
        if scenario.purpose == "date" and s.role in ("MEAL", "CAFE") and rules["chain_hint"] in s.place.tags:
            found.append(Finding("DATE_CHAIN", name))
        if (
            s.role == "MEAL"
            and scenario.purpose in rules.get("proper_meal_purposes", [])
            and any(code == c or code.startswith(c + ".") for c in rules.get("not_a_meal", []))
        ):
            found.append(Finding("SNACK_AS_MEAL", f"{name} [{code}]"))
        if s.role in ("ATTRACTION", "CULTURE") and (len(name.replace(" ", "")) <= 2 or name in region_names):
            found.append(Finding("VAGUE_SIGHT", name))
        if tag_rules.is_unlisted(name):
            found.append(Finding("NOT_A_SIGN", name))
        seen_kinds[code] += 1
    for code, n in seen_kinds.items():
        if n > 1:
            found.append(Finding("SAME_KIND_TWICE", code))
    use = course.total_price / max(1, scenario.budget_total)
    if use > 1.0:
        found.append(Finding("OVER_BUDGET", f"{use:.0%}"))
    elif use < float(rules["min_budget_use"]):
        found.append(Finding("LOW_BUDGET_USE", f"{use:.0%}"))
    return found


async def run(
    db: Database, settings: Settings, scenarios: list[Scenario], spec: dict[str, Any]
) -> list[Outcome]:
    tz = ZoneInfo(settings.timezone)
    day = (datetime.now(tz) + timedelta(days=int(spec.get("days_ahead", 5)))).date()
    outcomes: list[Outcome] = []
    async with db.sessionmaker() as session:
        service = CourseService(
            settings=settings,
            session=session,
            cache=MemoryCache(),
            narrative=cast(NarrativeService, None),  # dry_run never narrates
            tracker=NoopTracker(),
        )
        for sc in scenarios:
            req = dto.CourseGenerateRequest(
                region=sc.region,
                purpose=sc.purpose,
                party_size=sc.party_size,
                budget_total=sc.budget_total,
                start_at=datetime.combine(day, _hm(sc.start), tzinfo=tz),
                style=sc.style,
                alternatives=0,
            )
            outcome = Outcome(sc)
            try:
                region, ctx, out = await service.dry_run(req)
            except errors.AppError as exc:
                outcome.error = exc.code
                outcome.findings.append(Finding("NO_COURSE", exc.code))
                outcomes.append(outcome)
                continue
            course = out.courses[0]
            # a sight named exactly like the chosen area (or the area minus "입구"/"역") is the area itself
            names = frozenset({region.name, region.name.removesuffix("입구").removesuffix("역")})
            outcome.findings = judge(course, ctx, sc, spec["rules"], names)
            outcome.price, outcome.walk_min = course.total_price, course.total_travel_min
            outcome.stops = [
                {
                    "role": s.role,
                    "name": s.place.name,
                    "category": s.place.category_code,
                    "at": f"{s.arrive_at:%H:%M}",
                    "price": s.est_price,
                    "photo": bool(s.place.thumbnail_url),
                    "local": s.place.local_score > 0,
                    # paid stops only: a free street or park is not something anyone vouches for
                    "vouched": s.place.is_curated,
                    "specialty": bool(s.place.local_word),
                }
                for s in course.stops
            ]
            outcome.real_photos = sum(1 for s in outcome.stops if s["photo"])
            outcome.has_specialty = bool(ctx.local_words)
            outcome.local_stops = sum(1 for s in outcome.stops if s["local"])
            outcomes.append(outcome)
    return outcomes


def summarize(outcomes: list[Outcome], rules: dict[str, Any]) -> dict[str, Any]:
    total = len(outcomes)
    by_code: Counter[str] = Counter(f.code for o in outcomes for f in o.findings)
    clean = sum(1 for o in outcomes if not o.findings)
    stops = [s for o in outcomes for s in o.stops]
    # variety: how much of a region's courses lean on one and the same sight
    repeats: dict[str, tuple[str, float]] = {}
    per_region: dict[str, list[Outcome]] = defaultdict(list)
    for o in outcomes:
        per_region[o.scenario.region].append(o)
    for region, items in per_region.items():
        sights = Counter(
            s["name"] for o in items for s in o.stops if s["role"] in ("ATTRACTION", "CULTURE", "NIGHTVIEW")
        )
        if sights:
            name, n = sights.most_common(1)[0]
            repeats[region] = (name, n / len(items))
    return {
        "scenarios": total,
        "clean": clean,
        "clean_rate": round(clean / max(1, total), 3),
        "findings": {code: by_code[code] for code in CHECKS if by_code[code]},
        "avg_stops": round(len(stops) / max(1, total), 2),
        "real_photo_rate": round(sum(1 for s in stops if s["photo"]) / max(1, len(stops)), 3),
        # of the courses in a neighbourhood with a clear specialty, how many actually serve it
        "specialty_rate": round(
            sum(1 for o in outcomes if any(s.get("specialty") for s in o.stops))
            / max(1, sum(1 for o in outcomes if o.has_specialty)),
            3,
        ),
        # of the places people pay at, how many an official body vouches for (tourism board, model
        # restaurant, century store, 30 years in business): the stand-in for reviews we do not have
        "vouched_rate": round(
            sum(1 for s in stops if s.get("vouched") and s["price"] > 0)
            / max(1, sum(1 for s in stops if s["price"] > 0)),
            3,
        ),
        "local_rate": round(sum(1 for o in outcomes if o.local_stops) / max(1, total), 3),
        "avg_budget_use": round(
            sum(o.price / max(1, o.scenario.budget_total) for o in outcomes) / max(1, total), 3
        ),
        "most_repeated_sight": {
            r: {"name": n, "share": round(share, 2)}
            for r, (n, share) in sorted(repeats.items(), key=lambda kv: -kv[1][1])
            if share >= float(rules["repeat_share_warn"])
        },
    }


def render(summary: dict[str, Any], outcomes: list[Outcome], *, examples: int = 4) -> str:
    lines = [
        f"시나리오 {summary['scenarios']} · 결함 없는 코스 {summary['clean']} ({summary['clean_rate']:.1%})",
        f"평균 {summary['avg_stops']}곳 · 예산 사용 {summary['avg_budget_use']:.0%}"
        f" · 실제 사진 {summary['real_photo_rate']:.0%}",
        f"동네다움: 명물이 뚜렷한 동네의 코스 중 {summary.get('specialty_rate', 0):.0%} 에 명물 가게 포함"
        f" · 전체 코스의 {summary.get('local_rate', 0):.0%} 에 동네 명물·대표 볼거리가 하나 이상",
        f"보증된 곳: 돈을 쓰는 장소의 {summary.get('vouched_rate', 0):.0%} 에 공적 표식"
        "(관광공사·모범음식점·백년가게·30년)",
        "",
        "결함 (많은 순):",
    ]
    samples: dict[str, list[str]] = defaultdict(list)
    for o in outcomes:
        for f in o.findings:
            samples[f.code].append(f"{o.scenario.key} · {f.detail}")
    for code, n in sorted(summary["findings"].items(), key=lambda kv: -kv[1]):
        lines.append(f"  {code:<18} {n:>4}  {CHECKS[code]}")
        lines.extend(f"      - {x}" for x in samples[code][:examples])
    if summary["most_repeated_sight"]:
        lines.append("")
        lines.append("같은 명소에 기대는 지역 (그 지역 코스 중 비율):")
        for region, hit in summary["most_repeated_sight"].items():
            lines.append(f"  {region:<28} {hit['name']}  {hit['share']:.0%}")
    return "\n".join(lines)


def save(name: str, summary: dict[str, Any], outcomes: list[Outcome]) -> Path:
    BASELINE_DIR.mkdir(parents=True, exist_ok=True)
    path = BASELINE_DIR / f"{name}.json"
    payload = {
        "saved_at": datetime.now().isoformat(timespec="seconds"),
        "summary": summary,
        "courses": {
            o.scenario.key: {"stops": o.stops, "findings": [asdict(f) for f in o.findings]} for o in outcomes
        },
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    return path


def compare(name: str, summary: dict[str, Any], outcomes: list[Outcome]) -> str:
    path = BASELINE_DIR / f"{name}.json"
    if not path.exists():
        return f"(기준선 '{name}' 이 없어요 — 먼저 --save {name})"
    base = json.loads(path.read_text(encoding="utf-8"))
    before, lines = base["summary"], [f"기준선 '{name}' ({base['saved_at']}) 대비:"]

    def delta(label: str, a: float, b: float, *, good_up: bool, pct: bool = True) -> None:
        if a == b:
            return
        mark = "▲" if (b > a) == good_up else "▼"
        fmt = (lambda v: f"{v:.1%}") if pct else (lambda v: f"{v:g}")
        lines.append(f"  {mark} {label}: {fmt(a)} → {fmt(b)}")

    delta("결함 없는 코스", before["clean_rate"], summary["clean_rate"], good_up=True)
    delta("명물 포함", before.get("specialty_rate", 0.0), summary.get("specialty_rate", 0.0), good_up=True)
    delta("동네다운 코스", before.get("local_rate", 0.0), summary.get("local_rate", 0.0), good_up=True)
    delta("보증된 곳", before.get("vouched_rate", 0.0), summary.get("vouched_rate", 0.0), good_up=True)
    delta("실제 사진", before["real_photo_rate"], summary["real_photo_rate"], good_up=True)
    delta("예산 사용", before["avg_budget_use"], summary["avg_budget_use"], good_up=True)
    delta("평균 장소 수", before["avg_stops"], summary["avg_stops"], good_up=True, pct=False)
    for code in CHECKS:
        a, b = before["findings"].get(code, 0), summary["findings"].get(code, 0)
        delta(code, a, b, good_up=False, pct=False)
    changed = [
        o
        for o in outcomes
        if (old := base["courses"].get(o.scenario.key)) is not None
        and [s["name"] for s in old["stops"]] != [s["name"] for s in o.stops]
    ]
    lines.append(f"  코스가 바뀐 시나리오: {len(changed)} / {len(outcomes)}")
    for o in changed[:6]:
        old = " → ".join(s["name"] for s in base["courses"][o.scenario.key]["stops"])
        new = " → ".join(s["name"] for s in o.stops)
        lines.append(f"    {o.scenario.key}\n      전: {old}\n      후: {new}")
    return "\n".join(lines)
