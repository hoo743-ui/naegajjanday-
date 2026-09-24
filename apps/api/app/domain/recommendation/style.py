"""Course style: the same budget spent "efficiently" (close, little walking) or "for fun".

A style is a twist of the purpose's own profile, never a separate engine:
  weight_mult / weight_add → scoring weights        params  → ScoringParams overrides
  affinity_add             → purpose tag affinities swap_roles → template slots

Defaults live here; `scoring_profile.params.styles` (DB) overrides them per purpose, the same way
`params.variants` overrides the alternative courses.

`buzz` is the popularity signal public data can honestly give: how many shops stand within a short walk.
A place in a packed street scores high, a lone shop on a back road scores low. No reviews or ratings are
involved (we have none) — once our own save/visit counts exist they belong in this same feature.
"""

from __future__ import annotations

import json
import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import replace
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.domain.models import CourseResult, PlaceCandidate, ScoringProfile, Slot, Template
from app.domain.recommendation.diversify import variant_profile

DEFAULT_STYLE = "efficient"

DEFAULT_STYLES: dict[str, dict[str, Any]] = {
    "efficient": {},
    "fun": {
        # walking a little further is fine when the place is worth it
        "weight_mult": {"distance": 0.45, "budget": 0.8, "congestion": 0.4, "purpose_fit": 1.25},
        "weight_add": {"buzz": 0.22},
        "params": {"lambda_travel": 0.006},
        # a nationwide chain is nobody's idea of a fun day out; hands-on and lively places are
        "affinity_add": {"체인점": -0.5, "체험형": 0.6, "힙한": 0.4, "활기찬": 0.4, "포토존": 0.3},
        # the free park stroll that closes every course becomes something to DO
        # The play money comes out of the meal, not out of every slot: spread evenly it pushed the
        # BAR slot under real pub prices and the evening lost its last stop.
        "swap_roles": {"ATTRACTION": {"role": "ACTIVITY", "share": 0.14, "take_from": "MEAL"}},
        # Hard-avoided like a user's own "피할래요" tag, but only where a chain is the dull choice.
        # Pubs stay: non-chain bars are priced ~25,000/person by category average, so banning chain
        # pubs removed the BAR stop from every ordinary budget — and chain pubs ARE where people gather.
        "avoid_tags": {"체인점": ["MEAL", "CAFE", "DESSERT"]},
    },
}

MIN_DONOR_KEEP = 0.6  # the meal never gives up more than 40 % of its share
BUZZ_RADIUS_M = 120.0
BUZZ_SATURATION_PCTL = 0.9  # the 90th percentile of the pool counts as "fully buzzing"
_M_PER_DEG_LAT = 111_320.0


def resolve_style(profile: ScoringProfile, name: str | None) -> tuple[str, dict[str, Any]]:
    overrides = profile.params.styles or {}
    known = {*DEFAULT_STYLES, *overrides}
    key = name if name in known else DEFAULT_STYLE
    return key, {**DEFAULT_STYLES.get(key, {}), **overrides.get(key, {})}


def styled_profile(profile: ScoringProfile, style: Mapping[str, Any]) -> ScoringProfile:
    if not style:
        return profile
    out = variant_profile(profile, dict(style))
    added = {k: out.weights.get(k, 0.0) + float(v) for k, v in (style.get("weight_add") or {}).items()}
    return replace(out, weights={**out.weights, **added})


def styled_affinity(affinity: Mapping[str, float], style: Mapping[str, Any]) -> dict[str, float]:
    out = dict(affinity)
    for tag, delta in (style.get("affinity_add") or {}).items():
        out[tag] = max(-1.0, min(1.0, out.get(tag, 0.0) + float(delta)))
    return out


def styled_avoidance(style: Mapping[str, Any]) -> dict[str, frozenset[str]]:
    return {tag: frozenset(roles) for tag, roles in (style.get("avoid_tags") or {}).items()}


def styled_never(style: Mapping[str, Any]) -> dict[str, frozenset[str]]:
    """Like avoid_tags, but kept even when the slot would otherwise stay empty."""
    return {tag: frozenset(roles) for tag, roles in (style.get("never_tags") or {}).items()}


def styled_templates(templates: Sequence[Template], style: Mapping[str, Any]) -> list[Template]:
    swaps: Mapping[str, Mapping[str, Any]] = style.get("swap_roles") or {}
    if not swaps:
        return list(templates)
    return [_swap_roles(t, swaps) for t in templates]


