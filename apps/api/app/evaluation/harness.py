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
import math
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, time, timedelta
from pathlib import Path
from typing import Any, cast
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.core import errors
from app.core.cache import MemoryCache
from app.core.config import API_ROOT, Settings
from app.domain.anchors import university_rules
from app.domain.media import SHOWABLE, distinct_photos
from app.domain.models import CourseResult, GeoPoint, RequestContext
from app.domain.recommendation.budget import evening_minute, is_night
from app.domain.recommendation.day_score import REPEATABLE, experience_kind
from app.domain.recommendation.features import is_open
from app.domain.routing.travel_time import haversine_m
from app.infra.analytics.base import NoopTracker
from app.infra.db.models import PlaceImage
from app.infra.db.session import Database
from app.infra.default_hours import get_default_hours
from app.infra.tagging import get_tag_rules
from app.repositories.place_repo import SqlPlaceRepository
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
    "NIGHT_TRAIL": "해 진 뒤의 산길 · 둘레길",
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
    "REPEATED_KIND": "같은 경험(카페 · 카페)을 되풀이한다",
    "PHOTO_TWICE": "한 코스에 같은 사진이 두 번",
    "PHOTO_UNVERIFIED": "검증되지 않은 사진을 보여 준다",
}


@dataclass(slots=True)
class Scenario:
    region: str
    purpose: str
    start: str
    style: str
    party_size: int
    budget_total: int
    anchor: str | None = None  # docs/34: a campus by name ("가천대학교"); the day is planned around it

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
    # docs/29 day metrics
    between_min: int = 0  # travel between stops (the first leg from the area's centre excluded)
    kinds: int = 0  # distinct kinds of experience
    concentration: float = 0.0  # largest share of stops in one 500 m block
    purpose_fit: float = 0.0
    beyond_core: int = 0  # stops outside the neighbourhood's own radius
    spread_m: int = 0  # the widest distance between two stops


def load_spec(path: Path = SCENARIOS_PATH) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def build_scenarios(
    spec: dict[str, Any], scope: str, only: dict[str, list[str]], budget_scale: float = 1.0
) -> list[Scenario]:
    """`budget_scale` multiplies every budget: 3.0 asks what a generous budget buys, the case the
    service exists for (a bigger budget must become a fuller day, not the same course with change)."""
    if scope == "university":
        return _university_scenarios(spec, only, budget_scale)
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


def _university_scenarios(
    spec: dict[str, Any], only: dict[str, list[str]], budget_scale: float
) -> list[Scenario]:
    """docs/34: campus days — each campus × each campus purpose, by the campus's name (ids differ per DB)."""
    uni = spec["universities"]
    out = []
    for name in only.get("region") or uni["anchors"]:
        for purpose, p in uni["purposes"].items():
            if only.get("purpose") and purpose not in only["purpose"]:
                continue
            for start in only.get("start") or uni.get("starts", spec["starts"]):
                party = int(p["party_size"])
                budget = round(int(p["budget_per_person"]) * budget_scale / 1000) * 1000 * party
                out.append(Scenario(f"univ:{name}", purpose, start, "efficient", party, budget, anchor=name))
    return out


def _hm(value: str) -> time:
    h, m = value.split(":")
    return time(int(h), int(m))


