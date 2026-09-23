"""Anchor-based day planning (docs/34): the place a day is planned around.

A destination context is only a new *input* to the recommendation engine — never a separate recommender.
The strategy reads a few knobs from `data/recommendation/anchor_contexts.json`:

* how far the day may reach (campus ring · nearby streets · the wider area, scaled by transport),
* whether the campus itself is a stop (a walk around it: free, a real place, so saving / sharing work),
* whether a festival that day is the core slot, a welcome extra, or ignored.

Only UNIVERSITY (with the FESTIVAL inside it) is implemented; the enum names what is meant to follow.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from datetime import date
from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from app.domain.models import GeoPoint, Slot, Template

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
ANCHOR_CONTEXTS_PATH = DATA_DIR / "recommendation" / "anchor_contexts.json"

CampusStop = Literal["required", "optional", "none"]
FestivalMode = Literal["core", "if_any", "none"]
Reach = Literal["campus", "nearby", "extended"]


class DestinationContext(StrEnum):
    GENERAL_AREA = "general_area"  # a district / neighbourhood (region)
    SPECIFIC_PLACE = "specific_place"  # a station or a place (origin)
    UNIVERSITY = "university"  # a campus as the anchor of the day
    FESTIVAL = "festival"  # a university day whose core slot is that day's festival
    # later, on the same seam: CONCERT · SPORTS · ATTRACTION · PARK · MUSEUM · THEME_PARK


@dataclass(frozen=True, slots=True)
class Anchor:
    kind: Literal["university"]
    id: str  # the campus place's public id
    place_id: int
    name: str
    point: GeoPoint
    address: str | None = None


@dataclass(frozen=True, slots=True)
class AnchorPlan:
    """What the anchor changes for one purpose: the engine's own knobs, nothing new."""

    intents: tuple[str, ...]
    campus_stop: CampusStop
    festival: FestivalMode
    radius_m: int
    campus_radius_m: int


@dataclass(frozen=True, slots=True)
class AnchoredEvent:
    id: int
    title: str
    starts_on: date
    ends_on: date
    start_time: str | None
    end_time: str | None
    priority: int
    anchored: bool  # linked to this campus (an admin-entered university festival), not merely nearby
    distance_m: float


@lru_cache(maxsize=1)
def anchor_rules(path: Path = ANCHOR_CONTEXTS_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def university_rules() -> dict[str, Any]:
    return dict(anchor_rules()["university"])


def context_purposes() -> frozenset[str]:
    """Purposes that only make sense around a campus ("캠퍼스 탐방"): hidden from the plain purpose list."""
    return frozenset(str(code) for code in university_rules().get("context_purposes", []))


def plan_for(purpose_code: str, transport: str) -> AnchorPlan:
    rules = university_rules()
    entry = dict(rules["purposes"].get(purpose_code) or rules["purposes"]["_default"])
    reach = str(entry.get("reach", "nearby"))
    scale = float(rules.get("transport_scale", {}).get(transport, 1.0))
    radius = int(float(rules["rings_m"][reach]) * scale)
    return AnchorPlan(
        intents=tuple(str(i) for i in entry.get("intents", [])),
        campus_stop=entry.get("campus_stop", "optional"),
        festival=entry.get("festival", "if_any"),
        radius_m=radius,
        campus_radius_m=int(rules.get("campus_radius_m", 700)),
    )


def campus_first(templates: list[Template], share: float = 0.02) -> list[Template]:
    """The campus walk opens the day (docs/34 §6: campus → meal → café …). A template that already has a
    sight slot keeps it (now certain); one that has none gets a small free slot in front of everything."""
    out: list[Template] = []
    for template in templates:
        slots = list(template.slots)
        at = next((i for i, s in enumerate(slots) if s.course_role == "ATTRACTION"), None)
        if at is not None:
            slots[at] = replace(slots[at], is_optional=False)
        else:
            slots = [
                replace(s, position=s.position + 1, budget_share=s.budget_share * (1.0 - share))
                for s in slots
            ]
            first = min((s.position for s in slots), default=1) - 1
            slots.insert(0, Slot(position=first, course_role="ATTRACTION", budget_share=share))
        out.append(replace(template, slots=tuple(slots)))
    return out


def pick_festival(events: list[AnchoredEvent]) -> AnchoredEvent | None:
    """The day's festival: one linked to this campus beats one that merely happens nearby; then priority;
    then the closer one. None when there is nothing that day (the day falls back to the campus)."""
    if not events:
        return None
    return min(events, key=lambda e: (not e.anchored, -e.priority, e.distance_m))


def festival_missing_warning() -> dict[str, Any]:
    entry = dict(university_rules().get("festival_missing") or {})
    return {"code": entry.get("code", "FESTIVAL_NOT_FOUND"), "detail": str(entry.get("detail", ""))}


def hhmm_to_min(value: str | None) -> int | None:
    if not value:
        return None
    try:
        hours, minutes = value.split(":", 1)
        total = int(hours) * 60 + int(minutes)
    except ValueError:
        return None
    return total if 0 <= total <= 48 * 60 else None


def event_window(start_time: str | None, end_time: str | None) -> tuple[int, int] | None:
    """(open_min, close_min) of the day for an event with hours; an end before the start runs past midnight.
    None without both (the date alone counts, as before)."""
    start, end = hhmm_to_min(start_time), hhmm_to_min(end_time)
    if start is None or end is None:
        return None
    if end <= start:
        end += 24 * 60
    return start, end