def _swap_roles(template: Template, swaps: Mapping[str, Mapping[str, Any]]) -> Template:
    if template.time_band == "night":
        # each purpose writes its own night (docs/48): the walk after a drink is the point, and "fun" turned
        # a family's and a solo evening's stroll into a karaoke room
        return template
    present = {s.course_role for s in template.slots}
    slots: list[Slot] = []
    for slot in template.slots:
        swap = swaps.get(slot.course_role)
        # never create a second slot of a role the template already has
        if swap is None or str(swap["role"]) in present:
            slots.append(slot)
            continue
        present.add(str(swap["role"]))
        slots.append(replace(slot, course_role=str(swap["role"]), budget_share=float(swap["share"])))
        extra = float(swap["share"]) - slot.budget_share
        donor = next((i for i, s in enumerate(slots) if s.course_role == swap.get("take_from")), None)
        if donor is not None and extra > 0:
            keep = max(slots[donor].budget_share - extra, slots[donor].budget_share * MIN_DONOR_KEEP)
            slots[donor] = replace(slots[donor], budget_share=keep)
    return replace(template, slots=tuple(slots))


CONDITIONS_PATH = Path(__file__).resolve().parents[3] / "data" / "recommendation" / "conditions.json"


@lru_cache(maxsize=1)
def day_conditions(path: Path = CONDITIONS_PATH) -> dict[str, dict[str, Any]]:
    """What the day is like (rain, …), each described with the same knobs a style has."""
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {k: v for k, v in data.items() if not k.startswith("_")}


EXTRA_ROLES_PATH = Path(__file__).resolve().parents[3] / "data" / "recommendation" / "extra_roles.json"


@lru_cache(maxsize=1)
def extra_roles(path: Path = EXTRA_ROLES_PATH) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {k: v for k, v in data.items() if not k.startswith("_")}


def carries(course: CourseResult, extra: Mapping[str, Any]) -> bool:
    """Whether the course holds what was asked for by name: that kind of place, or else that role."""
    if extra.get("category"):
        return any(s.place.category_code == extra["category"] for s in course.stops)
    return any(s.role == extra["role"] for s in course.stops)


def extra_unavailable(name: str, extra: Mapping[str, Any], *, vetoed: bool) -> dict[str, Any]:
    """The user ticked "a drink" / "a ball game" and the course has none: say so, never drop it silently."""
    detail = extra.get("vetoed" if vetoed else "missing") or extra.get("missing") or ""
    return {
        "code": "EXTRA_UNAVAILABLE",
        "detail": str(detail),
        "meta": {"extra": name, "label": extra.get("label"), "vetoed": vetoed},
    }


SUGGESTIONS_PATH = Path(__file__).resolve().parents[3] / "data" / "recommendation" / "suggestions.json"


@lru_cache(maxsize=1)
def suggestion_rules(path: Path = SUGGESTIONS_PATH) -> dict[str, Any]:
    """What to offer when money is left over (DATA — edit, restart)."""
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {k: v for k, v in data.items() if not k.startswith("_")}


def night_notice(condition: Mapping[str, Any]) -> dict[str, Any]:
    """Hours after dark are inferred from signs and names: the page must say so."""
    return {"code": "NIGHT_HOURS_ESTIMATED", "detail": str(condition.get("notice") or ""), "meta": {}}


def opt_in_categories() -> frozenset[str]:
    """Categories that enter a course only on request (every extras entry that names a category)."""
    return frozenset(str(e["category"]) for e in extra_roles().values() if e.get("category"))


def wanted_pools(
    pools: Mapping[int, list[PlaceCandidate]], categories: Sequence[str]
) -> dict[int, list[PlaceCandidate]]:
    """The user asked for a kind of place by name: the first slot that has one offers nothing else."""
    out = dict(pools)
    for category in categories:
        for position in sorted(out):
            matching = [c for c in out[position] if c.category_code == category]
            if matching:
                out[position] = matching
                break
    return out


def wanted_places(
    pools: Mapping[int, list[PlaceCandidate]], place_ids: frozenset[int]
) -> dict[int, list[PlaceCandidate]]:
    """A leg planned around a well-visited area must show what the area is visited for: the first
    slot that can hold one of those sights offers nothing else. Nothing changes when none of them
    passed the filters (closed at that hour, over the budget)."""
    out = dict(pools)
    if not place_ids:
        return out
    for position in sorted(out):
        # an event id can equal a place id (separate tables): only places answer a place id
        matching = [c for c in out[position] if c.id in place_ids and not c.is_event]
        if matching:
            out[position] = matching
            break
    return out


def wanted_events(
    pools: Mapping[int, list[PlaceCandidate]], event_ids: frozenset[int]
) -> dict[int, list[PlaceCandidate]]:
    """That day's festival of the anchor campus (docs/34): the first slot that can hold it offers only it.
    Nothing changes when it did not pass the filters (its hours clash with the day, over the budget)."""
    out = dict(pools)
    if not event_ids:
        return out
    for position in sorted(out):
        matching = [c for c in out[position] if c.is_event and c.id in event_ids]
        if matching:
            out[position] = matching
            break
    return out


