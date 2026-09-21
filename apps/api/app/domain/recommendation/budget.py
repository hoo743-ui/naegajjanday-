"""Template selection, slot budget allocation, optional-slot dropping and carry-over (doc 06 §1, §5)."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import datetime

from app.domain.models import BudgetTooLowError, NoTemplateError, Slot, Template

FULLDAY_MIN_DURATION = 330  # "반나절"(6h) and up; a 4-stop band template tops out around 4.5h
FULLDAY_LATEST_START_H = 15
MIN_STAY_INSIDE_WINDOW = 45  # a gated slot must open at least this long before the window closes
SLOT_MIN_PER_STOP = 60  # a stop (stay + getting there) needs about an hour of the meeting window


@dataclass(frozen=True, slots=True)
class SlotBudget:
    slot: Slot
    share: float  # renormalized share
    budget: float  # per-person target b_s


def time_band_for(start_at: datetime, duration_min: int | None) -> str:
    hour = start_at.hour + start_at.minute / 60
    # fullday = lunch … dinner. A long window that starts in the late afternoon has room for one
    # meal only, so it stays on its own band (an 18:00–24:00 plan must not get two dinners).
    if duration_min is not None and duration_min >= FULLDAY_MIN_DURATION and hour < FULLDAY_LATEST_START_H:
        return "fullday"
    if hour < 14:
        return "lunch"
    if hour < 17:
        return "afternoon"
    return "evening"


def select_template(
    templates: Sequence[Template], *, time_band: str, party_size: int, budget_per_person: float
) -> Template:
    """Pick the richest affordable template, preferring an exact time-band match."""
    fits_party = [t for t in templates if t.party_min <= party_size <= t.party_max] or list(templates)
    if not fits_party:
        raise NoTemplateError("no template for purpose")
    affordable = [t for t in fits_party if t.min_budget_per_person <= budget_per_person]
    if not affordable:
        in_band = [t for t in fits_party if t.time_band == time_band] or fits_party
        floor = min(t.min_budget_per_person for t in in_band)
        raise BudgetTooLowError(min_budget=int(math.ceil(floor * party_size / 1000.0) * 1000))
    in_band = [t for t in affordable if t.time_band == time_band]
    pool = in_band or [t for t in affordable if t.time_band != "fullday"] or affordable
    return max(pool, key=lambda t: (t.min_budget_per_person, -t.id))


def _normalize(slots: Sequence[Slot]) -> list[tuple[Slot, float]]:
    total = sum(s.budget_share for s in slots)
    if total <= 0:
        return [(s, 0.0) for s in slots]
    return [(s, s.budget_share / total) for s in slots]


def allocate(
    template: Template, budget_per_person: float, include_roles: Sequence[str] | None = None
) -> list[SlotBudget]:
    """b_s = b × share. Optional slots whose b_s falls below their `min_slot_budget` are dropped
    from the back and the remaining shares renormalized. Share-0 (free) slots stay at 0."""
    slots = [s for s in template.slots if not include_roles or s.course_role in include_roles]
    if not slots:
        slots = list(template.slots)
    while True:
        shares = _normalize(slots)
        victim = next(
            (
                s
                for s, share in reversed(shares)
                if s.is_optional and s.min_slot_budget and budget_per_person * share < s.min_slot_budget
            ),
            None,
        )
        if victim is None or len(slots) <= 1:
            break
        slots = [s for s in slots if s is not victim]
    return [
        SlotBudget(slot=s, share=share, budget=budget_per_person * share) for s, share in _normalize(slots)
    ]


def drop_slot(
    slot_budgets: Sequence[SlotBudget], position: int, budget_per_person: float
) -> list[SlotBudget]:
    """Remove one slot (e.g. no candidates) and hand its share to the others."""
    rest = [sb.slot for sb in slot_budgets if sb.slot.position != position]
    return [SlotBudget(slot=s, share=sh, budget=budget_per_person * sh) for s, sh in _normalize(rest)]


def max_slots_for(duration_min: int, per_stop_min: float = SLOT_MIN_PER_STOP) -> int:
    """How many stops fit a meeting window: about one per hour (stay + transfer), at least one."""
    return max(1, round(duration_min / per_stop_min))


def fit_to_duration(
    slot_budgets: Sequence[SlotBudget],
    duration_min: int | None,
    budget_per_person: float,
    per_stop_min: float = SLOT_MIN_PER_STOP,
    start_min: int | None = None,
) -> tuple[list[SlotBudget], list[Slot]]:
    """Trim the template to the requested window instead of squeezing every stay (doc 06 §1).

    First go slots that cannot even begin inside the window (an 11:00–17:00 plan has no use for a
    dinner slot gated at 17:00). Then optional slots (from the back), then the slot with the smallest
    budget share — the biggest-share slot (the point of the meeting, usually the meal) is never
    dropped. Freed shares are renormalized over what remains. Returns (kept, dropped)."""
    kept = list(slot_budgets)
    dropped: list[Slot] = []
    if duration_min is None:
        return kept, dropped
    if start_min is not None:
        last_start = start_min + duration_min - MIN_STAY_INSIDE_WINDOW
        for sb in list(kept):
            gate = sb.slot.earliest_start_min
            if gate is not None and gate > last_start and len(kept) > 1:
                dropped.append(sb.slot)
                kept = drop_slot(kept, sb.slot.position, budget_per_person)
    limit = max_slots_for(duration_min, per_stop_min)
    while len(kept) > limit:
        optional = [sb for sb in kept if sb.slot.is_optional]
        if optional:
            victim = max(optional, key=lambda sb: sb.slot.position)
        else:
            anchor = max(kept, key=lambda sb: (sb.share, -sb.slot.position))
            victim = min(
                (sb for sb in kept if sb is not anchor), key=lambda sb: (sb.share, -sb.slot.position)
            )
        dropped.append(victim.slot)
        kept = drop_slot(kept, victim.slot.position, budget_per_person)
    return kept, dropped


def carry_over(planned: Sequence[float], spent: Sequence[float]) -> float:
    """Money saved (or overspent, negative) by earlier slots, to be added to the next slot's b_s."""
    return sum(planned) - sum(spent)


def effective_budget(slot_budget: float, carry: float) -> float:
    return max(0.0, slot_budget + carry)


def reposition(slots: Sequence[Slot]) -> list[Slot]:
    return [replace(s, position=i + 1) for i, s in enumerate(slots)]
