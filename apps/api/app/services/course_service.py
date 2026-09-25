"""Course use-cases: generate, read, swap, reorder, save, feedback, narrative stream."""

from __future__ import annotations

import hashlib
import json
import random
import time
import uuid
from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import asdict, replace
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import course_key, errors
from app.core.cache import Cache
from app.core.config import Settings
from app.core.logging import get_logger
from app.domain.anchors import (
    Anchor,
    AnchoredEvent,
    campus_first,
    context_purposes,
    festival_missing_warning,
    pick_festival,
    university_rules,
)
from app.domain.anchors import plan_for as anchor_plan_for
from app.domain.media import distinct_photos
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
from app.domain.recommendation import day_score, leftover
from app.domain.recommendation.blend import (
    blend_affinity,
    blend_profiles,
    blend_rules,
    vetoed_roles,
    without_roles,
)
from app.domain.recommendation.budget import SlotBudget, evening_minute, is_night
from app.domain.recommendation.candidates import FilterContext, area_names_of, compact_name, hard_filter
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
from app.domain.recommendation.preference import (
    WISH_AVOID_ROLES,
    WISH_CONDITIONS,
    Interpreted,
    interpret,
    reweight_templates,
)
from app.domain.recommendation.scorer import PlaceScorer
from app.domain.recommendation.style import (
    DEFAULT_STYLE,
    carries,
    day_conditions,
    extra_roles,
    extra_unavailable,
    night_notice,
    one_sweet_stop,
    opt_in_categories,
    resolve_scene,
    resolve_style,
    styled_affinity,
    styled_avoidance,
    styled_never,
    styled_profile,
    styled_templates,
    suggestion_rules,
    with_kept,
    with_optional_after,
    with_role,
)
from app.domain.region_intro import editorial_intros
from app.domain.routing.travel_time import TravelTimeProvider, encode_polyline, haversine_m
from app.domain.signature import get_signature_rules
from app.infra.analytics.base import AnalyticsEvent, EventTracker
from app.infra.db.base import as_utc
from app.infra.db.models import Course, CourseFeedback, CourseStop, Purpose, RecommendationLog, Region, User
from app.infra.tagging import get_tag_rules
from app.repositories.config_repo import SqlConfigRepository
from app.repositories.course_repo import OWNED_STATUSES, REPLACED, SqlCourseRepository
from app.repositories.place_repo import CandidateReads, SqlPlaceRepository
from app.repositories.region_repo import SqlRegionRepository
from app.repositories.user_repo import SqlUserRepository
from app.schemas import course as dto
from app.schemas import route as route_dto
from app.schemas.common import LatLng, decode_cursor, encode_cursor
from app.schemas.meta import LocalSignature
from app.services import signature_service
from app.services.meta_service import local_signature_out
from app.services.narrative_service import Narrative, NarrativeService

logger = get_logger(__name__)

COURSE_CACHE_TTL_S = 300
CANDIDATES_TTL_S = 600
IDEMPOTENCY_TTL_S = 86_400
RANDOM_TOP_N = 5
CANDIDATE_LINE_MAX = 40  # the one line under a replacement option (and reason_short) fits a card subtitle
RECOMPUTED_WARNINGS = frozenset({"BUDGET_OVER", "STOP_CLOSED"})  # read off the stops: redone on every replan
PREFERENCE_EMA_ALPHA = 0.2


FOCUS_OFF = "-"  # request.focus value meaning "do not build the course around a local specialty"


