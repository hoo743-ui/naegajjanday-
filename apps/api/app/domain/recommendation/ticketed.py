"""입장권이 있어야 들어가는 곳 (창업자 2026-09-26): "롯데월드 같은 경우에는 거길 입장해야 들어갈 수 있는 카페,
음식점이 있기 때문에 그 값 자체가 필터로 연동이 되어야 할 듯."

A café inside 롯데월드 어드벤처 or 에버랜드 is behind the ticket gate. The data (`ticketed_venues.json`) names
the venues, their official admission and how to tell a place inside them (the gate's address, a word on the
sign, an explicit id — never a mall or a hotel that shares the street number). Everything here is derived when
a place is read (repositories.place_repo.to_candidate), so no row of the database is ever changed.

- the venue itself costs its admission (adult price × party), not the category's average;
- a place inside is a stop only right after its venue (or another place inside it): nobody walks out and
  buys a second ticket for a coffee, and without the venue it is not a stop at all;
- the walk between them is the few minutes inside the gate.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.domain.models import GeoPoint, PlaceCandidate
from app.domain.routing.travel_time import haversine_m

TICKETED_PATH = Path(__file__).resolve().parents[3] / "data" / "recommendation" / "ticketed_venues.json"
_SPACE = re.compile(r"\s+")


def _compact(text: str | None) -> str:
    return _SPACE.sub("", text or "")


def _address_key(key: str) -> re.Pattern[str]:
    """ "올림픽로 240" matches "올림픽로240 (잠실동)" — never "올림픽로 2400" or "올림픽로 240-1"."""
    street, _, number = key.strip().rpartition(" ")
    return re.compile(re.escape(_compact(street)) + re.escape(number) + r"(?![\d-])")


@dataclass(frozen=True, slots=True)
class Admission:
    adult: int
    child: int | None
    ticket: str
    as_of: str  # "YYYY-MM"
    basis: str  # "공식" | "추정"
    source: str


@dataclass(frozen=True, slots=True)
class Venue:
    key: str
    name: str
    place_ids: frozenset[int]
    names: frozenset[str]  # compact sign names that are this venue (a duplicate listing)
    gate: GeoPoint
    radius_m: float
    admission: Admission
    stay_min: int | None = None  # a theme park is an afternoon, not the category's hour
    address_keys: tuple[re.Pattern[str], ...] = ()
    # on a shared address only a sign carrying one of these words is inside (올림픽로 240 is also a
    # department store, a mart, a hotel and 키자니아)
    require_words: tuple[str, ...] = ()
    inner_ids: frozenset[int] = frozenset()
    inner_words: tuple[str, ...] = ()  # a sign naming the venue ("롯데월드어드벤처 부산점") near the gate
    address_words: tuple[str, ...] = ()  # "오월드 내": the address itself says it is inside
    except_ids: frozenset[int] = frozenset()
    except_words: tuple[str, ...] = ()

    def admission_line(self) -> str:
        basis = "공식 요금" if self.admission.basis == "공식" else "추정 요금"
        return f"입장권 1인 {self.admission.adult:,}원 ({basis}, {self.admission.as_of} 기준)"

    def inside_line(self) -> str:
        return f"{self.name} 안 · 입장권이 있어야 들어가요"


@dataclass(frozen=True, slots=True)
class TicketedVenues:
    venues: tuple[Venue, ...]
    inner_roles: frozenset[str]
    leg_cap_min: float  # the walk between a venue and a place inside it, at most

    def by_key(self, key: str | None) -> Venue | None:
        return next((v for v in self.venues if v.key == key), None) if key else None

    def venue_of(self, place_id: int, name: str, role: str, point: GeoPoint) -> Venue | None:
        """The venue this place IS (its own listing or a duplicate of it near the gate). A café or a
        restaurant registered under the venue's name ("아쿠아플라넷일산", a café) is not the venue."""
        sign = _compact(name)
        for v in self.venues:
            if place_id in v.place_ids:
                return v
            if role not in self.inner_roles and sign in v.names and haversine_m(point, v.gate) <= v.radius_m:
                return v
        return None

    def inside_of(
        self, place_id: int, name: str, role: str, address: str | None, point: GeoPoint
    ) -> Venue | None:
        """The venue this place stands inside (behind its ticket gate), or None."""
        sign, where = _compact(name), _compact(address)
        for v in self.venues:
            if place_id in v.place_ids or place_id in v.except_ids:
                continue
            if any(w in sign for w in v.except_words):
                continue
            if haversine_m(point, v.gate) > v.radius_m:
                continue
            if place_id in v.inner_ids:
                return v
            if any(w in where for w in v.address_words):
                return v
            if role not in self.inner_roles:
                continue
            if any(w in sign for w in v.inner_words):
                return v
            if any(k.search(where) for k in v.address_keys) and (
                not v.require_words or any(w in sign for w in v.require_words)
            ):
                return v
        return None

    def mark(self, place: PlaceCandidate) -> PlaceCandidate:
        """Set `ticket_venue` / `inside_venue` and price the venue at its admission. In place; returns it."""
        if place.is_event:
            return place
        venue = self.venue_of(place.id, place.name, place.course_role, place.point)
        if venue is not None:
            place.ticket_venue = venue.key
            place.price_per_person = venue.admission.adult
            place.price_is_estimated = venue.admission.basis != "공식"
            place.is_free = False
            if venue.stay_min:
                place.default_stay_min = venue.stay_min
            return place
        inside = self.inside_of(place.id, place.name, place.course_role, place.address, place.point)
        if inside is not None:
            place.inside_venue = inside.key
        return place


