"""One day across several neighbourhoods.

Each neighbourhood is planned by the ordinary engine as a leg of its own; this module decides what
each leg gets and joins the legs into one course. Money and time are handed forward: what a leg does
not spend is the next leg's to use, and the next leg starts when the previous one ends plus the ride
between them. The ride becomes the first stop's "from previous" so the timeline and the totals count
it like any other move.

Opinions (how long a leg is when the user gave no meeting length, how fast a hop is, how many
neighbourhoods fit in a day) live in `data/recommendation/multi_region.json`.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.domain.models import CourseResult, GeoPoint, StopResult
from app.domain.routing.travel_time import DETOUR_FACTOR, SPEED_KMH, haversine_m

RULES_PATH = Path(__file__).resolve().parents[3] / "data" / "recommendation" / "multi_region.json"


@lru_cache(maxsize=1)
def itinerary_rules(path: Path = RULES_PATH) -> dict[str, Any]:
    defaults: dict[str, Any] = {
        "max_regions": 3,
        "leg_default_min": 180,
        "leg_min_min": 90,
        "walk_hop_max_m": 1500,
        "hop_mode": "transit",
        "hop_overhead_min": {"walk": 0, "transit": 10, "car": 8},
        "budget_round": 1000,
        "max_nights": 3,
        "day_start_min": 600,
        "day_end_min": 1320,
        "full_day_min": 540,
        "first_day_floor_min": 120,
    }
    if path.exists():
        defaults.update(
            {k: v for k, v in json.loads(path.read_text(encoding="utf-8")).items() if k[0] != "_"}
        )
    return defaults


@dataclass(frozen=True, slots=True)
class Hop:
    """The move from the last stop of one neighbourhood into the next neighbourhood."""

    mode: str
    minutes: int
    distance_m: int


def hop_between(a: GeoPoint, b: GeoPoint, transport: str, rules: Mapping[str, Any]) -> Hop:
    """Close enough is walked; otherwise the user's own transport, or public transit for a walker."""
    straight = haversine_m(a, b)
    if straight <= float(rules["walk_hop_max_m"]):
        mode = "walk"
    else:
        mode = transport if transport != "walk" else str(rules["hop_mode"])
    path_m = straight * DETOUR_FACTOR[mode]
    overhead = float(rules["hop_overhead_min"].get(mode, 0))  # waiting for the bus, parking the car
    minutes = path_m / 1000.0 / SPEED_KMH[mode] * 60.0 + overhead
    return Hop(mode=mode, minutes=max(1, round(minutes)), distance_m=round(path_m))


def leg_budget(remaining: int, legs_left: int, rules: Mapping[str, Any]) -> int:
    """An even share of what is left, so an under-spent first neighbourhood enriches the next."""
    unit = int(rules["budget_round"])
    share = remaining / max(1, legs_left)
    return max(unit, int(share // unit) * unit)


def leg_minutes(remaining_min: int | None, legs_left: int, rules: Mapping[str, Any]) -> int:
    if remaining_min is None:
        return int(rules["leg_default_min"])
    return max(int(rules["leg_min_min"]), remaining_min // max(1, legs_left))


def merge_legs(legs: Sequence[CourseResult], hops: Sequence[Hop]) -> tuple[CourseResult, dict[int, Hop]]:
    """Joins the legs in order. `hops[k]` leads into `legs[k + 1]`. Returns the course and, by stop
    position, the hop that precedes it (so the view can show "대중교통 18분" instead of a walk)."""
    stops: list[StopResult] = []
    hop_at: dict[int, Hop] = {}
    for k, leg in enumerate(legs):
        for i, stop in enumerate(leg.stops):
            position = len(stops) + 1
            if k > 0 and i == 0:
                hop = hops[k - 1]
                hop_at[position] = hop
                # the ride plus the walk from where it drops you to the door
                stop = replace(
                    stop,
                    travel_min_from_prev=hop.minutes + stop.travel_min_from_prev,
                    distance_m_from_prev=hop.distance_m + stop.distance_m_from_prev,
                )
            stops.append(replace(stop, position=position))
    first = legs[0]
    span = stops[-1].leave_at - stops[0].arrive_at
    merged = replace(
        first,
        stops=stops,
        total_price=sum(s.est_price for s in stops),
        total_travel_min=sum(s.travel_min_from_prev for s in stops),
        total_distance_m=sum(s.distance_m_from_prev for s in stops),
        duration_min=int(span.total_seconds() // 60) + stops[0].travel_min_from_prev,
        score=sum(leg.score for leg in legs) / len(legs),
        objective=sum(leg.objective for leg in legs),
        warnings=[w for leg in legs for w in leg.warnings],
    )
    return merged, hop_at


def day_weights(start_min: int, days: int, rules: Mapping[str, Any]) -> list[int]:
    """Minutes each day of a trip has to spend money in: the first day from the meeting time to the end
    of the day, the others a whole day. The budget is split in this proportion."""
    whole = int(rules["day_end_min"]) - int(rules["day_start_min"])
    first = max(int(rules["first_day_floor_min"]), int(rules["day_end_min"]) - start_min)
    return [min(first, whole), *([whole] * (days - 1))]


def day_budget(remaining: int, weights: Sequence[int], day: int, rules: Mapping[str, Any]) -> int:
    """This day's share of what is left, by time available. The last day takes all that remains."""
    unit = int(rules["budget_round"])
    ahead = sum(weights[day:])
    share = remaining if day == len(weights) - 1 else remaining * weights[day] / max(1, ahead)
    return max(unit, int(share // unit) * unit)


def regions_by_day(slugs: Sequence[str], days: int) -> list[list[str]]:
    """Which neighbourhoods each day covers: in order, as evenly as they divide; with fewer
    neighbourhoods than days they come round again."""
    if not slugs:
        return [[] for _ in range(days)]
    if len(slugs) <= days:
        return [[slugs[d % len(slugs)]] for d in range(days)]
    size, extra = divmod(len(slugs), days)
    out: list[list[str]] = []
    at = 0
    for d in range(days):
        take = size + (1 if d < extra else 0)
        out.append(list(slugs[at : at + take]))
        at += take
    return out
