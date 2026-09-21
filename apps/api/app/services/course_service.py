"""Course use-cases: generate, read, swap, reorder, save, feedback, narrative stream."""

from __future__ import annotations

import hashlib
import json
import random
import time
import uuid
from collections.abc import AsyncIterator, Sequence
from dataclasses import asdict, replace
from datetime import datetime, timedelta
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
from app.domain.recommendation.blend import (
    blend_affinity,
    blend_profiles,
    blend_rules,
    vetoed_roles,
    without_roles,
)
from app.domain.recommendation.budget import SlotBudget, is_night
from app.domain.recommendation.candidates import FilterContext, area_names_of, hard_filter
from app.domain.recommendation.composer import CourseComposer, Partial, objective
from app.domain.recommendation.engine import RecommendationEngine, build_course
from app.domain.recommendation.features import is_open
from app.domain.recommendation.itinerary import (
    Area,
    Hop,
    areas_by_day,
    cluster_areas,
    day_budget,
    day_weights,
    hop_between,
    itinerary_rules,
    leg_budget,
    leg_minutes,
    merge_legs,
    regions_by_day,
)
from app.domain.recommendation.scorer import PlaceScorer
from app.domain.recommendation.style import (
    DEFAULT_STYLE,
    carries,
    day_conditions,
    extra_roles,
    extra_unavailable,
    night_notice,
    opt_in_categories,
    resolve_style,
    styled_affinity,
    styled_avoidance,
    styled_profile,
    styled_templates,
    suggestion_rules,
    with_role,
)
from app.domain.routing.travel_time import TravelTimeProvider, encode_polyline, haversine_m
from app.domain.signature import get_signature_rules
from app.infra.analytics.base import AnalyticsEvent, EventTracker
from app.infra.db.base import as_utc
from app.infra.db.models import Course, CourseFeedback, CourseStop, Purpose, RecommendationLog, Region, User
from app.infra.tagging import get_tag_rules
from app.repositories.config_repo import SqlConfigRepository
from app.repositories.course_repo import OWNED_STATUSES, REPLACED, SqlCourseRepository
from app.repositories.place_repo import SqlPlaceRepository
from app.repositories.region_repo import SqlRegionRepository
from app.repositories.user_repo import SqlUserRepository
from app.schemas import course as dto
from app.schemas.common import LatLng, decode_cursor, encode_cursor
from app.schemas.meta import LocalSignature
from app.services import signature_service
from app.services.meta_service import local_signature_out
from app.services.narrative_service import Narrative, NarrativeService

logger = get_logger(__name__)

COURSE_CACHE_TTL_S = 300
IDEMPOTENCY_TTL_S = 86_400
RANDOM_TOP_N = 5
PREFERENCE_EMA_ALPHA = 0.2