def _venue(raw: Mapping[str, Any]) -> Venue:
    a = raw["admission"]
    inner = raw.get("inner") or {}
    exc = raw.get("exceptions") or {}
    return Venue(
        key=str(raw["key"]),
        name=str(raw["name"]),
        place_ids=frozenset(int(i) for i in raw.get("place_ids", [])),
        names=frozenset(_compact(n) for n in [raw["name"], *raw.get("names", [])]),
        gate=GeoPoint(float(raw["gate"][0]), float(raw["gate"][1])),
        radius_m=float(raw.get("radius_m", 500)),
        admission=Admission(
            adult=int(a["adult"]),
            child=int(a["child"]) if a.get("child") is not None else None,
            ticket=str(a.get("ticket", "")),
            as_of=str(a["as_of"]),
            basis=str(a.get("basis", "추정")),
            source=str(a.get("source", "")),
        ),
        stay_min=int(raw["stay_min"]) if raw.get("stay_min") else None,
        address_keys=tuple(_address_key(k) for k in inner.get("address_keys", [])),
        require_words=tuple(_compact(w) for w in inner.get("require_name_words", [])),
        inner_ids=frozenset(int(i) for i in inner.get("place_ids", [])),
        inner_words=tuple(_compact(w) for w in inner.get("name_words", [])),
        address_words=tuple(_compact(w) for w in inner.get("address_words", [])),
        except_ids=frozenset(int(i) for i in exc.get("place_ids", [])),
        except_words=tuple(_compact(w) for w in exc.get("name_words", [])),
    )


def parse(data: Mapping[str, Any]) -> TicketedVenues:
    return TicketedVenues(
        venues=tuple(_venue(v) for v in data.get("venues", [])),
        inner_roles=frozenset(data.get("inner_roles", ["MEAL", "CAFE", "DESSERT", "BAR"])),
        leg_cap_min=float(data.get("leg_cap_min", 5)),
    )


@lru_cache(maxsize=1)
def ticketed_venues(path: Path = TICKETED_PATH) -> TicketedVenues:
    if not path.exists():
        return TicketedVenues((), frozenset(), 5.0)
    return parse(json.loads(path.read_text(encoding="utf-8")))


# ── the engine's rules ────────────────────────────────────────────────────────────────────────


def may_follow(place: PlaceCandidate, previous: PlaceCandidate | None) -> bool:
    """A place inside a venue is a stop only right after that venue or another place inside it."""
    if not place.inside_venue:
        return True
    if previous is None:
        return False
    return place.inside_venue in (previous.ticket_venue, previous.inside_venue)


def within_gate(place: PlaceCandidate, previous: PlaceCandidate | None) -> bool:
    """This hop stays behind the gate (venue → café inside, café → restaurant inside)."""
    return bool(place.inside_venue) and previous is not None and may_follow(place, previous)


def drop_orphans(
    pools: Mapping[int, list[PlaceCandidate]], kept: Sequence[PlaceCandidate] = ()
) -> dict[int, list[PlaceCandidate]]:
    """Places inside a venue no pool holds (nor the pinned stops) are no candidates."""
    every = [*kept, *(p for pool in pools.values() for p in pool)]
    venues = {p.ticket_venue for p in every if p.ticket_venue}
    return {pos: [p for p in pool if p.inside_venue in (None, *venues)] for pos, pool in pools.items()}


def orphaned(stops: Iterable[PlaceCandidate]) -> list[PlaceCandidate]:
    """Places inside a venue whose venue is not in the course (the scorecard's check)."""
    stops = list(stops)
    venues = {p.ticket_venue for p in stops if p.ticket_venue}
    return [p for p in stops if p.inside_venue and p.inside_venue not in venues]