def _minute(value: str) -> int:
    h, m = value.split(":")
    return int(h) * 60 + int(m)


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
    night = is_night(ctx.start_at)
    min_stops = int(rules.get("min_stops_night", rules["min_stops"]) if night else rules["min_stops"])
    if len(stops) < min_stops and not ctx.duration_min:
        found.append(Finding("FEW_STOPS", f"{len(stops)}곳"))
    for w in course.warnings:
        if w.get("code") == "SLOT_EMPTY":
            found.append(Finding("EMPTY_SLOT", str((w.get("meta") or {}).get("role"))))
    closed_after = {k: v for k, v in rules["closed_after"].items() if not k.startswith("_")}
    signs = get_default_hours()
    seen_kinds: Counter[str] = Counter()
    for s in stops:
        code, name, at = s.place.category_code, s.place.name, s.arrive_at.time()
        no_door = any(word in name for word in rules.get("no_door_names", ()))  # a beach never closes
        if s.place.is_event:
            pass
        elif s.place.hours_known:
            # the place's own hours (TourAPI · docs/55) are evidence; the category rule below is a guess
            if not is_open(s.place.opening_hours, s.arrive_at):
                found.append(Finding("CLOSED_AT_ARRIVAL", f"{name} [{code}] {at:%H:%M} 도착 (영업시간 밖)"))
        elif (sign := signs.for_sign(code, name)) is not None:
            # what the sign says (a mall, "24시", a museum by name — data/hours/default_hours.json › by_name)
            # beats the trade's guess below: '롯데월드몰' is a landmark by category and open until 22:00
            if not is_open(sign, s.arrive_at):
                found.append(
                    Finding("CLOSED_AT_ARRIVAL", f"{name} [{code}] {at:%H:%M} 도착 (간판 영업시간 밖)")
                )
        elif (
            not no_door
            and (limit := _prefix_lookup(closed_after, code))
            and evening_minute(s.arrive_at) >= _minute(limit)  # a museum at 00:30 is closed too
        ):
            found.append(Finding("CLOSED_AT_ARRIVAL", f"{name} [{code}] {at:%H:%M} 도착 (≥{limit})"))
        dark = at >= time(19) or at < time(6)
        if dark and ctx.transport != "car" and any(w in name for w in rules.get("night_trail_words", ())):
            found.append(Finding("NIGHT_TRAIL", f"{name} {at:%H:%M} 도착"))
        # past midnight is still the evening before: a pub at 00:12 is late, not early
        if (floor := _prefix_lookup(rules["not_before"], code)) and evening_minute(s.arrive_at) < _minute(
            floor
        ):
            found.append(Finding("TOO_EARLY", f"{name} [{code}] {at:%H:%M}"))
        # v1 promised "20 min a leg"; v2 prices a longer leg instead of forbidding it -> flag the long ones
        leg_limit = int(rules.get("max_walk_leg_min_v2", 30) if ctx.is_v2 else rules["max_walk_leg_min"])
        if s.position > 1 and s.travel_min_from_prev > leg_limit:
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
    experiences = Counter(k for s in stops if (k := experience_kind(s.place)))
    for kind, n in experiences.items():
        if n > REPEATABLE.get(kind, 1):
            found.append(Finding("REPEATED_KIND", f"{kind} x{n}"))
    use = course.total_price / max(1, scenario.budget_total)
    if use > 1.0:
        found.append(Finding("OVER_BUDGET", f"{use:.0%}"))
    elif use < float(rules["min_budget_use"]):
        found.append(Finding("LOW_BUDGET_USE", f"{use:.0%}"))
    return found


def _concentration(points: list[tuple[float, float]], cell_m: float = 500.0) -> float:
    if not points:
        return 0.0
    d_lat = cell_m / 111_000
    cells = Counter(
        (math.floor(lat / d_lat), math.floor(lng / (d_lat / max(0.2, math.cos(math.radians(lat))))))
        for lat, lng in points
    )
    return max(cells.values()) / len(points)


async def _photo_status(session: Any, stops: list[Any]) -> dict[int, str]:
    """place id -> verification status of the photo the course shows for it (docs/29 §27)."""
    urls = {
        s.place.id: s.place.thumbnail_url for s in stops if s.place.thumbnail_url and not s.place.is_event
    }
    if not urls:
        return {}
    rows = (
        await session.execute(
            select(PlaceImage.place_id, PlaceImage.url, PlaceImage.verification_status).where(
                PlaceImage.place_id.in_(list(urls))
            )
        )
    ).all()
    return {pid: status for pid, url, status in rows if urls.get(pid) == url}


