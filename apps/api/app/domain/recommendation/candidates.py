"""Hard filters of doc 06 §2. Anything rejected here never reaches scoring."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime

from app.domain.models import PlaceCandidate, RequestContext, ScoringParams
from app.domain.recommendation.features import is_open

SIGHT_ROLES = frozenset({"ATTRACTION", "CULTURE", "NIGHTVIEW"})


def compact_name(name: str) -> str:
    return "".join(name.split()).lower()


def area_names_of(region_name: str) -> frozenset[str]:
    """Every way the chosen area is called: full name, each part around "·", "OO입구"/"OO역" → "OO"."""
    parts = {region_name, *region_name.replace("·", " ").replace("(", " ").replace(")", " ").split()}
    parts |= {p.removesuffix("입구").removesuffix("역") for p in set(parts)}
    return frozenset(compact_name(p) for p in parts if len(compact_name(p)) >= 2)


@dataclass(frozen=True, slots=True)
class FilterContext:
    role: str
    slot_budget: float
    arrive_at: datetime
    party_size: int
    disliked_tags: frozenset[str]
    exclude_place_ids: frozenset[int]
    area_names: frozenset[str] = frozenset()
    blocked_categories: frozenset[str] = frozenset()
    # docs/34: places let through a blocked category — the campus the day is anchored on
    allowed_place_ids: frozenset[int] = frozenset()
    avoid_names: frozenset[str] = frozenset()

    @classmethod
    def build(cls, ctx: RequestContext, role: str, slot_budget: float, arrive_at: datetime) -> FilterContext:
        return cls(
            role=role,
            slot_budget=slot_budget,
            arrive_at=arrive_at,
            party_size=ctx.party_size,
            disliked_tags=frozenset(ctx.disliked_tags)
            | frozenset(t for t, roles in ctx.avoid_tags_by_role.items() if role in roles)
            | never_tags(ctx, role),
            exclude_place_ids=frozenset(ctx.exclude_place_ids),
            area_names=ctx.area_names,
            blocked_categories=ctx.blocked_categories,
            allowed_place_ids=ctx.anchor_place_ids,
            avoid_names=ctx.avoid_names,
        )


def never_tags(ctx: RequestContext, role: str) -> frozenset[str]:
    return frozenset(t for t, roles in ctx.never_tags_by_role.items() if role in roles)


def price_ok(place: PlaceCandidate, slot_budget: float, params: ScoringParams) -> bool:
    if place.is_free or not place.price_per_person:
        return True
    return place.price_per_person <= params.price_cap_ratio * slot_budget


def rejection_reason(place: PlaceCandidate, fc: FilterContext, params: ScoringParams) -> str | None:
    if place.course_role != fc.role:
        return "role"
    if not place.is_event and place.id in fc.exclude_place_ids:
        return "excluded_place"
    if place.category_code in fc.blocked_categories and (
        place.is_event or place.id not in fc.allowed_place_ids
    ):
        return "opt_in_only"  # shown only when the user asks for it (or the day is anchored on it)
    if not price_ok(place, fc.slot_budget, params):
        return "price_cap"
    if fc.avoid_names and any(word in compact_name(place.name) for word in fc.avoid_names):
        return "avoided_name"  # e.g. a mountain-top view at night, on foot
    if fc.area_names and place.course_role in SIGHT_ROLES and compact_name(place.name) in fc.area_names:
        return "is_the_area"  # the "sight" is the area the user is already in
    if any(place.tags.get(t, 0.0) >= params.exclude_tag_threshold for t in fc.disliked_tags):
        return "excluded_tag"
    if (
        params.group_tag
        and fc.party_size >= params.group_min_party
        and place.course_role not in {"ATTRACTION", "NIGHTVIEW", "CULTURE"}
        and place.tags.get(params.group_tag, 0.0) <= 0
    ):
        return "capacity"
    # closing soon / break time: the visit must fit before the doors (or the kitchen) close
    if not is_open(place.opening_hours, fc.arrive_at, stay_min=min(place.default_stay_min, 30)):
        return "closed"
    return None


def hard_filter(
    places: Iterable[PlaceCandidate], fc: FilterContext, params: ScoringParams
) -> list[PlaceCandidate]:
    return [p for p in places if rejection_reason(p, fc, params) is None]
