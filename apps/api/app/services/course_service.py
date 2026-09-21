"""Course use-cases: generate, read, swap, reorder, save, feedback, narrative stream."""

from __future__ import annotations

import hashlib
import json
import random
import time
import uuid
from collections.abc import AsyncIterator, Sequence
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import errors
from app.core.cache import Cache
from app.core.config import Settings
from app.core.logging import get_logger
from app.domain.models import (
    BudgetTooLowError,
    CourseResult,
    DomainError,
    EngineOutput,
    GeoPoint,
    PlaceCandidate,
    RequestContext,
    ScoringProfile,
    Slot,
    StopResult,
    Template,
)
from app.domain.recommendation.budget import SlotBudget
from app.domain.recommendation.candidates import FilterContext, area_names_of, hard_filter
from app.domain.recommendation.composer import CourseComposer, Partial, objective
from app.domain.recommendation.engine import RecommendationEngine, build_course
from app.domain.recommendation.features import is_open
from app.domain.recommendation.scorer import PlaceScorer
from app.domain.recommendation.style import (
    DEFAULT_STYLE,
    resolve_style,
    styled_affinity,
    styled_avoidance,
    styled_profile,
    styled_templates,
)
from app.domain.routing.travel_time import TravelTimeProvider, encode_polyline
from app.infra.analytics.base import AnalyticsEvent, EventTracker
from app.infra.db.base import as_utc
from app.infra.db.models import Course, CourseFeedback, CourseStop, Purpose, RecommendationLog, Region, User
from app.infra.tagging import get_tag_rules
from app.repositories.config_repo import SqlConfigRepository
from app.repositories.course_repo import OWNED_STATUSES, SqlCourseRepository
from app.repositories.place_repo import SqlPlaceRepository
from app.repositories.region_repo import SqlRegionRepository
from app.repositories.user_repo import SqlUserRepository
from app.schemas import course as dto
from app.schemas.common import LatLng, decode_cursor, encode_cursor
from app.services.narrative_service import Narrative, NarrativeService

logger = get_logger(__name__)

COURSE_CACHE_TTL_S = 300
IDEMPOTENCY_TTL_S = 86_400
RANDOM_TOP_N = 5
PREFERENCE_EMA_ALPHA = 0.2