async def run(
    db: Database,
    settings: Settings,
    scenarios: list[Scenario],
    spec: dict[str, Any],
    *,
    algorithm: str | None = None,
    move_style: str | None = None,
    duration_min: int | None = None,
    transport: str = "walk",
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
            anchor = None
            if sc.anchor:  # docs/34: find the campus by name in this database
                found = await SqlPlaceRepository(session).search_campuses(
                    sc.anchor, str(university_rules()["category"]), 1
                )
                if not found:
                    outcome = Outcome(sc, error="ANCHOR_NOT_FOUND")
                    outcome.findings.append(Finding("NO_COURSE", f"캠퍼스 없음: {sc.anchor}"))
                    outcomes.append(outcome)
                    continue
                anchor = dto.AnchorRef(kind="university", id=found[0].public_id)
            req = dto.CourseGenerateRequest(
                region=None if anchor else sc.region,
                anchor=anchor,
                purpose=sc.purpose,
                party_size=sc.party_size,
                budget_total=sc.budget_total,
                start_at=datetime.combine(day, _hm(sc.start), tzinfo=tz),
                style=sc.style,
                alternatives=0,
                algorithm=algorithm,
                move_style=move_style,
                duration_min=duration_min,
                transport=transport,
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
            photos = distinct_photos([s.place.thumbnail_url for s in course.stops])
            status = await _photo_status(session, course.stops)
            for s, shown in zip(course.stops, photos, strict=True):
                if s.place.thumbnail_url and shown is None:
                    outcome.findings.append(Finding("PHOTO_TWICE", s.place.name))
                elif shown and not s.place.is_event and status.get(s.place.id) not in SHOWABLE:
                    outcome.findings.append(Finding("PHOTO_UNVERIFIED", s.place.name))
            centre = GeoPoint(region.center_lat, region.center_lng)
            points = [(s.place.lat, s.place.lng) for s in course.stops]
            n_stops = max(1, len(course.stops))
            outcome.between_min = sum(s.travel_min_from_prev for s in course.stops[1:])
            outcome.kinds = len({k for s in course.stops if (k := experience_kind(s.place))})
            outcome.concentration = _concentration(points)
            outcome.purpose_fit = (
                sum(s.score_breakdown.get("purpose_fit", 0.0) for s in course.stops) / n_stops
            )
            outcome.beyond_core = sum(
                1 for s in course.stops if haversine_m(centre, s.place.point) > region.radius_m
            )
            outcome.spread_m = round(
                max(
                    (haversine_m(a.place.point, b.place.point) for a in course.stops for b in course.stops),
                    default=0.0,
                )
            )
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
                    "kind": experience_kind(s.place),
                    "leg": s.travel_min_from_prev,
                    "reasons": list(s.reason_codes),
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
    ok = [o for o in outcomes if o.stops]
    n_ok = max(1, len(ok))

    def share(pred: Any) -> float:
        return round(sum(1 for o in ok if pred(o)) / n_ok, 3)

    shown = max(1, sum(1 for s in stops if s["photo"]))
    day = {
        "avg_between_min": round(sum(o.between_min for o in ok) / n_ok, 1),
        "avg_kinds": round(sum(o.kinds for o in ok) / n_ok, 2),
        "avg_concentration": round(sum(o.concentration for o in ok) / n_ok, 3),
        "repeat_rate": share(lambda o: any(f.code == "REPEATED_KIND" for f in o.findings)),
        "purpose_fit": round(sum(o.purpose_fit for o in ok) / n_ok, 3),
        "budget_fit_rate": share(lambda o: o.price <= o.scenario.budget_total),
        "schedule_conflict_rate": share(
            lambda o: any(f.code in ("CLOSED_AT_ARRIVAL", "TOO_EARLY") for f in o.findings)
        ),
        "photo_mismatch_rate": round(by_code["PHOTO_UNVERIFIED"] / shown, 3),
        "photo_dup_rate": share(lambda o: any(f.code == "PHOTO_TWICE" for f in o.findings)),
        "beyond_core_rate": round(sum(o.beyond_core for o in ok) / max(1, len(stops)), 3),
        "avg_spread_m": round(sum(o.spread_m for o in ok) / n_ok),
    }
    return {
        **day,
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
        f"하루: 장소 사이 이동 평균 {summary.get('avg_between_min', 0)}분"
        f" · 경험 종류 {summary.get('avg_kinds', 0)}가지"
        f" · 한 블록 집중 {summary.get('avg_concentration', 0):.0%}"
        f" · 경험 반복 {summary.get('repeat_rate', 0):.0%}"
        f" · 목적 적합 {summary.get('purpose_fit', 0):.2f}",
        f"      예산 안 {summary.get('budget_fit_rate', 0):.0%}"
        f" · 일정 충돌 {summary.get('schedule_conflict_rate', 0):.0%}"
        f" · 동네 밖 장소 {summary.get('beyond_core_rate', 0):.0%}"
        f" · 장소 간 최대 거리 평균 {summary.get('avg_spread_m', 0)}m",
        f"사진: 오매칭 {summary.get('photo_mismatch_rate', 0):.1%}"
        f" · 한 코스 중복 {summary.get('photo_dup_rate', 0):.1%}",
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
    # docs/29: more travel is not worse by itself - shown as a plain change, judged with the rest
    for key, label, good_up, pct in (
        ("avg_kinds", "경험 종류", True, False),
        ("avg_concentration", "한 블록 집중", False, True),
        ("repeat_rate", "경험 반복", False, True),
        ("purpose_fit", "목적 적합", True, False),
        ("budget_fit_rate", "예산 안", True, True),
        ("schedule_conflict_rate", "일정 충돌", False, True),
        ("photo_mismatch_rate", "사진 오매칭", False, True),
        ("photo_dup_rate", "사진 중복", False, True),
    ):
        if key in before:
            delta(label, before[key], summary[key], good_up=good_up, pct=pct)
    for key, label in (
        ("avg_between_min", "장소 사이 이동(분)"),
        ("beyond_core_rate", "동네 밖 장소"),
        ("avg_spread_m", "장소 간 최대 거리(m)"),
    ):
        if key in before and before[key] != summary[key]:
            lines.append(f"  · {label}: {before[key]} -> {summary[key]}")
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
