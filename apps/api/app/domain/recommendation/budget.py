"""Template selection, slot budget allocation, optional-slot dropping and carry-over (doc 06 §1, §5)."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from functools import lru_cache
from pathlib import Path

from app.domain.models import BudgetTooLowError, NoTemplateError, Slot, Template

FULLDAY_MIN_DURATION = 330  # "반나절"(6h) and up; a 4-stop band template tops out around 4.5h
FULLDAY_LATEST_START_H = 15
MIN_STAY_INSIDE_WINDOW = 45  # a gated slot must open at least this long before the window closes
NIGHT_FROM_H = 21  # kitchens close around 21:30: from here on it is a night out, not a dinner
NIGHT_UNTIL_H = 5
SLOT_MIN_PER_STOP = 60  # a stop (stay + getting there) needs about an hour of the meeting window


@dataclass(frozen=True, slots=True)
class SlotBudget:
    slot: Slot
    share: float  # renormalized share
    budget: float  # per-person target b_s


def is_night(start_at: datetime) -> bool:
    return start_at.hour >= NIGHT_FROM_H or start_at.hour < NIGHT_UNTIL_H


NIGHT_WRAP_MIN = 24 * 60 + 30  # a night out without a set end wraps up around half past midnight
NIGHT_WINDOW_MIN, NIGHT_WINDOW_MAX = 120, 180


def night_window(start_at: datetime) -> int | None:
    """How long a night out runs when the user left the end open (docs/48): until about 00:30, two to
    three hours. A 21:30 start used to run the whole night template and end at 01:30 or later."""
    if not is_night(start_at):
        return None
    left = NIGHT_WRAP_MIN - evening_minute(start_at)
    return max(NIGHT_WINDOW_MIN, min(NIGHT_WINDOW_MAX, left))


def soft_window(start_at: datetime, end_min: int | None, floor: int = 90) -> int | None:
    """Minutes from the start to an evening end the company sets (end_min = minutes since midnight)."""
    if end_min is None:
        return None
    left = end_min - evening_minute(start_at)
    return max(floor, left) if left < 12 * 60 else None


def evening_minute(at: datetime) -> int:
    """Minutes since midnight, where the small hours belong to the evening before: 01:00 is 1500, not 60.
    A rule such as "a drink, from 17:00" (1020) must still hold at 1 a.m. — 00:01 is not a morning."""
    minute = at.hour * 60 + at.minute
    return minute + 24 * 60 if at.hour < NIGHT_UNTIL_H else minute


def time_band_for(start_at: datetime, duration_min: int | None) -> str:
    hour = start_at.hour + start_at.minute / 60
    if is_night(start_at):
        return "night"
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


SLOT_FLOORS_PATH = Path(__file__).resolve().parents[3] / "data" / "recommendation" / "slot_floors.json"


@dataclass(frozen=True, slots=True)
class SlotFloors:
    per_person: Mapping[str, float]  # role → what a stop of that kind costs a head, where one sits down
    max_share: float = 0.25  # a floor never takes more than this share of the budget
    yield_to: frozenset[str] = frozenset()  # a short slot's day is also tried without it, for these


@lru_cache(maxsize=1)
def slot_floors(path: Path = SLOT_FLOORS_PATH) -> SlotFloors:
    if not path.exists():
        return SlotFloors({})
    data = json.loads(path.read_text(encoding="utf-8"))
    return SlotFloors(
        {str(k): float(v) for k, v in (data.get("per_person") or {}).items() if not str(k).startswith("_")},
        float(data.get("max_share", 0.25)),
        frozenset(str(r) for r in data.get("yield_to") or ()),
    )


def without_short(
    template: Template,
    budget_per_person: float,
    include_roles: Sequence[str] | None = None,
    floors: SlotFloors | None = None,
) -> Template | None:
    """The same day without the slots whose share buys less than their floor — offered only when a slot
    they yield to (a bar) is planned too. 27,000원 a head buys dinner and a bar, or dinner and a café worth
    the name, not all three: with the café lifted to its floor the friends' evening lost its second round in
    4 of 13 courses. None when nothing is short or nothing to yield to."""
    f = floors or slot_floors()
    if not f.yield_to:
        return None
    plain = allocate(template, budget_per_person, include_roles, floors=SlotFloors({}))
    short = {
        sb.slot.position
        for sb in plain
        if (floor := f.per_person.get(sb.slot.course_role))
        and 0 < sb.budget < min(floor, f.max_share * budget_per_person)
    }
    if not short or not any(
        sb.slot.course_role in f.yield_to for sb in plain if sb.slot.position not in short
    ):
        return None
    return replace(template, slots=tuple(s for s in template.slots if s.position not in short))


MANDATORY_KEEP = 0.8  # any other slot gives at most a fifth of its plan to a floor (optional: to its minimum)


def with_floors(
    slots: Sequence[Slot], budget_per_person: float, floors: SlotFloors | None = None
) -> list[Slot]:
    """A café costs what a café costs (docs/59 #4). The friends' evening gave its café 10% of 27,000원 —
    2,700원, under the price cap of every café but a 2,000원 chain, so 54% of those cafés were one.
    A slot whose share buys less than its floor gets the floor (at most `max_share` of the budget), paid for
    by the other paid slots in proportion — an optional slot never below its own minimum (it would be
    dropped), one that must be there never below `MANDATORY_KEEP` of its plan. Not enough room: as planned.
    Shares only (of the slots that will be planned): every later step renormalizes from them."""
    f = floors or slot_floors()
    total = sum(s.budget_share for s in slots)
    if not f.per_person or total <= 0 or budget_per_person <= 0:
        return list(slots)
    shares = {s.position: s.budget_share / total for s in slots}
    wanted: dict[int, float] = {}
    for s in slots:
        floor = f.per_person.get(s.course_role)
        if floor and shares[s.position] > 0:  # a free slot (a walk) stays free
            want = min(floor / budget_per_person, f.max_share)
            if shares[s.position] < want:
                wanted[s.position] = want
    if not wanted:
        return list(slots)
    need = sum(w - shares[p] for p, w in wanted.items())
    room = {
        s.position: shares[s.position]
        - (
            s.min_slot_budget / budget_per_person
            if s.is_optional and s.min_slot_budget
            else shares[s.position] * MANDATORY_KEEP
        )
        for s in slots
        if s.position not in wanted and shares[s.position] > 0
    }
    room = {p: r for p, r in room.items() if r > 0}
    if sum(room.values()) < need:
        return list(slots)  # too small a budget for a café worth the name: the plan as it was
    give = need / sum(room.values())
    new = {p: wanted.get(p, shares[p] - room.get(p, 0.0) * give) for p in shares}
    return [replace(s, budget_share=new[s.position]) for s in slots]


def _normalize(slots: Sequence[Slot]) -> list[tuple[Slot, float]]:
    total = sum(s.budget_share for s in slots)
    if total <= 0:
        return [(s, 0.0) for s in slots]
    return [(s, s.budget_share / total) for s in slots]


def allocate(
    template: Template,
    budget_per_person: float,
    include_roles: Sequence[str] | None = None,
    floors: SlotFloors | None = None,
) -> list[SlotBudget]:
    """b_s = b × share. Optional slots whose b_s falls below their `min_slot_budget` are dropped
    from the back and the remaining shares renormalized. Share-0 (free) slots stay at 0. Then a slot
    whose share buys less than a stop of its kind costs is lifted to its floor (`with_floors`)."""
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
    slots = with_floors(slots, budget_per_person, floors)
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
    keep_roles: frozenset[str] = frozenset(),
) -> tuple[list[SlotBudget], list[Slot]]:
    """Trim the template to the requested window instead of squeezing every stay (doc 06 §1).

    First go slots that cannot even begin inside the window (an 11:00–17:00 plan has no use for a
    dinner slot gated at 17:00). Then optional slots (from the back), then the slot with the smallest
    budget share — the biggest-share slot (the point of the meeting, usually the meal) is never
    dropped. Freed shares are renormalized over what remains. Returns (kept, dropped).

    `keep_roles`: roles that are the point of this leg whatever their share (the sight of a
    whole-city trip costs nothing, so by share alone it was the first to go)."""
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
        free = [sb for sb in kept if sb.slot.course_role not in keep_roles] or kept
        optional = [sb for sb in free if sb.slot.is_optional]
        if optional:
            victim = max(optional, key=lambda sb: sb.slot.position)
        else:
            anchor = max(kept, key=lambda sb: (sb.share, -sb.slot.position))
            others = [sb for sb in free if sb is not anchor] or [sb for sb in kept if sb is not anchor]
            victim = min(others, key=lambda sb: (sb.share, -sb.slot.position))
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
