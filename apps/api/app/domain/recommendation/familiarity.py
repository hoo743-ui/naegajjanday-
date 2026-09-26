"""처음 오는 사람 · 자주 오는 사람 (founder 2026-09-26, docs/59 #1).

The same neighbourhood asks two questions. A first visit: "what is this place known for?" — today's
behaviour, the draws and the signature pull hard. A regular: "what haven't I done here yet?" — the pull of
the well-known is taken down, the specialty is not claimed unasked, places they have been are left out, and
newly opened places and lesser-known independents are pulled toward instead. Every other rule (scenes,
night, budget, chains) stays as it is. The knobs are data (data/recommendation/familiarity.json).
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.domain.models import PlaceCandidate, RequestContext

FAMILIARITY_PATH = Path(__file__).resolve().parents[3] / "data" / "recommendation" / "familiarity.json"
FIRST, REGULAR = "first", "regular"


@dataclass(frozen=True, slots=True)
class RegularRules:
    local_pull: float = 0.0
    draw_pull: float = 0.0
    known_scale: float = 0.3  # how much the `curated` feature (listed · visited · signature) still counts
    auto_focus: bool = False
    new_days: int = 730  # licensed within this many days before the day = newly opened
    new_pull: float = 0.1
    lesser_known_pull: float = 0.06
    not_independent_tags: frozenset[str] = frozenset()
    known_popularity: float = 0.0  # a measured navigation rank above this = a place everyone goes to


@dataclass(frozen=True, slots=True)
class FamiliarityRules:
    window_days: int = 180
    min_days: int = 2
    max_been_places: int = 300
    regular: RegularRules = RegularRules()
    opened_on_sources: Mapping[str, str] | None = None  # provider → key in place_source.raw


@lru_cache(maxsize=1)
def familiarity_rules(path: Path = FAMILIARITY_PATH) -> FamiliarityRules:
    if not path.exists():
        return FamiliarityRules()
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    infer = data.get("infer") or {}
    reg = {k: v for k, v in (data.get("regular") or {}).items() if k in RegularRules.__dataclass_fields__}
    if "not_independent_tags" in reg:
        reg["not_independent_tags"] = frozenset(reg["not_independent_tags"])
    found = (data.get("opened_on_sources") or {}).items()
    sources = {str(k): str(v) for k, v in found if not str(k).startswith("_")}
    return FamiliarityRules(
        window_days=int(infer.get("window_days", 180)),
        min_days=int(infer.get("min_days", 2)),
        max_been_places=int(infer.get("max_been_places", 300)),
        regular=RegularRules(**reg),
        opened_on_sources=sources,
    )


def infer(visit_days: Iterable[date], rules: FamiliarityRules | None = None) -> str:
    """Regular when the user planned a day here on at least `min_days` different days (the caller has
    already kept only the window): a reroll on the same day is the same visit."""
    r = rules or familiarity_rules()
    return REGULAR if len(set(visit_days)) >= r.min_days else FIRST


def parse_opened_on(raw: Mapping[str, Any] | None, key: str) -> date | None:
    """ "2024-03-02" (or "20240302") from a licence record; anything else is no date."""
    value = str((raw or {}).get(key) or "").strip()
    digits = value.replace("-", "").replace(".", "")[:8]
    if len(digits) != 8 or not digits.isdigit():
        return None
    try:
        return date(int(digits[:4]), int(digits[4:6]), int(digits[6:8]))
    except ValueError:
        return None


def is_regular(ctx: RequestContext) -> bool:
    return ctx.familiarity == REGULAR


def independent(place: PlaceCandidate, rules: RegularRules) -> bool:
    """A place of its own: not a chain branch nor an unmanned shop (a new Mega Coffee is not news)."""
    return not place.is_event and not any(place.tags.get(t) for t in rules.not_independent_tags)


def newly_opened(place: PlaceCandidate, on: date | datetime, rules: RegularRules) -> bool:
    """An independent licensed within `new_days` before the day (인허가일자, where the data has it)."""
    day = on.date() if isinstance(on, datetime) else on
    return (
        place.opened_on is not None
        and 0 <= (day - place.opened_on).days <= rules.new_days
        and independent(place, rules)
    )


def lesser_known(place: PlaceCandidate, rules: RegularRules) -> bool:
    """An independent few would call a destination: not listed or vouched for by a public body, not among
    the measured navigation destinations, not what the neighbourhood is known for."""
    return (
        independent(place, rules)
        and not place.is_curated
        and place.popularity <= rules.known_popularity
        and place.local_score <= 0
    )


def novelty_pull(place: PlaceCandidate, ctx: RequestContext) -> float:
    """What a regular is pulled toward, added to the place score as it stands (not a feature of its own,
    so the breakdown the page explains stays the same). Zero on a first visit."""
    if not is_regular(ctx):
        return 0.0
    rules = familiarity_rules().regular
    if newly_opened(place, ctx.start_at, rules):
        return rules.new_pull
    if lesser_known(place, rules):
        return rules.lesser_known_pull
    return 0.0


def novel(place: PlaceCandidate, on: date | datetime, rules: RegularRules | None = None) -> bool:
    """New to a regular: a newly opened independent, or a lesser-known one (what the scorecard counts)."""
    r = rules or familiarity_rules().regular
    return newly_opened(place, on, r) or lesser_known(place, r)


def mark_opened(candidates: Sequence[PlaceCandidate], opened: Mapping[int, date]) -> None:
    for cand in candidates:
        if not cand.is_event and cand.id in opened:
            cand.opened_on = opened[cand.id]
