"""이동 모드 M1 · M2 · M3 (docs/65 §2 · §6): how far the day goes, as a promise the engine keeps.

- M1 `inside` 역 안에서: every stop within R1 of the anchor (straight line), every leg on foot and
  within the walk limit.
- M2 `around` 역 주변 돌아보기 (the default): every stop within R2 of the anchor; a leg on foot over the
  limit is taken by public transit instead, once per course; a second one throws that combination away.
- M3 `onward` 다른 역으로 넘어가기: A's cluster, one hop, B's cluster; each cluster keeps M2 around its
  own anchor, and every stop is nearer its own anchor than the other one (nothing after the hop is on A's
  side).

The anchor is the station the user picked (or the neighbourhood's centre) — never the point the engine moves
its own origin to (`_settle_on_foot`, `_recenter_on_wanted`). The first leg (anchor → first stop) is not a leg
of the promise: the stop is within the radius already.

The numbers of the promise (R1, R2, the walk limit) are the founder's (docs/65 §5 ②): they are read from
the yardstick lock only (data/eval/yardstick.lock.json, "invariants"); this module has none of its own.
What may be tuned (how many transit legs, how far B may be suggested, the words) is in
data/recommendation/movement.json.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.domain.models import GeoPoint, PlaceCandidate, Promise, StopResult
from app.domain.recommendation.itinerary import hop_between, itinerary_rules
from app.domain.routing.travel_time import Leg, haversine_m

API_ROOT = Path(__file__).resolve().parents[3]
LOCK_PATH = API_ROOT / "data" / "eval" / "yardstick.lock.json"
RULES_PATH = API_ROOT / "data" / "recommendation" / "movement.json"

INSIDE, AROUND, ONWARD = "inside", "around", "onward"
MODES = (INSIDE, AROUND, ONWARD)
DEFAULT_MODE = AROUND
TRANSIT = "transit"
LOCK_KEYS = ("M1_radius_m", "M2_radius_m", "M2_walk_leg_max_min")


@lru_cache(maxsize=1)
def promise_numbers(path: Path = LOCK_PATH) -> dict[str, float]:
    """R1 · R2 · the walk limit, from the yardstick lock. Missing = the lock was not written: fail loudly
    rather than plan with a number nobody approved."""
    if not path.exists():
        raise RuntimeError(f"잣대 잠금 파일이 없다: {path}")
    found = json.loads(path.read_text(encoding="utf-8")).get("invariants") or {}
    missing = [k for k in LOCK_KEYS if k not in found]
    if missing:
        raise RuntimeError(f"잣대 잠금에 이동 모드 숫자가 없다: {missing} ({path})")
    return {k: float(found[k]) for k in LOCK_KEYS}


@lru_cache(maxsize=1)
def movement_rules(path: Path = RULES_PATH) -> dict[str, Any]:
    rules: dict[str, Any] = {
        "max_transit_legs": 1,
        "onward_ride_max_min": 15,
        "labels": {INSIDE: "역 안에서", AROUND: "역 주변 돌아보기", ONWARD: "다른 역으로 넘어가기"},
        "notices": {},
    }
    if path.exists():
        rules.update({k: v for k, v in json.loads(path.read_text(encoding="utf-8")).items() if k[0] != "_"})
    return rules


def make_promise(
    mode: str,
    center: GeoPoint,
    *,
    label: str | None = None,
    away_from: GeoPoint | None = None,
    hop_index: int | None = None,
) -> Promise:
    """The promise of one mode around one anchor. M3's clusters each keep M2 (`mode` stays "onward")."""
    numbers = promise_numbers()
    inside = mode == INSIDE
    return Promise(
        mode=mode,
        center=center,
        radius_m=numbers["M1_radius_m"] if inside else numbers["M2_radius_m"],
        walk_only=inside,
        walk_leg_max_min=numbers["M2_walk_leg_max_min"],  # M1 ⊂ M2: the same limit on foot (docs/65 §6)
        max_transit_legs=0 if inside else int(movement_rules()["max_transit_legs"]),
        label=label,
        away_from=away_from,
        hop_index=hop_index,
    )


def holds(promise: Promise, point: GeoPoint) -> bool:
    """The point lies where the promise says: within the radius (straight line), and — for a cluster of M3 —
    nearer its own anchor than the other one."""
    here = haversine_m(promise.center, point)
    if here > promise.radius_m:
        return False
    return promise.away_from is None or here < haversine_m(promise.away_from, point)


def transit_hop(a: GeoPoint, b: GeoPoint) -> Leg:
    """The same ride a hop between neighbourhoods is (itinerary.hop_between, with its wait), always by
    transit — a leg too long to walk is not walked, whatever its length."""
    hop = hop_between(a, b, TRANSIT, {**itinerary_rules(), "walk_hop_max_m": 0.0})
    return Leg(float(hop.minutes), float(hop.distance_m), TRANSIT)