def kept_pools(
    pools: Mapping[int, list[PlaceCandidate]],
    positions: Sequence[tuple[int, str]],
    kept: Sequence[PlaceCandidate],
) -> dict[int, list[PlaceCandidate]]:
    """The stops the user pinned: each takes the first free slot of its own role (slots in visiting order,
    pinned places in the order given, so the old order holds where the template allows) and is the only
    candidate there. No other slot offers a pinned place. A pinned place with no slot of its role left is
    not placed here; the caller says so (KEPT_PLACE_DROPPED)."""
    out = dict(pools)
    if not kept:
        return out
    keys = {(p.is_event, p.id) for p in kept}
    for position in out:
        out[position] = [c for c in out[position] if (c.is_event, c.id) not in keys]
    taken: set[int] = set()
    for place in kept:
        at = next((pos for pos, role in positions if role == place.course_role and pos not in taken), None)
        if at is None:
            continue
        taken.add(at)
        out[at] = [place]
    return out


KEPT_MIN_SHARE, KEPT_MAX_SHARE = 0.05, 0.6


def with_kept(
    templates: Sequence[Template], kept: Sequence[PlaceCandidate], budget_per_person: float
) -> list[Template]:
    """Every template gets a slot for each pinned place: a slot of that role that is already there stops being
    "if it fits"; a role with fewer slots than pinned places gets one more, with the share the place's own
    price takes of the budget (the other shares shrink to make room)."""
    if not kept:
        return list(templates)
    need: dict[str, list[PlaceCandidate]] = {}
    for place in kept:
        need.setdefault(place.course_role, []).append(place)
    out: list[Template] = []
    for template in templates:
        slots = list(template.slots)
        for role, places in need.items():
            have = [i for i, s in enumerate(slots) if s.course_role == role]
            for i in have[: len(places)]:
                slots[i] = replace(slots[i], is_optional=False)
            for place in places[len(have) :]:
                share = place.price / budget_per_person if budget_per_person > 0 else 0.0
                share = min(KEPT_MAX_SHARE, max(KEPT_MIN_SHARE, share))
                slots = [replace(s, budget_share=s.budget_share * (1.0 - share)) for s in slots]
                slots.append(
                    Slot(
                        position=max((s.position for s in slots), default=0) + 1,
                        course_role=role,
                        budget_share=share,
                    )
                )
        out.append(replace(template, slots=tuple(slots)))
    return out


def with_role(templates: Sequence[Template], extra: Mapping[str, Any]) -> list[Template]:
    """The user asked for a role by name ("a drink, please"): every template gets that slot for certain.

    A template that already has it keeps its own share and only loses the "if it fits" flag; one that
    does not gets the slot appended with the share and hours from `extra` (data, per role), and the
    other shares shrink to make room.
    """
    role = str(extra["role"])
    out: list[Template] = []
    for template in templates:
        slots = list(template.slots)
        at = next((i for i, s in enumerate(slots) if s.course_role == role), None)
        if at is not None:
            slots[at] = replace(slots[at], is_optional=False)
        else:
            share = float(extra["share"])
            slots = [replace(s, budget_share=s.budget_share * (1.0 - share)) for s in slots]
            slots.append(
                Slot(
                    position=max((s.position for s in slots), default=0) + 1,
                    course_role=role,
                    budget_share=share,
                    earliest_start_min=extra.get("earliest_start_min"),
                    latest_start_min=extra.get("latest_start_min"),
                    min_slot_budget=extra.get("min_slot_budget"),
                )
            )
        out.append(replace(template, slots=tuple(slots)))
    return out


def assign_buzz(candidates: Iterable[PlaceCandidate], radius_m: float = BUZZ_RADIUS_M) -> None:
    """Sets `buzz` ∈ [0, 1] on every candidate from how many other candidates stand within `radius_m`."""
    unique = {(c.is_event, c.id): c for c in candidates}
    places = list(unique.values())
    if len(places) < 2:
        return
    lat0 = sum(p.point.lat for p in places) / len(places)
    m_per_deg_lng = _M_PER_DEG_LAT * math.cos(math.radians(lat0))

    def xy(p: PlaceCandidate) -> tuple[float, float]:
        return p.point.lng * m_per_deg_lng, p.point.lat * _M_PER_DEG_LAT

    grid: dict[tuple[int, int], list[tuple[float, float]]] = {}
    coords = [xy(p) for p in places]
    for x, y in coords:
        grid.setdefault((int(x // radius_m), int(y // radius_m)), []).append((x, y))
    r2 = radius_m * radius_m
    counts = []
    for x, y in coords:
        cx, cy = int(x // radius_m), int(y // radius_m)
        near = sum(
            1
            for dx in (-1, 0, 1)
            for dy in (-1, 0, 1)
            for ox, oy in grid.get((cx + dx, cy + dy), ())
            if (ox - x) ** 2 + (oy - y) ** 2 <= r2
        )
        counts.append(near - 1)  # not itself
    top = sorted(counts)[min(len(counts) - 1, int(len(counts) * BUZZ_SATURATION_PCTL))]
    for place, count in zip(places, counts, strict=True):
        place.buzz = min(1.0, count / top) if top > 0 else 0.0