DARK_BY_THE_END_H = 17  # a course starting from here on ends after dark
SCENE_CATEGORY_PULL = 0.3  # 누구와: a liked kind of place (+1) adds this much to a place score of 0..1


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
        self._reads: CandidateReads | None = None  # the candidate reads of the plan under way (see `_plan`)
        # docs/34: the anchors resolved for this request (campus id → campus + that day's festival)
        self._anchors: dict[str, dict[str, Any]] = {}
        # the stops pinned for this request (public id → place): read once, handed to every leg / day
        self._kept: dict[str, PlaceCandidate] = {}
        self._courses = SqlCourseRepository(session)
        self._users = SqlUserRepository(session)
        self._tz = ZoneInfo(settings.timezone)

    # --- generate ----------------------------------------------------------------------------

    async def _plan(
        self, req: dto.CourseGenerateRequest, user: User | None
    ) -> tuple[Region, GeoPoint, Purpose, RequestContext, ScoringProfile, EngineOutput]:
        """Everything up to and including the engine run — no cache, no rows, no tracking."""
        req = await self._with_kept(req)
        req, earlier = self._earlier_for_scene(req)
        days = await self._city_days(req)
        # one plan asks for the same candidates again and again (rescale passes, the v2 structure
        # alternative, each day of a trip): read once, per plan only
        self._reads = CandidateReads(self._places)
        try:
            if req.nights > 0:
                planned = await self._plan_trip(req, user, days)
            else:
                planned = await self._plan_day(req, user, days[0] if days else None)
        finally:
            self._reads = None
        await self._note_missing_extras(req, planned[3], planned[5])
        self._note_kept(req, planned[3], planned[5])
        if earlier is not None:
            for bucket in (planned[5].warnings, *(c.warnings for c in planned[5].courses)):
                bucket.insert(0, earlier)
        return planned

    def _earlier_for_scene(
        self, req: dto.CourseGenerateRequest
    ) -> tuple[dto.CourseGenerateRequest, dict[str, Any] | None]:
        """누구와 (docs/48): a day with children is not a night out. Asked for at night, it is planned for
        that evening instead (founder, 2026-09-25) — and the course says so."""
        _key, scene = resolve_scene(req.purpose, req.scene)
        start = self._local(req.start_at)
        if req.nights > 0 or not scene.get("earlier_start") or not is_night(start):
            return req, None
        hh, mm = (int(x) for x in str(scene["earlier_start"]).split(":"))
        moved = start.replace(hour=hh, minute=mm, second=0, microsecond=0)
        label = f"{hh}시" + (f" {mm}분" if mm else "")
        notice = {
            "code": "SCENE_EARLIER",
            "detail": str(scene.get("earlier_notice") or "").format(time=label),
            "meta": {"asked": start.isoformat(), "planned": moved.isoformat()},
        }
        return req.model_copy(update={"start_at": moved}), notice

    async def _with_kept(self, req: dto.CourseGenerateRequest) -> dto.CourseGenerateRequest:
        """The stops the user pinned (the course is a draft they edit): read them once, and a pinned place is
        never excluded — the web sends the whole old course as excluded and the pinned ones as kept."""
        keep = list(dict.fromkeys(req.keep_place_ids))
        self._kept = await self._places.candidates_by_public_ids(keep) if keep else {}
        if not keep:
            return req
        excluded = [pid for pid in req.preferences.exclude_place_ids if pid not in set(keep)]
        return req.model_copy(
            update={
                "keep_place_ids": keep,
                "preferences": req.preferences.model_copy(update={"exclude_place_ids": excluded}),
            }
        )

    def _kept_for(self, req: dto.CourseGenerateRequest) -> list[PlaceCandidate]:
        return [self._kept[pid] for pid in dict.fromkeys(req.keep_place_ids) if pid in self._kept]

    def _split_kept(self, keep: Sequence[str], points: Sequence[GeoPoint | None]) -> list[list[str]]:
        """A day across several neighbourhoods (or a trip of several days): each pinned stop goes to the leg
        whose centre is nearest, so it is planned once and where it is."""
        out: list[list[str]] = [[] for _ in points]
        known = [(i, p) for i, p in enumerate(points) if p is not None]
        if not known:
            return out
        for pid in keep:
            place = self._kept.get(pid)
            if place is None:
                continue
            nearest = min(known, key=lambda ip: haversine_m(ip[1], place.point))[0]
            out[nearest].append(pid)
        return out

    async def _region_point(self, slug: str | None) -> GeoPoint | None:
        region = await self._regions.get_by_slug(slug) if slug else None
        return GeoPoint(region.center_lat, region.center_lng) if region else None

    def _note_kept(self, req: dto.CourseGenerateRequest, ctx: RequestContext, out: EngineOutput) -> None:
        """A pinned stop the course could not hold (closed at that hour, over the budget on its own, or gone
        from our data): the page must say so, never drop it silently. On a trip one day holding it will do."""
        if not req.keep_place_ids:
            return
        everywhere = {s.place.public_id for c in out.courses for s in c.stops}
        for course in out.courses:
            held = everywhere if ctx.days else {s.place.public_id for s in course.stops}
            for pid in req.keep_place_ids:
                if pid in held:
                    continue
                warning = self._kept_dropped(pid)
                if warning not in course.warnings:
                    course.warnings.append(warning)
                if warning not in out.warnings:
                    out.warnings.append(warning)

    def _kept_dropped(self, pid: str) -> dict[str, Any]:
        place = self._kept.get(pid)
        if place is None:
            return {
                "code": "KEPT_PLACE_DROPPED",
                "detail": "고정한 장소 중 한 곳을 찾을 수 없어 빼고 짰어요.",
                "meta": {"place_id": pid, "name": None, "reason": "unknown"},
            }
        name = get_tag_rules().sign_name(place.name)
        return {
            "code": "KEPT_PLACE_DROPPED",
            "detail": f"고정한 {name}은(는) 이 시간이나 예산에 맞지 않아 빼고 짰어요.",
            "meta": {"place_id": pid, "name": name, "reason": "unfit"},
        }

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
            notices = [night_notice(night)]
            _key, scene = resolve_scene(req.purpose, req.scene)
            if scene.get("night_notice"):  # "아이와" at 22:00: planned, and told it is late for a child
                notices.append({"code": "SCENE_NIGHT", "detail": str(scene["night_notice"]), "meta": {}})
            out = planned[5]
            for notice in notices:
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
        kept_by_day: list[list[str]] = [[] for _ in range(days)]
        if req.keep_place_ids:
            here = (
                GeoPoint(req.origin.lat, req.origin.lng)
                if req.origin
                else await self._region_point(req.region)
            )
            points = [
                city_days[d][0].point
                if d < len(city_days) and city_days[d]
                else (await self._region_point(by_day[d][0]) if by_day[d] else here)
                for d in range(days)
            ]
            kept_by_day = self._split_kept(req.keep_place_ids, points)
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
                    "keep_place_ids": kept_by_day[d],
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
        kept_by_leg: list[list[str]] = [[] for _ in spots]
        if req.keep_place_ids:
            points = [a.point for a in areas] if areas else [await self._region_point(slug) for slug in slugs]
            kept_by_leg = self._split_kept(req.keep_place_ids, points)
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
                    "keep_place_ids": kept_by_leg[k],
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
        kept = self._kept_for(req)
        reach = max(
            [
                float((day_conditions()[c].get("radius_mult") or {}).get(req.transport, 1.0))
                for c in conditions
            ],
            default=1.0,
        )
        ctx = await self._build_context(
            origin=origin,
            # a wide district times four is half a province: the pool explodes and the request times out
            radius_m=min(int(region.radius_m * reach), max(region.radius_m, self._reach_cap(conditions))),
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
        # docs/29: which engine plans this course, and how far this person is happy to go for better
        ctx.algorithm = req.algorithm or self._settings.recommendation_algorithm
        ctx.move_style = req.move_style or "balanced"
        ctx.wanted_place_ids = frozenset(must_visit)
        if must_visit:  # a leg of a whole-city trip: the sight is the point, however short the leg
            ctx.keep_roles = frozenset(str(r) for r in (itinerary_rules().get("city") or {}).get("roles", []))
        ctx.purpose_tag_affinity = blend_affinity([await self._config.tag_affinity(p.id) for p in purposes])
        ctx.purpose_codes = tuple(p.code for p in purposes)
        asked = {str(extra_roles()[r].get("category")) for r in req.extras if r in extra_roles()}
        ctx.blocked_categories = (opt_in_categories() - asked) | {str(university_rules()["category"])}
        rules = get_signature_rules()
        signature = (await signature_service.load(self._s, region.id)).strong(rules.auto_focus_min_strength)
        ctx.local_words = tuple(s.word for s in signature.specialties)
        ctx.landmark_ids = frozenset(s.place_id for s in signature.sights)
        ctx.focus_request = req.focus if req.focus in ctx.local_words else None  # only what it is known for
        if req.focus != FOCUS_OFF:  # "상관없어요": the user asked for a plain course
            ctx.auto_focus_words = ctx.local_words
        # docs/30: the few answers of the wizard, read into the engine's own knobs
        understood = interpret(
            pace=req.pace,
            move_style=req.move_style,
            wishes=req.wishes,
            liked_tags=ctx.liked_tags,
            disliked_tags=ctx.disliked_tags,
        )
        profile, templates = self._apply_style(
            ctx, profile, templates, understood.style if req.pace else req.style
        )
        profile, templates = self._apply_understood(ctx, profile, templates, understood)
        ctx.scene, scene = resolve_scene(purpose.code, req.scene)
        profile, templates = self._apply_scene(ctx, profile, templates, scene)
        # "조용하게": no pub and no karaoke room, unless a drink was asked for by name
        asked_roles = {str(extra_roles()[r]["role"]) for r in req.extras if r in extra_roles()}
        templates = without_roles(templates, understood.avoid_roles - asked_roles)
        templates = one_sweet_stop(templates)  # a café and a dessert shop in a row is one sitting
        ctx.blocked_categories = ctx.blocked_categories | understood.blocked_categories
        self._apply_conditions(ctx, conditions)
        for name in conditions:  # a rainy day: indoors, and a gallery instead of a walk
            condition = day_conditions()[name]
            # a slot swap names a kind of place that must be open: at night the gallery that replaces a
            # rainy walk is closed, and the course lost the slot altogether (one-stop courses at 1:30 a.m.)
            if not (condition.get("swap_roles") and "night" in conditions and name != "night"):
                templates = styled_templates(templates, condition)
        for role in req.extras:  # "술 한잔 포함": the slot is there for certain, whatever the template
            entry = extra_roles().get(role)
            if entry is not None and entry["role"] not in vetoed:
                templates = with_role(templates, entry)
                if entry.get("category"):
                    ctx.wanted_categories = (*ctx.wanted_categories, str(entry["category"]))
        festival_missing = False
        if req.anchor is not None:  # docs/34: a campus day — the same engine, a few knobs set by the anchor
            templates, festival_missing = await self._apply_anchor(req, purpose, ctx, list(templates))
        plain_templates, plain_keep = list(templates), ctx.keep_roles
        if kept:  # the stops the user pinned: a slot of its own role each, never trimmed, never excluded
            templates = with_kept(templates, kept, ctx.budget_per_person)
            ctx.kept_places = tuple(kept)
            ctx.keep_roles = ctx.keep_roles | {p.course_role for p in kept}
            ctx.exclude_place_ids -= {p.id for p in kept if not p.is_event}
        engine = RecommendationEngine(self._reads or self._places, self._travel)
        try:
            try:
                out = await engine.generate(ctx, templates, profile)
            except BudgetTooLowError:
                raise
            except DomainError:
                if not kept:
                    raise
                # nothing fits around the pinned stops: a course without them (the page says which) beats none
                ctx.kept_places, ctx.keep_roles = (), plain_keep
                out = await engine.generate(ctx, plain_templates, profile)
            self._note_festival(req, out, festival_missing)
        except BudgetTooLowError as exc:
            raise errors.BudgetTooLow(
                f"{region.name}에서 {req.party_size}명 기준 최소 {exc.min_budget:,}원이 필요해요.",
                meta={"min_budget": exc.min_budget},
            ) from exc
        except DomainError as exc:
            raise errors.NoCourseAvailable(
                f"{region.name}에서 조건에 맞는 코스를 찾지 못했어요. 예산이나 시간을 바꿔 볼까요?"
            ) from exc
        # the engine may have moved the origin (onto a ballpark asked for, or the liveliest walkable pocket
        # of a wide district): the course starts where it was planned from
        return region, ctx.origin, purpose, ctx, profile, out

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

    @staticmethod
    def _reach_cap(conditions: Sequence[str]) -> int:
        caps = [
            int(day_conditions()[c]["radius_cap_m"])
            for c in conditions
            if day_conditions()[c].get("radius_cap_m")
        ]
        return min(caps) if caps else 10**9

    def _conditions(self, req: dto.CourseGenerateRequest, *, wishes: bool = True) -> list[str]:
        """What the user said about the day, plus what the clock says (`auto`: never from the request).
        `wishes`: a wish that stands for a condition counts too ("실내 위주" = the rainy-day plan)."""
        known = day_conditions()
        said = [*req.conditions, *(WISH_CONDITIONS[w] for w in req.wishes if wishes and w in WISH_CONDITIONS)]
        chosen = [c for c in dict.fromkeys(said) if c in known and not known[c].get("auto")]
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
        if not signature.specialties and not signature.sights and region.slug not in editorial_intros():
            return None
        return await local_signature_out(self._s, region.name, signature, region.slug)

    async def _with_anchor(self, req: dto.CourseGenerateRequest) -> dto.CourseGenerateRequest:
        """docs/34: a campus as the anchor of the day becomes the existing "around a point" request —
        origin = the campus, origin_label = its name — so snapshot, echo and reroll need nothing new."""
        if req.anchor is None:
            if req.purpose in context_purposes():
                raise errors.ValidationFailed("대학교를 먼저 고르면 쓸 수 있는 목적이에요.")
            return req
        rules = university_rules()
        campus = await self._places.campus(req.anchor.id, str(rules["category"]))
        if campus is None:
            raise errors.NotFound("그 학교는 아직 없어요. 지역이나 역으로 골라 주세요.")
        anchor = Anchor(
            kind="university",
            id=campus.public_id,
            place_id=campus.id,
            name=campus.name,
            point=GeoPoint(campus.lat, campus.lng),
            address=campus.road_address or campus.address,
        )
        self._anchors[anchor.id] = {"anchor": anchor, "festival": None, "festival_in_course": False}
        return req.model_copy(
            update={
                "origin": LatLng(lat=anchor.point.lat, lng=anchor.point.lng),
                "origin_label": anchor.name[:40],
            }
        )

    async def _apply_anchor(
        self, req: dto.CourseGenerateRequest, purpose: Purpose, ctx: RequestContext, templates: list[Template]
    ) -> tuple[list[Template], bool]:
        """The anchor's knobs for this purpose (data/recommendation/anchor_contexts.json) — nothing but the
        engine's own: the reach, the campus as a pinned stop, the day's festival as a pinned event.
        Returns the templates and whether a festival day was asked for but the campus has none that day."""
        assert req.anchor is not None
        state = self._anchors[req.anchor.id]
        anchor: Anchor = state["anchor"]
        plan = anchor_plan_for(purpose.code, req.transport)
        ctx.anchored = True
        ctx.radius_m = plan.radius_m
        festival = None
        if plan.festival != "none":
            events = await self._places.anchored_events(
                anchor.place_id, anchor.point, plan.campus_radius_m, ctx.start_at.date()
            )
            festival = pick_festival(events)
        state["festival"] = festival
        missing = plan.festival == "core" and festival is None
        # no festival that day: the day falls back to the campus itself (docs/34 §6), not to any sight
        campus_stop = "required" if missing else plan.campus_stop
        if campus_stop == "required":
            ctx.wanted_place_ids = ctx.wanted_place_ids | {anchor.place_id}
            ctx.keep_roles = ctx.keep_roles | {"ATTRACTION"}
            templates = campus_first(templates)
        if campus_stop != "none":
            ctx.anchor_place_ids = frozenset({anchor.place_id})
        if festival is not None:
            ctx.wanted_event_ids = frozenset({festival.id})
            if plan.festival == "core":
                templates = with_role(templates, {"role": "CULTURE", "share": 0.06, "min_slot_budget": 0})
                ctx.keep_roles = ctx.keep_roles | {"CULTURE"}
        return templates, missing

    def _note_festival(self, req: dto.CourseGenerateRequest, out: EngineOutput, missing: bool) -> None:
        """Say what happened to the festival: none that day (the day fell back to the campus), or one
        that day whose hours do not fit the chosen time."""
        if req.anchor is None:
            return
        state = self._anchors[req.anchor.id]
        festival: AnchoredEvent | None = state["festival"]
        notes: list[tuple[CourseResult, dict[str, Any]]] = []
        if missing:
            notes = [(course, festival_missing_warning()) for course in out.courses]
        elif festival is not None:
            for course in out.courses:
                held = any(s.place.is_event and s.place.id == festival.id for s in course.stops)
                state["festival_in_course"] = state["festival_in_course"] or held
                if not held and anchor_plan_for(req.purpose, req.transport).festival == "core":
                    hours = f"({festival.start_time}~{festival.end_time})" if festival.start_time else ""
                    notes.append(
                        (
                            course,
                            {
                                "code": "FESTIVAL_TIME_CLASH",
                                "detail": f"{festival.title}{hours}은(는) 고른 시간과 맞지 않아 못 넣었어요. "
                                "출발 시간을 바꿔 보세요.",
                            },
                        )
                    )
        for course, warning in notes:
            if warning not in out.warnings:
                out.warnings.append(warning)
            if warning not in course.warnings:
                course.warnings.append(warning)

    @staticmethod
    def _context_of(snapshot: dict[str, Any], around_point: bool) -> str:
        """docs/34: what the day was planned around — for the result page's first chip."""
        anchor = snapshot.get("anchor")
        if anchor:
            return "festival" if anchor.get("festival") else "university"
        return "specific_place" if around_point and snapshot.get("origin_label") else "general_area"

    def _anchor_snapshot(self, req: dto.CourseGenerateRequest) -> dict[str, Any] | None:
        if req.anchor is None or req.anchor.id not in self._anchors:
            return None
        state = self._anchors[req.anchor.id]
        anchor: Anchor = state["anchor"]
        festival: AnchoredEvent | None = state["festival"]
        return {
            "kind": anchor.kind,
            "id": anchor.id,
            "name": anchor.name,
            "festival": festival.title if festival is not None and state["festival_in_course"] else None,
        }

    async def dry_run(self, req: dto.CourseGenerateRequest) -> tuple[Region, RequestContext, EngineOutput]:
        """The exact production pipeline with nothing persisted — what `eval-courses` measures."""
        req = await self._with_anchor(req)
        region, _origin, _purpose, ctx, _profile, out = await self._plan(req, None)
        return region, ctx, out

    async def generate(
        self,
        req: dto.CourseGenerateRequest,
        user: User | None,
        idempotency_key: str | None = None,
        ip: str | None = None,
    ) -> dto.CourseGenerateResponse:
        started = time.perf_counter()
        body = req.model_dump(mode="json")
        digest = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()[:32]
        owner = user.public_id if user else "anon"
        # Same request → same courses is only safe for one owner: anonymous courses carry an edit key, so they
        # are never handed to another anonymous visitor (only this client's own retry, by idempotency key).
        keys = [f"course:{owner}:{digest}"] if user else []
        if idempotency_key:
            keys.insert(0, f"idem:{owner}:{hashlib.sha256(idempotency_key.encode()).hexdigest()[:32]}")
        for key in keys:
            if (cached := await self._cache.get(key)) is not None:
                return dto.CourseGenerateResponse.model_validate(cached)

        replaced = await self._day_to_replace(req, user)
        if replaced is not None:
            req = await self._as_that_day(req, replaced)
        # a new day of an anonymous trip keeps the trip's key (its days are saved and edited together)
        edit_key: str | None = None
        if user is None:
            keep = replaced is not None and replaced.edit_key_hash is not None
            edit_key = course_key.current_key() if keep else course_key.new_key()
        req = await self._with_anchor(req)
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
                engine_version=f"{self._settings.engine_version}+{ctx.algorithm}",  # A/B-ready (docs/29)
                selected_courses=[],
                warnings=out.warnings,
                ip=ip,
            )
        )
        snapshot = {
            "preferences": req.preferences.model_dump(),
            "stay_scale": out.stay_scale,
            "duration_min": req.duration_min,
            "style": ctx.style,
            # a swap or reorder re-plans with the engine the course was made with (docs/29)
            "algorithm": ctx.algorithm,
            "move_style": ctx.move_style,
            "pace": list(req.pace),
            "wishes": list(req.wishes),
            "scene": ctx.scene,
            "focus": ctx.focus,
            "purposes": list(ctx.purpose_codes),
            "segments": ctx.segments,
            "extras": [r for r in req.extras if r in extra_roles()],
            # what the user said about the day (a wish standing for a condition is echoed as the wish)
            "conditions": [
                c for c in self._conditions(req, wishes=False) if not day_conditions()[c].get("auto")
            ],
            # echoed by `get()` so the result page and a reroll stay around the same station / place
            "origin_label": req.origin_label if req.origin else None,
            # docs/34: the campus the day was planned around, and the festival that made it into the course
            "anchor": self._anchor_snapshot(req),
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
                edit_key_hash=course_key.hash_key(edit_key) if edit_key else None,
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

        views = [
            await self._top_up(row, r.stops, user) or self._view(row, r.stops, origin) for row, r, _ in rows
        ]
        response = dto.CourseGenerateResponse(
            request_id=request_id,
            edit_key=edit_key,
            local=await self._signature_out(region),
            courses=views,
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
                algorithm=ctx.algorithm,
                scoring_profile=profile.label,
                template=out.template.code,
                candidates=out.candidates_count,
                latency_ms=log.latency_ms,
            ),
        )
        payload = response.model_dump(mode="json")
        if user is not None:
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
                reason_codes=list(s.reason_codes),
                congestion=s.congestion,
                slot=_slot_snapshot(s),
            )
            for s in result.stops
        ]

    def _view(self, row: Course, stops: Sequence[StopResult], origin: GeoPoint) -> dto.CourseOut:
        reasons = {s.position: s.reason for s in row.stops}
        codes = {s.position: list(s.reason_codes or []) for s in row.stops}
        # no photo twice in one course (docs/29 §21): a later stop with the same photo shows the category tile
        photos = distinct_photos([s.place.thumbnail_url for s in stops])
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
                leftover=self._leftover(row, stops),
                travel_min=row.total_travel_min,
                distance_m=row.total_distance_m,
                duration_min=row.duration_min,
                score=row.total_score,
            ),
            stops=[
                dto.StopOut(
                    position=s.position,
                    role=s.role,
                    place=place_brief(s.place, photo=photo),
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
                    reason_short=short_reason(s.reason_codes or codes.get(s.position, []), s.place),
                    reason_codes=s.reason_codes or codes.get(s.position, []),
                    congestion=(
                        dto.Congestion(
                            level=self._narrative.congestion_level(s.congestion), value=round(s.congestion, 2)
                        )
                        if s.congestion is not None
                        else None
                    ),
                )
                for s, photo in zip(stops, photos, strict=True)
            ],
            route=dto.RouteOut(
                polyline=encode_polyline([origin, *(s.place.point for s in stops)]), optimizer=row.optimizer
            ),
            warnings=[dto.Warning.model_validate(w) for w in row.warnings or []],
        )

    def _leftover(self, row: Course, stops: Sequence[StopResult]) -> dto.LeftoverOut:
        """How much is left, in the user's words, and why (docs/49)."""
        request = row.request or {}
        found = leftover.assess(
            budget=row.budget_total,
            price=row.total_price,
            prices=[s.est_price for s in stops],
            night=is_night(self._out_time(row.start_at)),
            asked_value="value" in (request.get("wishes") or []),
            slot_empty=any(w.get("code") == "SLOT_EMPTY" for w in row.warnings or []),
            rules=(suggestion_rules() or {}).get("leftover") or {},
        )
        return dto.LeftoverOut(band=found.band, reason=found.reason, text=found.text)

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
                    reason_codes=list(s.reason_codes or []),
                )
            )
        return row, stops, GeoPoint(row.origin_lat, row.origin_lng)

    async def route(self, public_id: str) -> route_dto.CourseRouteOut:
        """Route Intelligence (docs/27): the course as a measured, checked route (map · cards · sheet)."""
        from app.services.route_service import RouteInputStop, RouteService

        row, stops, origin = await self._load(public_id)
        view = {s.position: s for s in self._view(row, stops, origin).stops}
        inputs = []
        for s in stops:
            v = view.get(s.position)
            leg = v.from_prev if v else None
            inputs.append(
                RouteInputStop(
                    sequence=s.position,
                    place_id=s.place.public_id,
                    name=v.place.name if v else s.place.name,
                    address=s.place.address,
                    lat=s.place.lat,
                    lng=s.place.lng,
                    arrive_at=s.arrive_at,
                    leave_at=s.leave_at,
                    price=s.est_price,
                    opening_hours=list(s.place.opening_hours),
                    mode=leg.mode if leg else row.transport,  # type: ignore[arg-type]
                    hop_to=leg.hop_to if leg else None,
                    est_minutes=s.travel_min_from_prev or 0,
                    est_distance_m=s.distance_m_from_prev or 0,
                )
            )
        return await RouteService(self._settings, self._cache).build(public_id, row.transport, inputs)  # type: ignore[arg-type]

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
                anchor=dto.AnchorEcho(**anchor) if (anchor := snapshot.get("anchor")) else None,
                context=self._context_of(snapshot, around_point),
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
                pace=list((row.request or {}).get("pace") or []),
                move_style=(row.request or {}).get("move_style"),
                wishes=list((row.request or {}).get("wishes") or []),
                scene=(row.request or {}).get("scene"),
                scene_label=resolve_scene(purpose.code, (row.request or {}).get("scene"))[1].get("label")
                if (row.request or {}).get("scene")
                else None,
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
        # the same reading of pace and wishes as when it was made (docs/30)
        understood = interpret(
            pace=(row.request or {}).get("pace") or [],
            wishes=(row.request or {}).get("wishes") or [],
            liked_tags=ctx.liked_tags,
            disliked_tags=ctx.disliked_tags,
        )
        profile, _ = self._apply_understood(ctx, profile, [], understood)
        ctx.scene, scene = resolve_scene(ctx.purpose_code, (row.request or {}).get("scene"))
        profile, _ = self._apply_scene(ctx, profile, [], scene)
        # the day as it was said to be (rain, or "실내 위주"), and the night the clock says: a replacement
        # must not bring back the walk the rainy day took out
        said = [*((row.request or {}).get("conditions") or []), *understood.conditions]
        if "night" in day_conditions() and is_night(start_at):
            said.append("night")
        self._apply_conditions(ctx, list(dict.fromkeys(said)))
        # the engine the course was made with; courses from before docs/29 were planned by v1
        ctx.algorithm = str((row.request or {}).get("algorithm") or "v1")
        ctx.move_style = str((row.request or {}).get("move_style") or "balanced")
        ctx.core_radius_m = region.radius_m if region else 1200
        # a place that joined from beyond the neighbourhood keeps saying so after a replan
        ctx.ring_keys = {
            (s.event_id is not None, s.event_id or s.place_id or 0)
            for s in row.stops
            if "WORTH_THE_TRIP" in (s.reason_codes or [])
        }
        # a swap must not bring in what the course was never asked to have (a ballpark on a day off)
        kept = (row.request or {}).get("extras") or []
        asked = {str(extra_roles()[r].get("category")) for r in kept if r in extra_roles()}
        ctx.blocked_categories = (
            (opt_in_categories() - asked)
            | {str(university_rules()["category"])}
            | understood.blocked_categories
        )
        stay_scale = float((row.request or {}).get("stay_scale", 1.0))
        return ctx, profile, CourseComposer(PlaceScorer(profile, ctx), ctx, stay_scale=stay_scale)

    @staticmethod
    def _apply_scene(
        ctx: RequestContext, profile: ScoringProfile, templates: Sequence[Template], scene: Mapping[str, Any]
    ) -> tuple[ScoringProfile, list[Template]]:
        """누구와 (docs/48): who comes along moves the same knobs a style does — never the hard limits."""
        if not scene:
            return profile, list(templates)
        ctx.purpose_tag_affinity = styled_affinity(ctx.purpose_tag_affinity, scene)
        for tag, roles in styled_never(scene).items():
            ctx.never_tags_by_role[tag] = ctx.never_tags_by_role.get(tag, frozenset()) | roles
        for tag in scene.get("allow_tags") or ():  # "어른끼리": the family's no-pocha rule does not apply
            ctx.never_tags_by_role.pop(tag, None)
            ctx.avoid_tags_by_role.pop(tag, None)
        ctx.blocked_categories = ctx.blocked_categories | frozenset(scene.get("blocked_categories") or ())
        # which kinds of place this company likes, straight onto the score: through the preference feature a
        # place's many tags drowned the category and the scenes changed almost nothing (2026-09-25)
        for code, weight in (scene.get("category_weights") or {}).items():
            ctx.trait_pull[f"cat:{code}"] = round(
                ctx.trait_pull.get(f"cat:{code}", 0.0) + SCENE_CATEGORY_PULL * float(weight), 3
            )
        templates = styled_templates(reweight_templates(templates, scene.get("role_share") or {}), scene)
        if scene.get("add_optional"):
            templates = with_optional_after(templates, scene["add_optional"])
        if scene.get("end_by"):  # "아이와": an open-ended day wraps up in the early evening
            hh, mm = (int(x) for x in str(scene["end_by"]).split(":"))
            ctx.soft_end_min = hh * 60 + mm
        if scene.get("params"):  # shorter legs with children or parents
            profile = styled_profile(profile, {"params": scene["params"]})
        return profile, templates

    @staticmethod
    def _apply_conditions(ctx: RequestContext, names: Sequence[str]) -> None:
        """A condition's tag pull and its per-role avoidances (the template swap is generation's own)."""
        for name in names:
            condition = day_conditions().get(name)
            if not condition:
                continue
            ctx.purpose_tag_affinity = styled_affinity(ctx.purpose_tag_affinity, condition)
            for tag, roles in styled_avoidance(condition).items():
                ctx.avoid_tags_by_role[tag] = ctx.avoid_tags_by_role.get(tag, frozenset()) | roles
            if condition.get("max_walk_leg_min"):
                ctx.leg_cap_min = float(condition["max_walk_leg_min"])
        # a walk that starts in the evening ends after dark: no mountain-top view on foot or by transit then
        # either (18:30 starts reached 우면산 소망탑 at 21:55). By car a night view is the drive.
        night = day_conditions().get("night") or {}
        if ctx.transport != "car" and (ctx.start_at.hour >= DARK_BY_THE_END_H or is_night(ctx.start_at)):
            ctx.avoid_names |= {compact_name(w) for w in night.get("avoid_names_on_foot") or ()}

    @staticmethod
    def _apply_understood(
        ctx: RequestContext, profile: ScoringProfile, templates: Sequence[Template], understood: Interpreted
    ) -> tuple[ScoringProfile, list[Template]]:
        """Pace and wishes as soft weights on top of the purpose (docs/30 §13: preferences and style never
        override the hard limits — budget, time, party, "술 한잔 포함" stay where they were)."""
        if not (understood.pace or understood.wishes):
            return profile, list(templates)
        twist = understood.as_style()
        ctx.purpose_tag_affinity = styled_affinity(ctx.purpose_tag_affinity, twist)
        ctx.slot_min_scale = understood.slot_scale
        ctx.structure_fill = understood.structure_fill
        ctx.trait_pull = dict(understood.trait_pull)
        return styled_profile(profile, twist), reweight_templates(templates, understood.role_share)

    @staticmethod
    def _apply_style(
        ctx: RequestContext, profile: ScoringProfile, templates: Sequence[Template], name: str | None
    ) -> tuple[ScoringProfile, list[Template]]:
        """Twists the purpose profile, its tag affinities and its templates by the requested style."""
        ctx.style, style = resolve_style(profile, name)
        ctx.purpose_tag_affinity = styled_affinity(ctx.purpose_tag_affinity, style)
        ctx.avoid_tags_by_role = styled_avoidance(style)
        ctx.never_tags_by_role = styled_never(style)
        return styled_profile(profile, style), styled_templates(templates, style)

    async def _finish_replan(
        self,
        row: Course,
        partial: Partial,
        ctx: RequestContext,
        profile: ScoringProfile,
        extra_warnings: list[dict[str, Any]],
    ) -> dto.CourseOut:
        # What was said about the request stays said (the hour is still night, the bar still could not be
        # added); only what is read off the stops themselves is worked out again below.
        still_here = {s.place.public_id for s in partial.stops}
        keep = [
            w
            for w in row.warnings or []
            if w.get("code") not in RECOMPUTED_WARNINGS
            # "we added X for you" goes when X goes
            and (w.get("code") != "TOPPED_UP" or (w.get("meta") or {}).get("place_id") in still_here)
        ]
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

    async def _swap_options(
        self,
        row: Course,
        stops: Sequence[StopResult],
        target: StopResult,
        origin: GeoPoint,
        user: User | None,
    ) -> tuple[RequestContext, ScoringProfile, CourseComposer, list[tuple[PlaceCandidate, Partial]]]:
        """Every place that could take `target`'s spot, each with the whole course re-timed around it: same
        role, open when the course gets there, within what that stop may cost, not already in the course,
        under the request's own conditions and wishes (the same checks for swap, candidates and a pick)."""
        assert target.slot is not None
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
        if ctx.is_v2:  # the same reach as generation: a standout a little further may replace it (docs/29)
            pool = await self._with_ring(pool, target, origin, radius, fc, ctx, profile)

        options: list[tuple[PlaceCandidate, Partial]] = []
        for cand in pool:
            sequence = [
                (
                    cand if s.position == target.position else s.place,
                    SlotBudget(s.slot, s.slot_share, s.slot_base_budget),
                )
                for s in stops
                if s.slot is not None
            ]
            partial = composer.replan(sequence, strict=True)
            if partial is not None:
                options.append((cand, partial))
        return ctx, profile, composer, options

    @staticmethod
    def _target(stops: Sequence[StopResult], position: int) -> StopResult | None:
        target = next((s for s in stops if s.position == position), None)
        return target if target is not None and target.slot is not None else None

    async def swap(self, public_id: str, req: dto.SwapRequest, user: User | None) -> dto.CourseOut:
        row, stops, origin = await self._load(public_id)
        self._check_owner(row, user)
        target = self._target(stops, req.position)
        if target is None:
            raise errors.ValidationFailed(f"{req.position}번째 장소가 없어요.")
        ctx, profile, _composer, options = await self._swap_options(row, stops, target, origin, user)
        b = ctx.budget_per_person

        def j(item: tuple[PlaceCandidate, Partial]) -> float:
            return objective(item[1], b, profile.params, final=True, ctx=ctx)

        current = target.place
        if req.place_id is not None:  # the user picked one of the offered places: that one, or a clear no
            picked = [o for o in options if o[0].public_id == req.place_id]
            if not picked:
                raise errors.CandidateNotEligible(
                    "이 곳은 지금 이 자리에 넣을 수 없어요. 후보를 새로 불러와 주세요.",
                    meta={"place_id": req.place_id, "position": req.position},
                )
            options = picked
        elif req.strategy == "cheaper":
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
                "stop_swapped",
                user.public_id if user else row.public_id,
                {"strategy": "pick" if req.place_id else req.strategy},
            )
        )
        return out

    async def candidates(
        self, public_id: str, position: int, limit: int, viewer: User | None
    ) -> dto.StopCandidateList:
        """A few places that could take one stop's spot, best for the whole day first, of different kinds
        where possible — the same places a swap would accept, so any of them can be picked (`place_id`)."""
        row, stops, origin = await self._load(public_id)
        target = self._target(stops, position)
        if target is None:
            raise errors.StopNotFound(f"{position}번째 장소가 없어요.")
        # 1.5 s of engine work per sheet opening → remembered for this exact course state (the places in
        # order: a swap or reorder changes the key) and this viewer (their preferences shape the order)
        state = hashlib.sha256(
            "|".join(f"{s.position}:{s.place.public_id}" for s in stops).encode()
        ).hexdigest()[:16]
        key = f"cand:{public_id}:{position}:{limit}:{viewer.public_id if viewer else '-'}:{state}"
        if (cached := await self._cache.get(key)) is not None:
            return dto.StopCandidateList.model_validate(cached)
        ctx, profile, composer, options = await self._swap_options(row, stops, target, origin, viewer)
        b = ctx.budget_per_person
        options.sort(key=lambda o: (-objective(o[1], b, profile.params, final=True, ctx=ctx), o[0].id))
        picked: list[tuple[PlaceCandidate, Partial]] = []
        for o in options:  # one of each kind first: three cafés of one chain are one choice, not three
            if len(picked) < limit and all(o[0].category_code != p[0].category_code for p in picked):
                picked.append(o)
        picked += [o for o in options if all(o is not p for p in picked)][: limit - len(picked)]
        # the course as it is, timed the same way, so the difference is the place and not the estimator
        now = composer.replan(
            [
                (s.place, SlotBudget(s.slot, s.slot_share, s.slot_base_budget))
                for s in stops
                if s.slot is not None
            ],
            strict=False,
        )
        base_travel = now.travel_min if now is not None else float(row.total_travel_min)
        items = []
        for cand, partial in picked:
            est_price = cand.price * row.party_size
            price_delta = est_price - target.est_price
            walk_delta = round(partial.travel_min - base_travel) if row.transport == "walk" else None
            items.append(
                dto.StopCandidate(
                    place=place_brief(cand),
                    role=cand.course_role,
                    est_price=est_price,
                    price_delta=price_delta,
                    walk_min_delta=walk_delta,
                    line=candidate_line(cand, price_delta, walk_delta),
                )
            )
        out = dto.StopCandidateList(items=items)
        await self._cache.set(key, out.model_dump(mode="json"), CANDIDATES_TTL_S)
        return out

    async def _with_ring(
        self,
        pool: list[PlaceCandidate],
        target: StopResult,
        origin: GeoPoint,
        radius: float,
        fc: FilterContext,
        ctx: RequestContext,
        profile: ScoringProfile,
    ) -> list[PlaceCandidate]:
        params = profile.params
        tiers = day_score.reach_tiers(params, ctx)
        far = min(ctx.core_radius_m * max(tiers), params.reach_max_m(ctx.transport)) if tiers else 0.0
        if far <= radius:
            return pool
        found = await self._places.fetch_standouts(
            target.role, origin, far, min_popularity=params.worth_trip_min, place_ids=sorted(ctx.landmark_ids)
        )
        ring = [
            p
            for p in hard_filter(found, fc, params)
            if p.public_id != target.place.public_id and haversine_m(origin, p.point) > radius
        ]
        admitted = RecommendationEngine._admit_rings(ctx, {0: pool}, {0: ring}, params)
        return admitted[0]

    async def _leftover_options(
        self, row: Course, stops: Sequence[StopResult], user: User | None, *, same_role: bool = False
    ) -> list[tuple[str, PlaceCandidate, int, int]]:
        """(role, place, walk minutes, metres) near the last stop that the money left over can buy.
        `same_role`: a second cafe is not a suggestion, but a second free sight beats a course of one place
        (the top-up asks for it only when nothing else was found)."""
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
        vetoed = vetoed_roles([str(code) for code in purposes]) | (
            set() if same_role else {s.role for s in stops}
        )
        # "조용하게" offers no pub afterwards either, unless a drink was asked for by name
        extras = (row.request or {}).get("extras") or []
        asked_roles = {str(extra_roles()[r]["role"]) for r in extras if r in extra_roles()}
        wishes = (row.request or {}).get("wishes") or []
        vetoed |= {r for w in wishes for r in WISH_AVOID_ROLES.get(w, ())} - asked_roles
        reach_m = float(rules["max_walk_min"]) * float(rules["walk_m_per_min"])
        arrive_at = last.leave_at + timedelta(minutes=5)
        minute = evening_minute(self._local(arrive_at))  # 00:01 is the same evening, not a morning
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
        out = await self._append(row, stops, role, place, user, [])
        if out is None:
            raise errors.ValidationFailed("이 곳을 넣으면 시간이 맞지 않아요.")
        await self._tracker.track(
            AnalyticsEvent("stop_added", user.public_id if user else row.public_id, {"role": role})
        )
        return out

    async def _append(
        self,
        row: Course,
        stops: Sequence[StopResult],
        role: str,
        place: PlaceCandidate,
        user: User | None,
        notes: list[dict[str, Any]],
    ) -> dto.CourseOut | None:
        """One of `_leftover_options` goes to the end of the course (None: the hours do not work out)."""
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
            return None
        return await self._finish_replan(row, partial, ctx, profile, notes)

    async def _top_up(
        self, row: Course, stops: Sequence[StopResult], user: User | None
    ) -> dto.CourseOut | None:
        """One place is not a course. When the budget could not pay for the rest (two people, 20,000 won,
        2 a.m.: the cheapest kitchen still open costs more), what we would have offered as "이런 건 어때요?"
        — a walk away, open at that hour, within the money left — is put in, and the course says so."""
        rules = (suggestion_rules() or {}).get("top_up") or {}
        out: dto.CourseOut | None = None
        for _ in range(int(rules.get("max_added", 0))):
            few = len(stops) < int(rules.get("below_stops", 0))
            # docs/49: a course that spent under 60 % is filled once more before anyone sees it — by day.
            # At night little is open and the night was cut short on purpose; the leftover line says why
            # (2026-09-25: a family night got two coin karaoke rooms after 23:00 this way)
            use = row.total_price / row.budget_total if row.budget_total else 1.0
            underspent = use < float(rules.get("below_use", 0.0)) and not is_night(
                self._out_time(row.start_at)
            )
            if not (few or underspent):
                break
            options = await self._leftover_options(row, stops, user)
            if not options and few:  # a second of a kind only to save a course of one place
                options = await self._leftover_options(row, stops, user, same_role=True)
            if not options:
                break
            role, place, _walk_min, _metres = options[0]
            note = {
                "code": "TOPPED_UP",
                "detail": str(
                    rules.get("notice")
                    if few
                    else rules.get("notice_underspent") or rules.get("notice") or ""
                ).format(place=place.name),
                "meta": {"place_id": place.public_id, "role": role},
            }
            added = await self._append(row, stops, role, place, user, [note])
            if added is None:
                break
            out = added
            row, stops, _origin = await self._load(row.public_id)
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
        """An owned course: its owner only. An ownerless one: whoever holds its edit key (X-Course-Key);
        a legacy ownerless course without a key hash stays open, as before."""
        if row.user_id is not None:
            return user is not None and user.id == row.user_id
        if row.edit_key_hash is None:
            return True
        return course_key.matches(course_key.current_key(), row.edit_key_hash)

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