FOCUS_OFF = "-"  # request.focus value meaning "do not build the course around a local specialty"


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
        days = await self._city_days(req)
        if req.nights > 0:
            planned = await self._plan_trip(req, user, days)
        else:
            planned = await self._plan_day(req, user, days[0] if days else None)
        await self._note_missing_extras(req, planned[3], planned[5])
        return planned

    async def _city_days(self, req: dto.CourseGenerateRequest) -> list[list[Area]]:
        """A province or a whole city as the destination: not the area around its centre point, but the
        clusters of sights people really go to (measured navigation ranks), a few per day.
        Empty = an ordinary neighbourhood request, or a city we have no visit data for."""
        city = itinerary_rules().get("city") or {}
        if not city or not req.region or len(req.regions) >= 2 or req.origin is not None:
            return []
        region = await self._regions.get_by_slug(req.region)
        if region is None or region.level > int(city["from_level"]):
            return []
        found = await self._places.popular_sights(
            await self._regions.ids_under(region.id),
            [str(r) for r in city["roles"]],
            float(city["min_popularity"]),
            int(city["sights"]),
        )
        by_class: dict[str, float] = {str(k): float(v) for k, v in (city.get("class_weight") or {}).items()}

        def draw(code: str) -> float:  # how much a kind of place pulls a traveller; most specific code wins
            parts = code.split(".")
            return next(
                (by_class[k] for n in range(len(parts), 0, -1) if (k := ".".join(parts[:n])) in by_class), 1.0
            )

        sights = [(pid, name, point, pop * draw(code)) for pid, name, point, pop, code in found]
        days = req.nights + 1
        per_day = int(city["areas_per_day"].get(req.transport, 1))
        # twice as many areas as the trip can hold: a day picks its neighbours from what is left
        areas = cluster_areas(sights, float(city["cluster_radius_m"]), days * per_day * 2)
        span_m = float((city.get("day_span_m") or {}).get(req.transport, float("inf")))
        return areas_by_day(areas, days, per_day, span_m) if areas else []

    async def _plan_day(
        self, req: dto.CourseGenerateRequest, user: User | None, areas: Sequence[Area] | None = None
    ) -> tuple[Region, GeoPoint, Purpose, RequestContext, ScoringProfile, EngineOutput]:
        if areas:
            planned = await self._plan_across(req, user, areas)
        elif len(req.regions) >= 2:
            planned = await self._plan_across(req, user)
        else:
            planned = await self._plan_one(req, user)
        night = day_conditions().get("night")
        if night and is_night(self._local(req.start_at)):
            notice, out = night_notice(night), planned[5]
            out.warnings.append(notice)
            for course in out.courses:
                if notice not in course.warnings:
                    course.warnings.append(notice)
        return planned

    async def _note_missing_extras(
        self, req: dto.CourseGenerateRequest, ctx: RequestContext, out: EngineOutput
    ) -> None:
        """ "A drink, please" and no bar in the course: the page must say so. On a trip one day is enough."""
        asked = {name: extra_roles()[name] for name in dict.fromkeys(req.extras) if name in extra_roles()}
        if not asked:
            return
        vetoed = vetoed_roles([p.code for p in await self._purposes(req)])
        for name, extra in asked.items():
            held = [carries(course, extra) for course in out.courses]
            if ctx.days and any(held):
                continue
            warning = extra_unavailable(name, extra, vetoed=str(extra["role"]) in vetoed)
            out.warnings.append(warning)
            for course, has_it in zip(out.courses, held, strict=True):
                if not has_it:
                    course.warnings.append(warning)

    async def _plan_trip(
        self,
        req: dto.CourseGenerateRequest,
        user: User | None,
        city_days: Sequence[Sequence[Area]] = (),
    ) -> tuple[Region, GeoPoint, Purpose, RequestContext, ScoringProfile, EngineOutput]:
        """Several days: one course a day. The budget follows the time each day has, what a day leaves
        goes to the next, and nowhere is visited twice. Lodging is not in the budget (no official
        prices exist); the page lists places to stay near where each day ends."""
        rules = itinerary_rules()
        days = min(req.nights, int(rules["max_nights"])) + 1
        start = self._local(req.start_at)
        weights = day_weights(start.hour * 60 + start.minute, days, rules)
        chosen = list(dict.fromkeys(req.regions)) or ([req.region] if req.region else [])
        by_day = regions_by_day(chosen, days)
        remaining = req.budget_total
        excluded = list(req.preferences.exclude_place_ids)
        first: tuple[Region, GeoPoint, Purpose, RequestContext, ScoringProfile, EngineOutput] | None = None
        courses: list[CourseResult] = []
        meta: dict[str, dict[str, Any]] = {}
        candidates = 0
        for d in range(days):
            day_start = start
            if d > 0:
                midnight = (start + timedelta(days=d)).replace(hour=0, minute=0, second=0, microsecond=0)
                day_start = midnight + timedelta(minutes=int(rules["day_start_min"]))
            slugs = by_day[d]
            budget = day_budget(remaining, weights, d, rules)
            day_req = req.model_copy(
                update={
                    "nights": 0,
                    "region": slugs[0] if slugs else req.region,
                    "regions": slugs if len(slugs) >= 2 else [],
                    "budget_total": budget,
                    "start_at": day_start,
                    "duration_min": req.duration_min if d == 0 else int(rules["full_day_min"]),
                    "alternatives": 0,
                    "preferences": req.preferences.model_copy(update={"exclude_place_ids": excluded}),
                }
            )
            planned = await self._plan_day(day_req, user, city_days[d] if d < len(city_days) else None)
            region, origin, _purpose, ctx, _profile, out = planned
            first = first or planned
            label = f"{d + 1}일차"
            course = replace(out.courses[0], label=label)
            courses.append(course)
            candidates += out.candidates_count
            meta[label] = {
                "day": d + 1,
                "days": days,
                "region_id": region.id,
                "origin": (origin.lat, origin.lng),
                "budget_total": budget,
                "start_at": day_start,
                "duration_min": day_req.duration_min,
                "segments": ctx.segments,
                "focus": ctx.focus,
            }
            remaining = max(0, remaining - course.total_price)
            excluded += [s.place.public_id for s in course.stops if not s.place.is_event]
        assert first is not None
        region, origin, purpose, ctx, profile, out = first
        ctx.days = meta
        warnings = [w for c in courses for w in c.warnings]
        return (
            region,
            origin,
            purpose,
            ctx,
            profile,
            replace(out, courses=courses, candidates_count=candidates, warnings=warnings),
        )

    async def _plan_across(
        self, req: dto.CourseGenerateRequest, user: User | None, areas: Sequence[Area] | None = None
    ) -> tuple[Region, GeoPoint, Purpose, RequestContext, ScoringProfile, EngineOutput]:
        """One day across several neighbourhoods: each is planned as a leg of its own, and money and
        time are handed forward (see `domain.recommendation.itinerary`)."""
        rules = itinerary_rules()
        slugs = list(dict.fromkeys(req.regions))[: int(rules["max_regions"])]
        city = rules.get("city") or {}
        # where each leg happens: a neighbourhood (by slug) or, for a whole-city trip, a well-visited area
        spots: list[dict[str, Any]] = (
            [
                {
                    "region": None,
                    "origin": LatLng(lat=a.point.lat, lng=a.point.lng),
                    "origin_label": a.name,
                    "name": f"{a.name}{city.get('label_suffix', '')}",
                }
                for a in areas
            ]
            if areas
            else [{"region": slug, "origin": None, "origin_label": None, "name": None} for slug in slugs]
        )
        remaining = req.budget_total
        minutes_left = req.duration_min
        start_at = self._local(req.start_at)
        excluded = list(req.preferences.exclude_place_ids)
        legs: list[CourseResult] = []
        hops: list[Hop] = []
        segments: list[dict[str, Any]] = []
        repeat: list[str] = []
        first: tuple[Region, GeoPoint, Purpose, RequestContext, ScoringProfile, EngineOutput] | None = None
        candidates = 0
        for k, spot in enumerate(spots):
            left = len(spots) - k
            leg_req = req.model_copy(
                update={
                    "region": spot["region"],
                    "regions": [],
                    "origin": spot["origin"],
                    "origin_label": spot["origin_label"],
                    "budget_total": leg_budget(remaining, left, rules),
                    "start_at": start_at,
                    "duration_min": leg_minutes(minutes_left, left, rules),
                    "alternatives": 0,
                    "preferences": req.preferences.model_copy(update={"exclude_place_ids": excluded}),
                    # two karaoke rooms in a row because the neighbourhood changed is not a plan
                    "skip_roles": [*req.skip_roles, *repeat],
                }
            )
            pinned = areas[k].place_ids[: int(city.get("pin_top", 3))] if areas else ()
            planned = await self._plan_one(leg_req, user, pinned)
            region, leg_origin, _purpose, _ctx, _profile, out = planned
            first = first or planned
            course = out.courses[0]
            candidates += out.candidates_count
            position = sum(len(leg.stops) for leg in legs) + 1
            segments.append(
                {
                    "slug": region.slug,
                    "name": spot["name"] or region.name,
                    "lat": leg_origin.lat,
                    "lng": leg_origin.lng,
                    "radius_m": int(city.get("area_radius_m", region.radius_m)) if areas else region.radius_m,
                    "from_position": position,
                    "to_position": position + len(course.stops) - 1,
                    "hop": asdict(hops[-1]) if hops else None,
                    "area": bool(areas),  # a well-visited area of a whole-city trip, not a neighbourhood
                }
            )
            legs.append(course)
            closing = course.stops[-1].role
            repeat = [closing] if closing in rules["no_repeat_roles"] else []
            remaining = max(0, remaining - course.total_price)
            excluded += [s.place.public_id for s in course.stops if not s.place.is_event]
            if k + 1 < len(spots):
                if areas:
                    ahead = areas[k + 1].point
                else:
                    nxt = await self._regions.get_by_slug(slugs[k + 1])
                    if nxt is None:
                        raise errors.RegionNotFound(f"'{slugs[k + 1]}' 지역은 아직 없어요.")
                    ahead = GeoPoint(nxt.center_lat, nxt.center_lng)
                last = course.stops[-1]
                hop = hop_between(last.place.point, ahead, req.transport, rules)
                hops.append(hop)
                start_at = last.leave_at + timedelta(minutes=hop.minutes)
                if minutes_left is not None:
                    spent = int((start_at - self._local(req.start_at)).total_seconds() // 60)
                    minutes_left = max(0, req.duration_min - spent) if req.duration_min else None
        assert first is not None
        region, origin, purpose, ctx, profile, out = first
        merged, _hop_at = merge_legs(legs, hops)
        ctx.segments = segments
        ctx.budget_total = req.budget_total
        ctx.duration_min = req.duration_min
        merged_out = replace(
            out, courses=[merged], candidates_count=candidates, warnings=list(merged.warnings)
        )
        return region, origin, purpose, ctx, profile, merged_out

    async def _plan_one(
        self, req: dto.CourseGenerateRequest, user: User | None, must_visit: Sequence[int] = ()
    ) -> tuple[Region, GeoPoint, Purpose, RequestContext, ScoringProfile, EngineOutput]:
        region, origin = await self._resolve_region(req)
        purposes = await self._purposes(req)
        purpose = purposes[0]  # the first one gives the day its shape; all of them weigh in below
        profile = blend_profiles([await self._config.scoring_profile(p.id, p.code) for p in purposes])
        vetoed = vetoed_roles([p.code for p in purposes])
        vetoed |= frozenset(r.upper() for r in req.skip_roles)
        templates = without_roles(await self._config.templates_for(purpose.id, purpose.code), vetoed)
        conditions = self._conditions(req)
        reach = max(
            [
                float((day_conditions()[c].get("radius_mult") or {}).get(req.transport, 1.0))
                for c in conditions
            ],
            default=1.0,
        )
        ctx = await self._build_context(
            origin=origin,
            radius_m=int(region.radius_m * reach),
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
        ctx.wanted_place_ids = frozenset(must_visit)
        if must_visit:  # a leg of a whole-city trip: the sight is the point, however short the leg
            ctx.keep_roles = frozenset(str(r) for r in (itinerary_rules().get("city") or {}).get("roles", []))
        ctx.purpose_tag_affinity = blend_affinity([await self._config.tag_affinity(p.id) for p in purposes])
        ctx.purpose_codes = tuple(p.code for p in purposes)
        asked = {str(extra_roles()[r].get("category")) for r in req.extras if r in extra_roles()}
        ctx.blocked_categories = opt_in_categories() - asked
        rules = get_signature_rules()
        signature = (await signature_service.load(self._s, region.id)).strong(rules.auto_focus_min_strength)
        ctx.local_words = tuple(s.word for s in signature.specialties)
        ctx.landmark_ids = frozenset(s.place_id for s in signature.sights)
        ctx.focus_request = req.focus if req.focus in ctx.local_words else None  # only what it is known for
        if req.focus != FOCUS_OFF:  # "상관없어요": the user asked for a plain course
            ctx.auto_focus_words = ctx.local_words
        profile, templates = self._apply_style(ctx, profile, templates, req.style)
        for name in conditions:  # a rainy day: indoors, and a gallery instead of a walk
            condition = day_conditions()[name]
            ctx.purpose_tag_affinity = styled_affinity(ctx.purpose_tag_affinity, condition)
            for tag, roles in styled_avoidance(condition).items():
                ctx.avoid_tags_by_role[tag] = ctx.avoid_tags_by_role.get(tag, frozenset()) | roles
            templates = styled_templates(templates, condition)
        for role in req.extras:  # "술 한잔 포함": the slot is there for certain, whatever the template
            entry = extra_roles().get(role)
            if entry is not None and entry["role"] not in vetoed:
                templates = with_role(templates, entry)
                if entry.get("category"):
                    ctx.wanted_categories = (*ctx.wanted_categories, str(entry["category"]))
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

    async def _day_to_replace(self, req: dto.CourseGenerateRequest, user: User | None) -> Course | None:
        """`replaces` names one day of a trip. Anything else (an ordinary course) is an ordinary reroll."""
        if not req.replaces:
            return None
        row = await self._courses.get_by_public_id(req.replaces)
        if row is None or int((row.request or {}).get("days") or 1) < 2 or row.status == REPLACED:
            return None
        self._check_owner(row, user)
        return row

    async def _as_that_day(self, req: dto.CourseGenerateRequest, day: Course) -> dto.CourseGenerateRequest:
        """One course, for that day only, and nowhere the other days already go."""
        others = [c for c in await self._courses.siblings(day) if c.id != day.id]
        visited = await self._places.candidates_by_ids(
            [s.place_id for c in others for s in c.stops if s.place_id]
        )
        excluded = [*req.preferences.exclude_place_ids, *(p.public_id for p in visited.values())]
        return req.model_copy(
            update={
                "nights": 0,
                "alternatives": 0,
                "preferences": req.preferences.model_copy(
                    update={"exclude_place_ids": list(dict.fromkeys(excluded))[:100]}
                ),
            }
        )

    @staticmethod
    def _take_the_place_of(row: Course, day: Course) -> None:
        """The new course becomes that day of the same trip; the old one steps out of the tabs."""
        before = day.request or {}
        row.recommendation_log_id = day.recommendation_log_id
        row.label = day.label
        row.request = {
            **(row.request or {}),
            **{k: before.get(k) for k in ("day", "days", "nights", "trip_budget_total")},
        }
        if day.status in OWNED_STATUSES:  # a saved trip stays saved, all of it
            row.user_id, row.status = day.user_id, day.status
        day.status = REPLACED

    def _conditions(self, req: dto.CourseGenerateRequest) -> list[str]:
        """What the user said about the day, plus what the clock says (`auto`: never from the request)."""
        known = day_conditions()
        chosen = [c for c in dict.fromkeys(req.conditions) if c in known and not known[c].get("auto")]
        if "night" in known and is_night(self._local(req.start_at)):
            chosen.append("night")
        return chosen

    async def _city_echo(self, slug: str | None) -> dto.SlugName | None:
        city = await self._regions.get_by_slug(slug) if slug else None
        return dto.SlugName(slug=city.slug, name=city.name) if city else None

    async def _purpose_names(self, codes: Sequence[str]) -> list[dto.CodeName]:
        found = [await self._config.get_purpose(code) for code in codes]
        return [dto.CodeName(code=p.code, name=p.name) for p in found if p is not None]

    async def _purposes(self, req: dto.CourseGenerateRequest) -> list[Purpose]:
        """The chosen purposes in order, first one first, each once, at most `max_purposes`."""
        codes = list(dict.fromkeys([req.purpose, *req.purposes]))[: int(blend_rules().get("max_purposes", 3))]
        found: list[Purpose] = []
        for code in codes:
            purpose = await self._config.get_purpose(code)
            if purpose is None:
                raise errors.PurposeNotFound(f"'{code}' 목적은 아직 지원하지 않아요.")
            found.append(purpose)
        return found

    async def _signature_out(self, region: Region) -> LocalSignature | None:
        """What the neighbourhood is known for. None when nothing stands out: the page says nothing then."""
        floor = get_signature_rules().auto_focus_min_strength
        signature = (await signature_service.load(self._s, region.id)).strong(floor)
        if not signature.specialties and not signature.sights:
            return None
        return local_signature_out(region.name, signature)

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

        replaced = await self._day_to_replace(req, user)
        if replaced is not None:
            req = await self._as_that_day(req, replaced)
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
            "focus": ctx.focus,
            "purposes": list(ctx.purpose_codes),
            "segments": ctx.segments,
            "extras": [r for r in req.extras if r in extra_roles()],
            "conditions": [c for c in self._conditions(req) if not day_conditions()[c].get("auto")],
            # echoed by `get()` so the result page and a reroll stay around the same station / place
            "origin_label": req.origin_label if req.origin else None,
            # a whole-city trip: planning this day again must ask for the city, not for the district the
            # first area happens to lie in
            "city": req.region
            if any(seg.get("area") for seg in ctx.segments or [])
            or any(seg.get("area") for day in (ctx.days or {}).values() for seg in day.get("segments") or [])
            else None,
        }
        rows: list[tuple[Course, CourseResult, Narrative]] = []
        for result in out.courses:
            day = ctx.days.get(result.label)  # a trip: this course is one of its days
            day_budget_total = day["budget_total"] if day else req.budget_total
            narrative = await self._narrative.generate(
                result,
                party_size=req.party_size,
                budget_total=day_budget_total,
                transport=req.transport,
                use_llm=self._settings.narrative_inline_llm,
                tag_affinity=ctx.purpose_tag_affinity,
            )
            row = Course(
                user_id=user.id if user else None,
                region_id=day["region_id"] if day else region.id,
                purpose_id=purpose.id,
                party_size=req.party_size,
                budget_total=day_budget_total,
                transport=req.transport,
                origin_lat=day["origin"][0] if day else origin.lat,
                origin_lng=day["origin"][1] if day else origin.lng,
                start_at=day["start_at"] if day else ctx.start_at,
                request=snapshot
                if not day
                else {
                    **snapshot,
                    "duration_min": day["duration_min"],
                    "segments": day["segments"],
                    "focus": day["focus"],
                    "day": day["day"],
                    "days": day["days"],
                    "nights": req.nights,
                    "trip_budget_total": req.budget_total,
                },
                recommendation_log_id=log.id,
                warnings=[],
            )
            self._apply(row, result, narrative)
            if replaced is not None:
                self._take_the_place_of(row, replaced)
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
            local=await self._signature_out(region),
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
        segments = (row.request or {}).get("segments") or []
        hops = {seg["from_position"]: seg for seg in segments if seg.get("hop")}
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
                        # the ride into the next neighbourhood is not the walk the rest of the day is
                        mode=(hops[s.position]["hop"] or {}).get("mode", row.transport)
                        if s.position in hops
                        else row.transport,
                        hop_to=hops[s.position]["name"] if s.position in hops else None,
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
                day=(row.request or {}).get("day"),
                days=(row.request or {}).get("days"),
                trip_budget_total=(row.request or {}).get("trip_budget_total"),
                city=await self._city_echo(snapshot.get("city")),
                regions=[
                    dto.SlugName(slug=seg["slug"], name=seg["name"])
                    for seg in (row.request or {}).get("segments") or []
                ],
                purposes=await self._purpose_names((row.request or {}).get("purposes") or [purpose.code]),
                party_size=row.party_size,
                budget_total=row.budget_total,
                transport=row.transport,
                start_at=self._out_time(row.start_at),
                duration_min=(row.request or {}).get("duration_min"),
                style=(row.request or {}).get("style") or DEFAULT_STYLE,
                focus=(row.request or {}).get("focus"),
                extras=list((row.request or {}).get("extras") or []),
                conditions=list((row.request or {}).get("conditions") or []),
            ),
            local=await self._signature_out(region) if region else None,
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
        # a swap must not bring in what the course was never asked to have (a ballpark on a day off)
        kept = (row.request or {}).get("extras") or []
        asked = {str(extra_roles()[r].get("category")) for r in kept if r in extra_roles()}
        ctx.blocked_categories = opt_in_categories() - asked
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
        # in a course across neighbourhoods a stop is replaced from its own neighbourhood
        for seg in (row.request or {}).get("segments") or []:
            if seg["from_position"] <= target.position <= seg["to_position"]:
                origin = ctx.origin = GeoPoint(seg["lat"], seg["lng"])
                radius = seg["radius_m"] * profile.params.radius_expand_factor
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

    async def _leftover_options(
        self, row: Course, stops: Sequence[StopResult], user: User | None
    ) -> list[tuple[str, PlaceCandidate, int, int]]:
        """(role, place, walk minutes, metres) near the last stop that the money left over can buy."""
        rules = suggestion_rules()
        if not rules or not stops:
            return []
        left = row.budget_total - row.total_price
        per_person = left / max(1, row.party_size)
        if (
            per_person < float(rules["min_left_per_person"])
            or left < float(rules["min_left_ratio"]) * row.budget_total
        ):
            return []
        ctx, profile, _composer = await self._replan_tools(row, user)
        ctx.exclude_place_ids |= {s.place.id for s in stops if not s.place.is_event}
        last = stops[-1]
        purposes = (row.request or {}).get("purposes") or []
        vetoed = vetoed_roles([str(code) for code in purposes]) | {s.role for s in stops}
        reach_m = float(rules["max_walk_min"]) * float(rules["walk_m_per_min"])
        arrive_at = last.leave_at + timedelta(minutes=5)
        minute = arrive_at.hour * 60 + arrive_at.minute
        found: list[tuple[str, PlaceCandidate, int, int]] = []
        for role, rule in rules["roles"].items():
            if role in vetoed or minute < int(rule.get("earliest_start_min", 0)):
                continue
            pool = await self._places.fetch(role, last.place.point, reach_m, arrive_at.date())
            fc = FilterContext.build(ctx, role, per_person, arrive_at)
            open_now = hard_filter(pool, fc, profile.params)  # budget, hours, dislikes: all checked here
            if not open_now:
                continue

            def worth(p: PlaceCandidate) -> tuple[float, float, float]:
                vouched = max(p.popularity, 1.0 if p.is_curated else 0.0, p.local_score)
                return (vouched, 1.0 if p.thumbnail_url else 0.0, -haversine_m(last.place.point, p.point))

            best = max(open_now, key=worth)
            metres = int(haversine_m(last.place.point, best.point) * 1.25)
            found.append((role, best, max(1, round(metres / float(rules["walk_m_per_min"]))), metres))
            if len(found) >= int(rules["limit"]):
                break
        return found

    async def suggestions(self, public_id: str, user: User | None) -> dto.SuggestionList:
        """Money left over is not a success to report and leave: it is an offer to make."""
        row, stops, _origin = await self._load(public_id)
        left = row.budget_total - row.total_price
        rules = suggestion_rules()
        items = [
            dto.Suggestion(
                role=role,
                place=place_brief(place),
                est_price=0 if place.is_free else int(place.price_per_person or 0) * row.party_size,
                walk_min=walk_min,
                distance_m=metres,
                line=str(rules["roles"][role]["line"]).format(left=f"{left:,}원"),
            )
            for role, place, walk_min, metres in await self._leftover_options(row, stops, user)
        ]
        return dto.SuggestionList(budget_left=left, items=items)

    async def add_stop(self, public_id: str, req: dto.AddStopRequest, user: User | None) -> dto.CourseOut:
        """Puts a suggested place at the end of the course. Only what `suggestions` would offer right
        now can be added, so the budget, the hours and the walk have already been checked."""
        row, stops, _origin = await self._load(public_id)
        self._check_owner(row, user)
        offered = {
            p.public_id: (role, p) for role, p, _m, _d in await self._leftover_options(row, stops, user)
        }
        if req.place_id not in offered:
            raise errors.ValidationFailed("지금은 코스에 넣을 수 없는 곳이에요. 목록을 새로 고쳐 주세요.")
        role, place = offered[req.place_id]
        ctx, profile, composer = await self._replan_tools(row, user)
        per_person = (row.budget_total - row.total_price) / max(1, row.party_size)
        slot = Slot(position=len(stops) + 1, course_role=role, budget_share=0.0, is_optional=True)
        sequence = [
            (s.place, SlotBudget(s.slot, s.slot_share, s.slot_base_budget))
            for s in stops
            if s.slot is not None
        ]
        partial = composer.replan([*sequence, (place, SlotBudget(slot, 0.0, per_person))], strict=False)
        if partial is None:
            raise errors.ValidationFailed("이 곳을 넣으면 시간이 맞지 않아요.")
        out = await self._finish_replan(row, partial, ctx, profile, [])
        await self._tracker.track(
            AnalyticsEvent("stop_added", user.public_id if user else row.public_id, {"role": role})
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
        if int((row.request or {}).get("days") or 1) > 1:
            # a trip is kept whole: a day left unsaved would be swept away by retention a few days later
            for other in await self._courses.siblings(row):
                if other.id != row.id and self._can_edit(other, user) and other.status not in OWNED_STATUSES:
                    other.user_id, other.status = user.id, "saved"
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
                    day=(r.request or {}).get("day"),
                    days=(r.request or {}).get("days"),
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