class CourseService:
    def __init__(
        self,
        *,
        settings: Settings,
        session: AsyncSession,
        cache: Cache,
        narrative: NarrativeService,
        tracker: EventTracker,
        travel_provider: TravelTimeProvider | None = None,
    ) -> None:
        self._settings = settings
        self._s = session
        self._cache = cache
        self._narrative = narrative
        self._tracker = tracker
        self._travel = travel_provider
        self._regions = SqlRegionRepository(session)
        self._config = SqlConfigRepository(session)
        self._places = SqlPlaceRepository(session)
        self._courses = SqlCourseRepository(session)
        self._users = SqlUserRepository(session)
        self._tz = ZoneInfo(settings.timezone)

    # --- generate ----------------------------------------------------------------------------

    async def _plan(
        self, req: dto.CourseGenerateRequest, user: User | None
    ) -> tuple[Region, GeoPoint, Purpose, RequestContext, ScoringProfile, EngineOutput]:
        """Everything up to and including the engine run — no cache, no rows, no tracking."""
        region, origin = await self._resolve_region(req)
        purpose = await self._config.get_purpose(req.purpose)
        if purpose is None:
            raise errors.PurposeNotFound(f"'{req.purpose}' 목적은 아직 지원하지 않아요.")
        profile = await self._config.scoring_profile(purpose.id, purpose.code)
        templates = await self._config.templates_for(purpose.id, purpose.code)
        ctx = await self._build_context(
            origin=origin,
            radius_m=region.radius_m,
            region_id=region.id,
            purpose=purpose,
            party_size=req.party_size,
            budget_total=req.budget_total,
            start_at=self._local(req.start_at),
            transport=req.transport,
            duration_min=req.duration_min,
            include_roles=req.include_roles,
            preferences=req.preferences.model_dump(),
            alternatives=req.alternatives,
            user=user,
        )
        ctx.area_names = area_names_of(region.name)
        profile, templates = self._apply_style(ctx, profile, templates, req.style)
        engine = RecommendationEngine(self._places, self._travel)
        try:
            out = await engine.generate(ctx, templates, profile)
        except BudgetTooLowError as exc:
            raise errors.BudgetTooLow(
                f"{region.name}에서 {req.party_size}명 기준 최소 {exc.min_budget:,}원이 필요해요.",
                meta={"min_budget": exc.min_budget},
            ) from exc
        except DomainError as exc:
            raise errors.NoCourseAvailable(
                f"{region.name}에서 조건에 맞는 코스를 찾지 못했어요. 예산이나 시간을 바꿔 볼까요?"
            ) from exc
        return region, origin, purpose, ctx, profile, out

    async def dry_run(self, req: dto.CourseGenerateRequest) -> tuple[Region, RequestContext, EngineOutput]:
        """The exact production pipeline with nothing persisted — what `eval-courses` measures."""
        region, _origin, _purpose, ctx, _profile, out = await self._plan(req, None)
        return region, ctx, out

    async def generate(
        self, req: dto.CourseGenerateRequest, user: User | None, idempotency_key: str | None = None
    ) -> dto.CourseGenerateResponse:
        started = time.perf_counter()
        body = req.model_dump(mode="json")
        digest = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()[:32]
        owner = user.public_id if user else "anon"
        keys = [f"course:{owner}:{digest}"]
        if idempotency_key:
            keys.insert(0, f"idem:{owner}:{hashlib.sha256(idempotency_key.encode()).hexdigest()[:32]}")
        for key in keys:
            if (cached := await self._cache.get(key)) is not None:
                return dto.CourseGenerateResponse.model_validate(cached)

        region, origin, purpose, ctx, profile, out = await self._plan(req, user)

        request_id = str(uuid.uuid4())
        log = await self._courses.add_log(
            RecommendationLog(
                request_id=request_id,
                user_id=user.id if user else None,
                region_id=region.id,
                purpose_id=purpose.id,
                request=body,
                candidate_count=out.candidates_count,
                scoring_profile_version=profile.label,
                engine_version=self._settings.engine_version,
                selected_courses=[],
                warnings=out.warnings,
            )
        )
        snapshot = {
            "preferences": req.preferences.model_dump(),
            "stay_scale": out.stay_scale,
            "duration_min": req.duration_min,
            "style": ctx.style,
            # echoed by `get()` so the result page and a reroll stay around the same station / place
            "origin_label": req.origin_label if req.origin else None,
        }
        rows: list[tuple[Course, CourseResult, Narrative]] = []
        for result in out.courses:
            narrative = await self._narrative.generate(
                result,
                party_size=req.party_size,
                budget_total=req.budget_total,
                transport=req.transport,
                use_llm=self._settings.narrative_inline_llm,
                tag_affinity=ctx.purpose_tag_affinity,
            )
            row = Course(
                user_id=user.id if user else None,
                region_id=region.id,
                purpose_id=purpose.id,
                party_size=req.party_size,
                budget_total=req.budget_total,
                transport=req.transport,
                origin_lat=origin.lat,
                origin_lng=origin.lng,
                start_at=ctx.start_at,
                request=snapshot,
                recommendation_log_id=log.id,
                warnings=[],
            )
            self._apply(row, result, narrative)
            await self._courses.add(row)
            rows.append((row, result, narrative))

        log.selected_courses = [
            {
                "course_id": row.public_id,
                "label": r.label,
                "objective": r.objective,
                "places": [s.place.public_id for s in r.stops],
            }
            for row, r, _ in rows
        ]
        log.latency_ms = int((time.perf_counter() - started) * 1000)
        await self._places.bump_recommend_count(
            [s.place.id for s in out.courses[0].stops if not s.place.is_event]
        )
        events = await self._places.events_near(origin, region.radius_m * 1.5, ctx.start_at.date())
        await self._s.commit()

        response = dto.CourseGenerateResponse(
            request_id=request_id,
            courses=[self._view(row, r.stops, origin) for row, r, _ in rows],
            nearby_events=[
                dto.NearbyEvent(
                    id=e.public_id,
                    title=e.title,
                    starts_on=e.starts_on,
                    ends_on=e.ends_on,
                    distance_m=round(dist),
                    is_free=e.is_free,
                )
                for e, dist in events[:5]
            ],
            meta=dto.GenerateMeta(
                engine_version=self._settings.engine_version,
                scoring_profile=profile.label,
                template=out.template.code,
                candidates=out.candidates_count,
                latency_ms=log.latency_ms,
            ),
        )
        payload = response.model_dump(mode="json")
        await self._cache.set(keys[-1], payload, COURSE_CACHE_TTL_S)
        if idempotency_key:
            await self._cache.set(keys[0], payload, IDEMPOTENCY_TTL_S)
        await self._tracker.track(
            AnalyticsEvent(
                "course_generated",
                distinct_id=user.public_id if user else request_id,
                properties={
                    "region": region.slug,
                    "purpose": purpose.code,
                    "party_size": req.party_size,
                    "budget_total": req.budget_total,
                    "latency_ms": log.latency_ms,
                    "warnings": [w["code"] for w in out.warnings],
                },
            )
        )
        return response

    async def _resolve_region(self, req: dto.CourseGenerateRequest) -> tuple[Region, GeoPoint]:
        if req.region:
            region = await self._regions.get_by_slug(req.region)
            if region is None:
                raise errors.RegionNotFound(f"'{req.region}' 지역은 아직 없어요.")
        else:
            assert req.origin is not None
            region = await self._regions.nearest_active(GeoPoint(req.origin.lat, req.origin.lng))
            if region is None:
                raise errors.RegionNotFound("근처에 서비스 중인 지역이 없어요.")
        if region.status != "active":
            raise errors.RegionNotReady(f"{region.name}은(는) 장소를 모으는 중이에요. 조금만 기다려 주세요!")
        origin = (
            GeoPoint(req.origin.lat, req.origin.lng)
            if req.origin
            else GeoPoint(region.center_lat, region.center_lng)
        )
        return region, origin

    def _local(self, value: datetime | None) -> datetime:
        if value is None:
            return datetime.now(self._tz).replace(second=0, microsecond=0)
        return (value if value.tzinfo else value.replace(tzinfo=self._tz)).astimezone(self._tz)

    async def _build_context(
        self,
        *,
        origin: GeoPoint,
        radius_m: int,
        region_id: int | None,
        purpose: Purpose,
        party_size: int,
        budget_total: int,
        start_at: datetime,
        transport: str,
        duration_min: int | None,
        include_roles: list[str] | None,
        preferences: dict[str, Any],
        alternatives: int,
        user: User | None,
    ) -> RequestContext:
        liked, disliked = (
            list(preferences.get("liked_tags") or []),
            list(preferences.get("disliked_tags") or []),
        )
        category_weights: dict[str, float] = {}
        if user is not None and (pref := await self._users.get_preference(user.id)) is not None:
            liked = liked or list(pref.liked_tags or [])
            disliked = disliked or list(pref.disliked_tags or [])
            category_weights = dict(pref.category_weights or {})
        return RequestContext(
            origin=origin,
            radius_m=radius_m,
            purpose_code=purpose.code,
            party_size=party_size,
            budget_total=budget_total,
            start_at=start_at,
            transport=transport,  # type: ignore[arg-type]
            duration_min=duration_min,
            include_roles=[r.upper() for r in include_roles] if include_roles else None,
            liked_tags=liked,
            disliked_tags=disliked,
            category_weights=category_weights,
            exclude_place_ids=await self._places.ids_by_public_ids(
                preferences.get("exclude_place_ids") or []
            ),
            purpose_tag_affinity=await self._config.tag_affinity(purpose.id),
            category_rating_avg=await self._places.category_rating_avg(region_id),
            alternatives=alternatives,
        )

    # --- persistence mapping -----------------------------------------------------------------

    @staticmethod
    def _apply(row: Course, result: CourseResult, narrative: Narrative) -> None:
        row.label = result.label
        row.template_id = result.template_id or row.template_id
        row.total_price = result.total_price
        row.total_travel_min = result.total_travel_min
        row.total_distance_m = result.total_distance_m
        row.total_score = result.score
        row.duration_min = result.duration_min
        row.optimizer = result.optimizer
        row.warnings = result.warnings
        row.summary, row.tip, row.narrative = narrative.summary, narrative.tip, narrative.as_text()
        row.stops = [
            CourseStop(
                position=s.position,
                place_id=None if s.place.is_event else s.place.id,
                event_id=s.place.id if s.place.is_event else None,
                course_role=s.role,
                arrive_at=s.arrive_at,
                leave_at=s.leave_at,
                est_price=s.est_price,
                travel_min_from_prev=s.travel_min_from_prev,
                distance_m_from_prev=s.distance_m_from_prev,
                score=s.score,
                score_breakdown=s.score_breakdown,
                reason=narrative.reasons.get(s.position),
                congestion=s.congestion,
                slot=_slot_snapshot(s),
            )
            for s in result.stops
        ]

    def _view(self, row: Course, stops: Sequence[StopResult], origin: GeoPoint) -> dto.CourseOut:
        reasons = {s.position: s.reason for s in row.stops}
        budget = row.budget_total
        return dto.CourseOut(
            id=row.public_id,
            label=row.label,
            status=row.status,
            summary=row.summary,
            tip=row.tip,
            totals=dto.Totals(
                price=row.total_price,
                price_per_person=round(row.total_price / max(1, row.party_size)),
                budget_left=budget - row.total_price,
                budget_utilization=round(row.total_price / budget, 3) if budget else 0.0,
                travel_min=row.total_travel_min,
                distance_m=row.total_distance_m,
                duration_min=row.duration_min,
                score=row.total_score,
            ),
            stops=[
                dto.StopOut(
                    position=s.position,
                    role=s.role,
                    place=place_brief(s.place),
                    arrive_at=self._out_time(s.arrive_at),
                    leave_at=self._out_time(s.leave_at),
                    est_price=s.est_price,
                    from_prev=dto.FromPrev(
                        travel_min=s.travel_min_from_prev,
                        distance_m=s.distance_m_from_prev,
                        mode=row.transport,
                    ),
                    score=s.score,
                    score_breakdown=s.score_breakdown,
                    reason=reasons.get(s.position),
                    congestion=(
                        dto.Congestion(
                            level=self._narrative.congestion_level(s.congestion), value=round(s.congestion, 2)
                        )
                        if s.congestion is not None
                        else None
                    ),
                )
                for s in stops
            ],
            route=dto.RouteOut(
                polyline=encode_polyline([origin, *(s.place.point for s in stops)]), optimizer=row.optimizer
            ),
            warnings=[dto.Warning.model_validate(w) for w in row.warnings or []],
        )

    def _out_time(self, value: datetime) -> datetime:
        utc = as_utc(value)
        assert utc is not None
        return utc.astimezone(self._tz)

    async def _load(self, public_id: str) -> tuple[Course, list[StopResult], GeoPoint]:
        row = await self._courses.get_by_public_id(public_id)
        if row is None:
            raise errors.CourseNotFound()
        places = await self._places.candidates_by_ids([s.place_id for s in row.stops if s.place_id])
        events = await self._places.event_candidates_by_ids([s.event_id for s in row.stops if s.event_id])
        stops: list[StopResult] = []
        for s in row.stops:
            cand = places.get(s.place_id or -1) or events.get(s.event_id or -1)
            if cand is None:  # the place was deleted after the course was generated
                continue
            stops.append(
                StopResult(
                    position=s.position,
                    role=s.course_role,
                    place=cand,
                    arrive_at=self._out_time(s.arrive_at),
                    leave_at=self._out_time(s.leave_at),
                    est_price=s.est_price,
                    travel_min_from_prev=s.travel_min_from_prev,
                    distance_m_from_prev=s.distance_m_from_prev,
                    score=s.score,
                    score_breakdown=dict(s.score_breakdown or {}),
                    congestion=s.congestion,
                    slot_budget=float((s.slot or {}).get("budget", 0.0)),
                    slot=_slot_from_snapshot(s.slot or {}, s.position, s.course_role),
                    slot_share=float((s.slot or {}).get("share", 0.0)),
                    slot_base_budget=float((s.slot or {}).get("budget", 0.0)),
                )
            )
        return row, stops, GeoPoint(row.origin_lat, row.origin_lng)

    async def get(self, public_id: str, viewer: User | None = None) -> dto.CourseDetailResponse:
        row, stops, origin = await self._load(public_id)
        is_owner = viewer is not None and row.user_id == viewer.id
        names = " → ".join(s.place.name for s in stops)
        purpose = await self._s.get(Purpose, row.purpose_id)
        assert purpose is not None
        region = await self._s.get(Region, row.region_id) if row.region_id else None
        snapshot = row.request or {}
        prefs = snapshot.get("preferences") or {}
        # planned around a station / place rather than the district centre → a reroll must send the point back
        around_point = region is None or (
            abs(origin.lat - region.center_lat) > 1e-6 or abs(origin.lng - region.center_lng) > 1e-6
        )
        events = await self._places.events_near(
            origin, (region.radius_m if region else 1200) * 1.5, self._out_time(row.start_at).date()
        )
        return dto.CourseDetailResponse(
            course=self._view(row, stops, origin),
            request=dto.CourseRequestEcho(
                region=dto.SlugName(slug=region.slug, name=region.name) if region else None,
                origin=LatLng(lat=origin.lat, lng=origin.lng) if around_point else None,
                origin_label=snapshot.get("origin_label") if around_point else None,
                preferences=dto.EchoPreferences(
                    liked_tags=list(prefs.get("liked_tags") or []),
                    disliked_tags=list(prefs.get("disliked_tags") or []),
                ),
                purpose=dto.CodeName(code=purpose.code, name=purpose.name),
                party_size=row.party_size,
                budget_total=row.budget_total,
                transport=row.transport,
                start_at=self._out_time(row.start_at),
                duration_min=(row.request or {}).get("duration_min"),
                style=(row.request or {}).get("style") or DEFAULT_STYLE,
            ),
            siblings=[
                dto.SiblingRef(id=c.public_id, label=c.label) for c in await self._courses.siblings(row)
            ],
            og=dto.OgMeta(
                title=f"내가짠데이 | {row.summary or row.label}",
                description=names,
                url=f"{self._settings.web_base_url.rstrip('/')}/course/{row.public_id}",
                image=next((s.place.thumbnail_url for s in stops if s.place.thumbnail_url), None),
            ),
            # same rule as `generate`: without this a reload or a shared link never showed any event
            nearby_events=[
                dto.NearbyEvent(
                    id=e.public_id,
                    title=e.title,
                    starts_on=e.starts_on,
                    ends_on=e.ends_on,
                    distance_m=round(dist),
                    is_free=e.is_free,
                )
                for e, dist in events[:5]
            ],
            is_owner=is_owner,
            can_edit=self._can_edit(row, viewer),
            is_saved=is_owner and row.status in OWNED_STATUSES,
        )

    # --- re-planning (swap / reorder) --------------------------------------------------------

    async def _replan_tools(
        self, row: Course, user: User | None
    ) -> tuple[RequestContext, ScoringProfile, CourseComposer]:
        purpose = await self._s.get(Purpose, row.purpose_id)
        assert purpose is not None
        profile = await self._config.scoring_profile(purpose.id, purpose.code)
        start_at = self._out_time(row.start_at)
        region = await self._s.get(Region, row.region_id) if row.region_id else None
        ctx = await self._build_context(
            origin=GeoPoint(row.origin_lat, row.origin_lng),
            radius_m=region.radius_m if region else 1200,
            region_id=row.region_id,
            purpose=purpose,
            party_size=row.party_size,
            budget_total=row.budget_total,
            start_at=start_at,
            transport=row.transport,
            duration_min=None,
            include_roles=None,
            preferences=(row.request or {}).get("preferences") or {},
            alternatives=0,
            user=user,
        )
        profile, _ = self._apply_style(ctx, profile, [], (row.request or {}).get("style"))
        stay_scale = float((row.request or {}).get("stay_scale", 1.0))
        return ctx, profile, CourseComposer(PlaceScorer(profile, ctx), ctx, stay_scale=stay_scale)

    @staticmethod
    def _apply_style(
        ctx: RequestContext, profile: ScoringProfile, templates: Sequence[Template], name: str | None
    ) -> tuple[ScoringProfile, list[Template]]:
        """Twists the purpose profile, its tag affinities and its templates by the requested style."""
        ctx.style, style = resolve_style(profile, name)
        ctx.purpose_tag_affinity = styled_affinity(ctx.purpose_tag_affinity, style)
        ctx.avoid_tags_by_role = styled_avoidance(style)
        return styled_profile(profile, style), styled_templates(templates, style)

    async def _finish_replan(
        self,
        row: Course,
        partial: Partial,
        ctx: RequestContext,
        profile: ScoringProfile,
        extra_warnings: list[dict[str, Any]],
    ) -> dto.CourseOut:
        keep = [w for w in row.warnings or [] if w.get("code") == "SLOT_EMPTY"]
        result = build_course(
            row.label, partial, row.template_id or 0, ctx, profile, row.optimizer or "manual", keep
        )
        result.warnings.extend(extra_warnings)
        narrative = await self._narrative.generate(
            result,
            party_size=row.party_size,
            budget_total=row.budget_total,
            transport=row.transport,
            use_llm=False,
            tag_affinity=ctx.purpose_tag_affinity,
        )
        self._apply(row, result, narrative)
        await self._s.commit()
        return self._view(row, result.stops, ctx.origin)

    async def swap(self, public_id: str, req: dto.SwapRequest, user: User | None) -> dto.CourseOut:
        row, stops, origin = await self._load(public_id)
        self._check_owner(row, user)
        target = next((s for s in stops if s.position == req.position), None)
        if target is None or target.slot is None:
            raise errors.ValidationFailed(f"{req.position}번째 장소가 없어요.")
        ctx, profile, composer = await self._replan_tools(row, user)
        ctx.exclude_place_ids |= {s.place.id for s in stops if not s.place.is_event}
        sb = SlotBudget(target.slot, target.slot_share, target.slot_base_budget)
        region = await self._s.get(Region, row.region_id) if row.region_id else None
        radius = (region.radius_m if region else 1200) * profile.params.radius_expand_factor
        pool = await self._places.fetch(target.role, origin, radius, ctx.start_at.date())
        fc = FilterContext.build(ctx, target.role, max(sb.budget, target.slot_budget), target.arrive_at)
        pool = [p for p in hard_filter(pool, fc, profile.params) if p.public_id != target.place.public_id]

        options: list[tuple[PlaceCandidate, Partial]] = []
        for cand in pool:
            sequence = [
                (
                    cand if s.position == req.position else s.place,
                    SlotBudget(s.slot, s.slot_share, s.slot_base_budget),
                )
                for s in stops
                if s.slot is not None
            ]
            partial = composer.replan(sequence, strict=True)
            if partial is not None:
                options.append((cand, partial))
        b = ctx.budget_per_person

        def j(item: tuple[PlaceCandidate, Partial]) -> float:
            return objective(item[1], b, profile.params, final=True)

        current = target.place
        if req.strategy == "cheaper":
            options = [o for o in options if o[0].price < current.price]
            options.sort(key=lambda o: -j(o))
        elif req.strategy == "closer":
            options.sort(key=lambda o: (o[1].travel_min, -j(o)))
            options = [o for o in options if o[1].travel_min <= row.total_travel_min] or options
        elif req.strategy == "higher_rated":
            if any(o[0].bayes_rating is not None for o in options):
                base = current.bayes_rating or 0.0
                options = [o for o in options if (o[0].bayes_rating or 0.0) > base]
                options.sort(key=lambda o: -(o[0].bayes_rating or 0.0))
            else:
                # Public bulk data carries no ratings: until our own feedback accumulates there is
                # nothing to compare, so give the best overall alternative instead of a dead end.
                options.sort(key=lambda o: -j(o))
        else:
            options.sort(key=lambda o: -j(o))
            options = random.sample(options[:RANDOM_TOP_N], k=min(len(options), RANDOM_TOP_N))
        if not options:
            raise errors.SwapNotPossible("조건에 맞는 다른 장소가 없어요. 다른 방식으로 바꿔 볼까요?")
        out = await self._finish_replan(row, options[0][1], ctx, profile, [])
        await self._tracker.track(
            AnalyticsEvent(
                "stop_swapped", user.public_id if user else row.public_id, {"strategy": req.strategy}
            )
        )
        return out

    async def reorder(self, public_id: str, req: dto.ReorderRequest, user: User | None) -> dto.CourseOut:
        row, stops, _origin = await self._load(public_id)
        self._check_owner(row, user)
        by_pos = {s.position: s for s in stops}
        if sorted(req.order) != sorted(by_pos):
            raise errors.ValidationFailed("order 에는 현재 코스의 모든 position 이 한 번씩 들어가야 해요.")
        ctx, profile, composer = await self._replan_tools(row, user)
        sequence = [
            (by_pos[p].place, SlotBudget(by_pos[p].slot, by_pos[p].slot_share, by_pos[p].slot_base_budget))  # type: ignore[arg-type]
            for p in req.order
        ]
        partial = composer.replan(sequence, strict=False)
        assert partial is not None
        warnings = [
            {
                "code": "STOP_CLOSED",
                "detail": f"{ps.place.name}은(는) 도착 시각에 영업하지 않을 수 있어요.",
                "meta": {"position": i + 1},
            }
            for i, ps in enumerate(partial.stops)
            if not is_open(ps.place.opening_hours, ps.arrive, 30)
        ]
        row.optimizer = "manual"
        return await self._finish_replan(row, partial, ctx, profile, warnings)

    # --- ownership / saved courses -----------------------------------------------------------

    @staticmethod
    def _can_edit(row: Course, user: User | None) -> bool:
        """An ownerless (anonymously generated) course is open to anyone; an owned one to its owner only."""
        return row.user_id is None or (user is not None and user.id == row.user_id)

    @classmethod
    def _check_owner(cls, row: Course, user: User | None) -> None:
        if not cls._can_edit(row, user):
            raise errors.Forbidden("다른 사람의 코스는 수정할 수 없어요.")

    async def save(self, public_id: str, user: User) -> dto.CourseOut:
        row, stops, origin = await self._load(public_id)
        self._check_owner(row, user)
        row.user_id, row.status = user.id, "saved"
        for s in stops:
            if not s.place.is_event:
                await self._bump_saved(s.place.id)
        await self._s.commit()
        await self._tracker.track(
            AnalyticsEvent("course_saved", user.public_id, {"course_id": row.public_id})
        )
        return self._view(row, stops, origin)

    async def _bump_saved(self, place_id: int) -> None:
        from sqlalchemy import update

        from app.infra.db.models import PlaceStats

        await self._s.execute(
            update(PlaceStats)
            .where(PlaceStats.place_id == place_id)
            .values(save_count=PlaceStats.save_count + 1)
        )

    async def list_mine(self, user: User, cursor: str | None, limit: int) -> dto.CourseListResponse:
        rows = await self._courses.list_for_user(user.id, decode_cursor(cursor), limit + 1)
        page, more = rows[:limit], len(rows) > limit
        places, events, regions, purposes = await self._list_names(page)
        return dto.CourseListResponse(
            items=[
                dto.CourseListItem(
                    id=r.public_id,
                    label=r.label,
                    summary=r.summary,
                    status=r.status,
                    total_price=r.total_price,
                    party_size=r.party_size,
                    created_at=self._out_time(r.created_at),
                    duration_min=r.duration_min,
                    region_name=regions.get(r.region_id or -1),
                    purpose_name=purposes.get(r.purpose_id),
                    stop_names=[
                        name
                        for s in r.stops
                        if (name := places.get(s.place_id or -1) or events.get(s.event_id or -1))
                    ],
                )
                for r in page
            ],
            next_cursor=encode_cursor(page[-1].id) if more and page else None,
        )

    async def _list_names(
        self, page: Sequence[Course]
    ) -> tuple[dict[int, str], dict[int, str], dict[int, str], dict[int, str]]:
        """Display names for a page of saved courses: one query per table for the whole page (no N+1).

        Returns `(place names, event titles, region names, purpose names)`, each keyed by primary key.
        """
        from sqlalchemy import select

        from app.infra.db.models import Event, Place

        async def lookup(id_col: Any, name_col: Any, ids: set[int]) -> dict[int, str]:
            if not ids:
                return {}
            rows = await self._s.execute(select(id_col, name_col).where(id_col.in_(ids)))
            return {int(row[0]): str(row[1]) for row in rows.all()}

        stops = [s for r in page for s in r.stops]
        return (
            await lookup(Place.id, Place.name, {s.place_id for s in stops if s.place_id}),
            await lookup(Event.id, Event.title, {s.event_id for s in stops if s.event_id}),
            await lookup(Region.id, Region.name, {r.region_id for r in page if r.region_id}),
            await lookup(Purpose.id, Purpose.name, {r.purpose_id for r in page}),
        )

    async def delete_mine(self, public_id: str, user: User) -> None:
        row = await self._courses.get_by_public_id(public_id)
        if row is None or row.user_id != user.id:
            raise errors.CourseNotFound()
        await self._courses.delete(row)
        await self._s.commit()

    async def feedback(self, public_id: str, req: dto.FeedbackRequest, user: User) -> None:
        row, stops, _ = await self._load(public_id)
        await self._courses.add_feedback(
            CourseFeedback(
                course_id=row.id,
                user_id=user.id,
                rating=req.rating,
                visited=req.visited,
                actual_spend=req.actual_spend,
                comment=req.comment,
                stop_feedback=[f.model_dump() for f in req.stop_feedback],
            )
        )
        if req.visited:
            row.status = "completed"
        # preference learning: EMA (alpha = 0.2) over category weights of liked / disliked stops
        pref = await self._users.ensure_preference(user.id)
        weights = dict(pref.category_weights or {})
        by_pos = {s.position: s for s in stops}
        for f in req.stop_feedback:
            if (stop := by_pos.get(f.position)) is None:
                continue
            code, signal = stop.place.category_code, 1.0 if f.liked else -1.0
            weights[code] = round(
                (1 - PREFERENCE_EMA_ALPHA) * weights.get(code, 0.0) + PREFERENCE_EMA_ALPHA * signal, 4
            )
        pref.category_weights = weights
        await self._s.commit()

    # --- narrative stream --------------------------------------------------------------------

    async def narrative_stream(self, public_id: str) -> AsyncIterator[str]:
        row, stops, _ = await self._load(public_id)
        result = CourseResult(
            label=row.label,
            template_id=row.template_id or 0,
            stops=stops,
            total_price=row.total_price,
            total_travel_min=row.total_travel_min,
            total_distance_m=row.total_distance_m,
            duration_min=row.duration_min,
            score=row.total_score,
            objective=0.0,
            optimizer=row.optimizer or "",
        )
        facts = self._narrative.facts(
            result, party_size=row.party_size, budget_total=row.budget_total, transport=row.transport
        )
        fallback = row.narrative or row.summary or ""

        async def gen() -> AsyncIterator[str]:
            async for token in self._narrative.stream(facts, fallback):
                yield token

        return gen()