def _fit(line: str) -> str:
    return line if len(line) <= CANDIDATE_LINE_MAX else line[: CANDIDATE_LINE_MAX - 1] + "…"


def candidate_line(place: PlaceCandidate, price_delta: int, walk_delta: int | None) -> str:
    """One short line under a replacement option: what changes for the day, from the numbers only."""
    cheaper, closer = price_delta < 0, walk_delta is not None and walk_delta < 0
    if cheaper and closer:
        assert walk_delta is not None
        return _fit(f"{-price_delta:,}원 아끼고 {-walk_delta}분 덜 걸어요")
    if cheaper:
        return _fit(f"지금보다 {-price_delta:,}원 아껴요")
    if closer:
        assert walk_delta is not None
        return _fit(f"이동이 {-walk_delta}분 줄어요")
    if place.price == 0:
        return "돈 들이지 않고 들를 수 있어요"
    if place.local_word:
        return _fit(f"이 동네 명물 {place.local_word} 집이에요")
    if price_delta == 0:
        return "같은 예산으로 다른 곳에 가 봐요"
    return _fit(f"{price_delta:,}원 더 들지만 예산 안이에요")


def short_reason(codes: Sequence[str], place: PlaceCandidate) -> str | None:
    """reason_codes (strongest first) as one card subtitle of at most 40 characters. Only what the code
    itself says about the place — never a claim the data does not hold (no reviews, no "맛집" by guess)."""
    for code in codes:
        line: str | None = None
        if code == "LOCAL_SIGNIFICANCE":
            line = f"이 동네 명물 {place.local_word}" if place.local_word else "이 동네에서 이름난 곳"
        elif code == "WORTH_THE_TRIP":
            line = "조금 멀어도 들를 만한 곳"
        elif code == "UNIQUE_EXPERIENCE":
            line = "오늘 하루에 색다른 경험 하나"
        elif code == "PURPOSE_MATCH":
            line = "오늘 목적에 잘 맞는 곳"
        elif code == "USER_PREFERENCE":
            line = "고른 취향에 맞는 곳"
        elif code == "HIGH_PLACE_QUALITY":
            if place.is_curated:
                line = "공공기관이 소개 · 지정한 곳"
            elif place.popularity >= 0.6:
                line = "사람들이 실제로 많이 찾는 곳"
        elif code == "BUDGET_FIT":
            line = "돈 들이지 않고 들르는 곳" if place.price == 0 else "예산에 잘 맞는 곳"
        elif code == "DIVERSITY":
            line = "코스에 변화를 주는 곳"
        elif code == "ROUTE_BALANCE":
            line = "앞 장소에서 가까워요"
        if line:
            return _fit(line)
    return "돈 들이지 않고 들르는 곳" if place.price == 0 else None


_KEEP = object()


def place_brief(p: PlaceCandidate, *, photo: str | object | None = _KEEP) -> dto.PlaceBrief:
    return dto.PlaceBrief(
        id=p.public_id,
        kind="event" if p.is_event else "place",
        name=get_tag_rules().sign_name(p.name),
        category=p.category_code,
        category_name=p.category_name,
        lat=p.lat,
        lng=p.lng,
        address=p.address,
        thumbnail_url=p.thumbnail_url if photo is _KEEP else photo,
        rating=p.rating_avg,
        review_count=p.rating_count,
        price_per_person=None if p.is_free else p.price_per_person,
        price_is_estimated=p.price_is_estimated,
        is_free=p.is_free,
        # scoring-only tags (e.g. "체인점") are not shown on the card
        tags=sorted(get_tag_rules().visible(p.tags), key=lambda t: -p.tags[t])[:4],
    )