def settle_leg(
    promise: Promise | None,
    transport: str,
    leg: Leg,
    a: GeoPoint,
    b: GeoPoint,
    transit_used: int,
) -> tuple[Leg, str | None] | None:
    """The leg between two stops under the promise: (leg, mode) — mode "transit" when a walk over the limit is
    ridden instead, None when it is the course's own transport. None altogether: the promise forbids it (a
    walk over the limit in M1, or a second one in M2). Only walking legs have a limit (docs/65 §6: by car
    or by transit the radius still holds, the walk rule does not)."""
    if promise is None or transport != "walk" or leg.minutes <= promise.walk_leg_max_min:
        return leg, None
    if promise.walk_only or transit_used >= promise.max_transit_legs:
        return None
    return transit_hop(a, b), TRANSIT


def ride_minutes(a: GeoPoint, b: GeoPoint, rules: Mapping[str, Any] | None = None) -> float:
    """M3's "15 minutes": the time on board only (no wait) — the hop's detour and speed, not its overhead."""
    rules = rules or itinerary_rules()
    path_m = haversine_m(a, b) * float(rules["hop_detour"])
    speed = float(rules["hop_speed_kmh"].get(TRANSIT, 26))
    return path_m / 1000.0 / speed * 60.0


def rank_onward(
    anchor: GeoPoint,
    candidates: Sequence[tuple[str, str, GeoPoint, float]],
    exclude: str | None,
    max_ride_min: float | None = None,
) -> list[tuple[str, str, GeoPoint, float]]:
    """M3's B when the user did not name one: `candidates` = (slug, name, centre, draw strength) of the
    neighbourhoods people come to for something (data/regions/draws.json). Within the ride, A itself left out;
    the strongest draw first, then the nearest, then the slug (so the same request always gets the same B)."""
    limit = float(movement_rules()["onward_ride_max_min"]) if max_ride_min is None else max_ride_min
    near = [c for c in candidates if c[0] != exclude and ride_minutes(anchor, c[2]) <= limit]
    return sorted(near, key=lambda c: (-c[3], round(haversine_m(anchor, c[2]), 1), c[0]))


def violations(stops: Sequence[StopResult], promise: Promise, transport: str) -> list[str]:
    """What in a finished course breaks the promise — empty when it holds. The engine plans within it; this is
    the post-condition the service checks (and the invariant tests re-measure independently)."""
    out: list[str] = []
    for s in stops:
        if not holds(promise, s.place.point):
            far = round(haversine_m(promise.center, s.place.point))
            out.append(f"OUTSIDE:{s.position}:{far}m")
    transit = [0]  # per cluster: M3's hop starts the count again
    for i, s in enumerate(stops):
        if i == 0:
            continue  # the first leg is not a leg of the promise
        if promise.hop_index is not None and i == promise.hop_index:
            transit.append(0)  # the hop of M3 is the one move of the day, not a walk
            continue
        if s.leg_mode == TRANSIT:
            transit[-1] += 1
            if promise.walk_only or transport != "walk":
                out.append(f"TRANSIT_LEG:{s.position}")
        elif transport == "walk" and s.travel_min_from_prev > promise.walk_leg_max_min:
            out.append(f"LONG_WALK:{s.position}:{s.travel_min_from_prev}min")
    out.extend(f"TRANSIT_LEGS:{n}" for n in transit if n > promise.max_transit_legs)
    return out


class WithinPromise:
    """A candidate source that only hands out what lies within the promise: the one choke point every pool of
    the engine goes through — the neighbourhood's own, its widening radius, the v2 outer rings, the recentring
    on a wanted place and the walkable-pocket search all read here."""

    def __init__(self, source: Any, promise: Promise) -> None:
        self._source = source
        self.promise = promise

    def _keep(self, found: Sequence[PlaceCandidate]) -> list[PlaceCandidate]:
        return [p for p in found if holds(self.promise, p.point)]

    async def fetch(
        self, role: str, origin: GeoPoint, radius_m: float, on_date: date, name_words: Sequence[str] = ()
    ) -> list[PlaceCandidate]:
        return self._keep(await self._source.fetch(role, origin, radius_m, on_date, name_words))

    async def opened_on(self, place_ids: Sequence[int]) -> dict[int, date]:
        opened = getattr(self._source, "opened_on", None)
        found: dict[int, date] = await opened(place_ids) if opened is not None else {}
        return found


class _WithStandouts(WithinPromise):
    async def fetch_standouts(
        self,
        role: str,
        origin: GeoPoint,
        radius_m: float,
        *,
        min_popularity: float,
        name_words: Sequence[str] = (),
        place_ids: Sequence[int] = (),
    ) -> list[PlaceCandidate]:
        found = await self._source.fetch_standouts(
            role, origin, radius_m, min_popularity=min_popularity, name_words=name_words, place_ids=place_ids
        )
        return self._keep(found)


def within_promise(source: Any, promise: Promise | None) -> Any:
    """`source` itself without a promise; otherwise the filtering wrapper, with `fetch_standouts` only when
    the source has it (the engine falls back to `fetch` otherwise)."""
    if promise is None:
        return source
    if getattr(source, "fetch_standouts", None) is not None:
        return _WithStandouts(source, promise)
    return WithinPromise(source, promise)