def _slot_snapshot(s: StopResult) -> dict[str, Any]:
    slot = s.slot
    return {
        "position": slot.position if slot else s.position,
        "share": s.slot_share,
        "budget": s.slot_base_budget,
        "is_optional": bool(slot and slot.is_optional),
        "is_order_flexible": bool(slot and slot.is_order_flexible),
        "earliest_start_min": slot.earliest_start_min if slot else None,
        "latest_start_min": slot.latest_start_min if slot else None,
    }


def _slot_from_snapshot(raw: dict[str, Any], position: int, role: str) -> Slot:
    return Slot(
        position=int(raw.get("position", position)),
        course_role=role,
        budget_share=float(raw.get("share", 0.0)),
        is_optional=bool(raw.get("is_optional")),
        is_order_flexible=bool(raw.get("is_order_flexible")),
        earliest_start_min=raw.get("earliest_start_min"),
        latest_start_min=raw.get("latest_start_min"),
    )


def place_brief(p: PlaceCandidate) -> dto.PlaceBrief:
    return dto.PlaceBrief(
        id=p.public_id,
        kind="event" if p.is_event else "place",
        name=get_tag_rules().sign_name(p.name),
        category=p.category_code,
        category_name=p.category_name,
        lat=p.lat,
        lng=p.lng,
        address=p.address,
        thumbnail_url=p.thumbnail_url,
        rating=p.rating_avg,
        review_count=p.rating_count,
        price_per_person=None if p.is_free else p.price_per_person,
        price_is_estimated=p.price_is_estimated,
        is_free=p.is_free,
        # scoring-only tags (e.g. "체인점") are not shown on the card
        tags=sorted(get_tag_rules().visible(p.tags), key=lambda t: -p.tags[t])[:4],
    )
