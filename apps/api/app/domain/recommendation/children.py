"""아이 수 (창업자 2026-09-27 "4 아이 인원 받자", docs/64 R18).

The wizard asks how many of the party are children when the day is 가족 · 아이와; the request carries it as
`children` (optional). Absent, nothing changes: tickets assume the scene's split (recommendation.ticketed
party_of) and the scene's own rules hold. Present:

- admission = adults × adult price + children × child price (ticketed.price, the card shows the split);
- more than 0 children is a day with children whatever the purpose or scene: no bar slot (a drink asked
  for is not added — it is said why), no place tagged 술자리 in any stop (the 어른끼리 scene's allowance does
  not hold), and the evening ends by the kids scene's hour (scenes.json › family › kids: end_by, and a night
  start is moved to that evening — earlier_start). The kids scene is the one the ticket rule names
  (ticketed_venues.json › party.child_scenes), so both read the same place.
"""

from __future__ import annotations

from typing import Any

from app.domain.models import RequestContext
from app.domain.recommendation.style import resolve_scene
from app.domain.recommendation.ticketed import ticketed_venues

DRINK_TAG = "술자리"
VETO_ROLES = frozenset({"BAR"})
# every course role a stop can have (data/seed/categories.json) — the drink tag is kept out of each
ALL_ROLES = frozenset(
    {"MEAL", "CAFE", "DESSERT", "BAR", "ATTRACTION", "ACTIVITY", "CULTURE", "NIGHTVIEW", "STAY"}
)


def with_children(children: int | None) -> bool:
    return children is not None and children > 0


def child_scene() -> dict[str, Any]:
    """The scene the ticket rule reads as "with children" (가족 › 아이와): its end_by and earlier_start."""
    for purpose, scenes in ticketed_venues().party.child_scenes.items():
        for code in sorted(scenes):
            key, scene = resolve_scene(purpose, code)
            if key == code:
                return scene
    return {}


def vetoed_for(children: int | None) -> frozenset[str]:
    """Course roles a day with children never has (the bar)."""
    return VETO_ROLES if with_children(children) else frozenset()


def apply_children(ctx: RequestContext, children: int | None) -> None:
    """Record the asked head count on the context; with children, the kids rules on top of whatever the
    purpose and scene already set. Run after the scene (the 어른끼리 allowance must not undo it)."""
    ctx.children = children
    if not with_children(children):
        return
    ctx.never_tags_by_role[DRINK_TAG] = ctx.never_tags_by_role.get(DRINK_TAG, frozenset()) | ALL_ROLES
    end_by = child_scene().get("end_by")
    if end_by:
        hh, mm = (int(x) for x in str(end_by).split(":"))
        minute = hh * 60 + mm
        ctx.soft_end_min = minute if ctx.soft_end_min is None else min(ctx.soft_end_min, minute)
