"""꼭 들를 곳 (docs/51 B1 · docs/59 #7): the errand is a leg of the day, not a note beside it.

먼저 들르기 — the user comes from the errand: the ride from it to the first stop is a leg like the others
(the map draws it, the page gives its minutes). 끝나고 들르기 — the user goes on to it: the day should end on
the side of the errand, not on the stop furthest from it, and the ride from the last stop is shown the same.

Pure: plain points in, numbers out — the engine, the page and the scorecard all read it from here.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from app.domain.models import GeoPoint
from app.domain.recommendation.itinerary import Hop, hop_between
from app.domain.routing.travel_time import haversine_m

# 끝나고 들르기: each km the last stop lies further from the errand than the course's stop nearest to it costs
# this much of the day objective (a clearly better place is about 0.1) — never more than END_PULL_CAP, so a
# good day in the other corner of the neighbourhood still beats a poor one next to the errand
END_PULL_PER_KM = 0.06
END_PULL_CAP = 0.15
# a last stop this close to the course's nearest one already heads the right way (the other side of a block)
TOWARD_SLACK_M = 300.0
# an errand this close to a stop is that stop (one of ours, pinned, or the same door by another name)
SAME_PLACE_M = 60.0


def away_m(points: Sequence[GeoPoint], end: GeoPoint) -> float:
    """How much further from `end` the last point is than the point of the course nearest to it (≥ 0)."""
    if not points:
        return 0.0
    dists = [haversine_m(p, end) for p in points]
    return max(0.0, dists[-1] - min(dists))


def end_pull(points: Sequence[GeoPoint], end: GeoPoint) -> float:
    """The objective's penalty for a course (or a course so far) that ends heading away from the errand
    the user goes to next. Relative to the course's own nearest stop, so it moves the ending, not the day."""
    return min(END_PULL_CAP, END_PULL_PER_KM * away_m(points, end) / 1000.0)


def heads_toward(points: Sequence[GeoPoint], end: GeoPoint, slack_m: float = TOWARD_SLACK_M) -> bool:
    return away_m(points, end) <= slack_m


def errand_leg(
    errand: GeoPoint,
    when: str,
    stops: Sequence[GeoPoint],
    transport: str,
    rules: Mapping[str, Any],
) -> Hop | None:
    """The ride between the errand and the course: from it to the first stop (before), from the last stop
    to it (after). None when there is no course, or when the errand is itself one of the stops."""
    if not stops or any(haversine_m(errand, p) <= SAME_PLACE_M for p in stops):
        return None
    if when == "after":
        return hop_between(stops[-1], errand, transport, rules)
    return hop_between(errand, stops[0], transport, rules)
