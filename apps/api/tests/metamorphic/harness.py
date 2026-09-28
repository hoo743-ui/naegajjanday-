"""일관성 테스트의 공용 부품 (docs/65 §3): 진짜 코스 서비스로 짜고, 결과를 비교하기 쉬운 모양으로.

코스는 `CourseService.dry_run` 으로 짠다 — `generate` 와 같은 파이프라인(지역 · 목적 · 조건 · 고정 · 엔진)에서
저장 · 캐시 · 추적만 뺀 것(점수표 eval-courses 가 재는 그것). 그래서 요청마다 "같은 DB 스냅숏"이 유지되고
(I1 의 전제), 전국 DB 를 읽기 전용으로 열어도 돈다.
빠지는 것: `generate` 가 저장한 뒤 하는 일 — 모자란 코스 채우기(`_top_up`), 추천 횟수 올리기.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, cast
from zoneinfo import ZoneInfo

from app.core import errors
from app.core.cache import MemoryCache
from app.core.config import Settings
from app.domain.models import CourseResult, RequestContext, StopResult
from app.evaluation.harness import Scenario, judge, load_spec
from app.infra.analytics.base import NoopTracker
from app.infra.db.session import Database
from app.schemas import course as dto
from app.services.course_service import CourseService
from app.services.narrative_service import NarrativeService

KST = ZoneInfo("Asia/Seoul")


def at(day: str, hm: str) -> datetime:
    """'2026-10-06', '18:00' → that minute in KST."""
    return datetime.fromisoformat(f"{day}T{hm}:00").replace(tzinfo=KST)


@dataclass(frozen=True, slots=True)
class Base:
    """One request of the sample. `world`: which DB it is meant for."""

    region: str
    purpose: str
    day: str
    start: str
    party_size: int = 2
    budget_total: int = 60000

    @property
    def key(self) -> str:
        return f"{self.region}|{self.purpose}|{self.day} {self.start}|{self.party_size}명|{self.budget_total:,}원"

    @property
    def id(self) -> str:
        """ASCII, for test ids."""
        return f"{self.region}-{self.purpose}-{self.day}T{self.start}-p{self.party_size}-{self.budget_total}"

    def request(self, **changes: Any) -> dto.CourseGenerateRequest:
        body: dict[str, Any] = {
            "region": self.region,
            "purpose": self.purpose,
            "party_size": self.party_size,
            "budget_total": self.budget_total,
            "start_at": at(self.day, self.start),
            "transport": "walk",
            "alternatives": 0,
        }
        body.update(changes)
        return dto.CourseGenerateRequest.model_validate(body)


@dataclass(slots=True)
class Plan:
    req: dto.CourseGenerateRequest
    ctx: RequestContext | None = None
    courses: list[CourseResult] = field(default_factory=list)
    error: str | None = None  # the AppError code when no course could be planned

    @property
    def ok(self) -> bool:
        return self.error is None and bool(self.courses) and bool(self.courses[0].stops)

    @property
    def course(self) -> CourseResult:
        return self.courses[0]

    @property
    def stops(self) -> list[StopResult]:
        return self.course.stops

    @property
    def ids(self) -> list[str]:
        """The primary course's places in order (public ids)."""
        return [s.place.public_id for s in self.stops]

    @property
    def roles(self) -> list[str]:
        return [s.role for s in self.stops]

    def describe(self) -> str:
        if not self.ok:
            return f"코스 없음({self.error})"
        return (
            " → ".join(
                f"{s.arrive_at:%H:%M} {s.role} {s.place.name}[{s.place.category_code}] {s.est_price:,}"
                for s in self.stops
            )
            + f" = {self.course.total_price:,}원"
            + (f" · 경고 {[w.get('code') for w in self.course.warnings]}" if self.course.warnings else "")
        )


class Planner:
    """Plans through the production service, a fresh session and service per request (nothing carried
    over between requests but the database)."""

    def __init__(self, db: Database, settings: Settings, *, world: str) -> None:
        self.db = db
        self.settings = settings
        self.world = world

    async def plan(self, req: dto.CourseGenerateRequest) -> Plan:
        async with self.db.sessionmaker() as session:
            service = CourseService(
                settings=self.settings,
                session=session,
                cache=MemoryCache(),
                narrative=cast(NarrativeService, None),  # dry_run never narrates
                tracker=NoopTracker(),
            )
            try:
                _region, ctx, out = await service.dry_run(req)
            except (errors.NoCourseAvailable, errors.BudgetTooLow) as exc:
                return Plan(req, error=exc.code)
            finally:
                await session.rollback()  # dry_run writes nothing; this only makes it certain
        return Plan(req, ctx=ctx, courses=list(out.courses))


# ── what the invariants measure ─────────────────────────────────────────────────────────────


def kept_share(before: list[str], after: list[str]) -> float:
    """I3: the share of the first course's places that are still in the second (order ignored)."""
    if not before:
        return 1.0
    return len(set(before) & set(after)) / len(set(before))


def kind_keep_share(before: list[str], after: list[str]) -> float:
    """I7: how much of the kind make-up (the multiset of course roles) survives — the multiset intersection
    over the larger course, so a kind lost or a kind added both count against it."""
    if not before and not after:
        return 1.0
    rest = list(after)
    common = 0
    for role in before:
        if role in rest:
            rest.remove(role)
            common += 1
    return common / max(len(before), len(after))


def closed_stops(plan: Plan) -> list[str]:
    """I4: the scorecard's own CLOSED_AT_ARRIVAL check (evaluation.harness.judge) — a stop reached when its
    known hours (or its sign's hours, or its trade's usual closing time) say it is shut."""
    assert plan.ctx is not None
    req = plan.req
    scenario = Scenario(
        region=req.region or "",
        purpose=req.purpose,
        start=f"{plan.ctx.start_at:%H:%M}",
        style=req.style,
        party_size=req.party_size,
        budget_total=req.budget_total,
    )
    found = judge(plan.course, plan.ctx, scenario, load_spec()["rules"])
    return [f.detail for f in found if f.code == "CLOSED_AT_ARRIVAL"]


def orphaned_inner(course: CourseResult) -> list[str]:
    """I12: stops behind a ticket gate (`inside_venue`) whose venue (`ticket_venue`) is not in the course."""
    venues = {s.place.ticket_venue for s in course.stops if s.place.ticket_venue}
    return [
        f"{s.place.name} (구역 {s.place.inside_venue})"
        for s in course.stops
        if s.place.inside_venue and s.place.inside_venue not in venues
    ]
