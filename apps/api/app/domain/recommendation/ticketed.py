"""입장권이 있어야 들어가는 곳 (창업자 2026-09-26): "롯데월드 같은 경우에는 거길 입장해야 들어갈 수 있는 카페,
음식점이 있기 때문에 그 값 자체가 필터로 연동이 되어야 할 듯."

A café inside 롯데월드 어드벤처 or 에버랜드 is behind the ticket gate. The data (`ticketed_venues.json`) names
the venues, their official admission and how to tell a place inside them (the gate's address, a word on the
sign, an explicit id — never a mall or a hotel that shares the street number). Everything here is derived when
a place is read (repositories.place_repo.to_candidate), so no row of the database is ever changed.

- the venue itself costs its admission (× party), not the category's average;
- a place inside is a stop only right after its venue (or another place inside it): nobody walks out and
  buys a second ticket for a coffee, and without the venue it is not a stop at all;
- the walk between them is the few minutes inside the gate.

Follow-up (창업자 2026-09-27, docs/59 #13):
- the day after a long venue (a theme park's afternoon) is short: one meal or café near the gate (or inside
  it), then home — no second outing, no long leg, and a day with the kids still ends by its scene's hour;
- a party with children pays the child price for them (`party_of`: the request has no head count by age, so
  아이와 is read as two adults and the rest children — one adult and one child for a pair);
- a price announced for a later day (에버랜드 2026-10-06) is in force from that day by itself (`changes`).
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from app.domain.models import GeoPoint, PlaceCandidate, RequestContext
from app.domain.routing.travel_time import haversine_m

TICKETED_PATH = Path(__file__).resolve().parents[3] / "data" / "recommendation" / "ticketed_venues.json"
_SPACE = re.compile(r"\s+")
KST = ZoneInfo("Asia/Seoul")


def _today() -> date:
    return datetime.now(KST).date()


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
    effective: date | None = None  # a price announced for a later day: in force from this day on

    def for_party(self, adults: int, children: int) -> int:
        """What the whole party pays at the gate: adults at the adult price, children at the child price."""
        child = self.adult if self.child is None else self.child
        return max(0, adults) * self.adult + max(0, children) * child


@dataclass(frozen=True, slots=True)
class Venue:
    key: str
    name: str
    place_ids: frozenset[int]
    names: frozenset[str]  # compact sign names that are this venue (a duplicate listing)
    gate: GeoPoint
    radius_m: float
    admission: Admission  # the price in force before any announced change
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
    changes: tuple[Admission, ...] = ()  # announced prices, oldest first (admission.changes in the file)

    def admission_on(self, day: date | None = None) -> Admission:
        """The price in force on `day` (today when not given): the latest change that has started."""
        day = day or _today()
        current = self.admission
        for change in self.changes:
            if change.effective is not None and change.effective <= day:
                current = change
        return current

    def admission_line(self, day: date | None = None, children: int = 0) -> str:
        a = self.admission_on(day)
        if children > 0 and a.child is not None and a.child != a.adult:
            short = "공식" if a.basis == "공식" else "추정"
            return f"입장권 어른 {a.adult:,} · 어린이 {a.child:,}원({short} {a.as_of})"
        basis = "공식 요금" if a.basis == "공식" else "추정 요금"
        return f"입장권 1인 {a.adult:,}원 ({basis}, {a.as_of} 기준)"

    def inside_line(self) -> str:
        return f"{self.name} 안 · 입장권이 있어야 들어가요"


@dataclass(frozen=True, slots=True)
class WrapUp:
    """After a long venue (docs/59 #13) the day ends near its gate. 서울랜드 with the kids: the park from
    12:46 to 16:48, then a café, a 35-minute walk to a sports park and a concert hall until 21:30 — after four
    hours in a theme park nobody sets out on a second outing."""

    long_stay_min: int = 180  # a venue stayed at least this long ends the day (a theme park: 240)
    roles: frozenset[str] = frozenset({"MEAL", "CAFE", "DESSERT"})  # the one stop after it
    leg_max_min: float = 15.0  # that stop is this near the gate (inside it: the few minutes of leg_cap_min)
    before_leg_max_min: float = 15.0  # a pinned venue: the stop before it (lunch) is this near its gate


@dataclass(frozen=True, slots=True)
class PartyRule:
    """Who pays the child price. A request says who comes along (scene) and how many, not how many are
    children — so a scene with children is read as `adults_of_family` adults and the rest children."""

    child_scenes: Mapping[str, frozenset[str]] = field(
        default_factory=lambda: {"family": frozenset({"kids"})}
    )
    adults_of_family: int = 2


@dataclass(frozen=True, slots=True)
class TicketedVenues:
    venues: tuple[Venue, ...]
    inner_roles: frozenset[str]
    leg_cap_min: float  # the walk between a venue and a place inside it, at most
    wrap: WrapUp = field(default_factory=WrapUp)
    party: PartyRule = field(default_factory=PartyRule)

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
        """Set `ticket_venue` / `inside_venue` and price the venue at today's adult admission (a request
        prices it again for its own day and party — `price`). In place; returns it."""
        if place.is_event:
            return place
        venue = self.venue_of(place.id, place.name, place.course_role, place.point)
        if venue is not None:
            admission = venue.admission_on()
            place.ticket_venue = venue.key
            place.price_per_person = admission.adult
            place.price_is_estimated = admission.basis != "공식"
            place.is_free = False
            if venue.stay_min:
                place.default_stay_min = venue.stay_min
            return place
        inside = self.inside_of(place.id, place.name, place.course_role, place.address, place.point)
        if inside is not None:
            place.inside_venue = inside.key
        return place

    # ── a request's own price: its day, its children ──────────────────────────────────────────

    def party_of(self, purpose_code: str, scene: str | None, party_size: int) -> tuple[int, int]:
        """(adults, children). A scene with children (가족 · 아이와): two adults and the rest children, one
        adult for a pair; any other company is all adults."""
        party_size = max(1, party_size)
        if scene is None or scene not in self.party.child_scenes.get(purpose_code, frozenset()):
            return party_size, 0
        adults = min(self.party.adults_of_family, max(1, party_size - 1))
        return adults, party_size - adults

    def price(self, places: Iterable[PlaceCandidate], ctx: RequestContext) -> None:
        """Price each venue among `places` for this request: the admission in force on its day, children at
        the child price. Per person is the party's total spread over it, rounded up (the course's total is
        never less than what the gate charges). In place; the same answer however often it runs."""
        adults, children = self.party_of(ctx.purpose_code, ctx.scene, ctx.party_size)
        day = ctx.start_at.date()
        for place in places:
            venue = self.by_key(place.ticket_venue)
            if venue is None or place.is_event:
                continue
            admission = venue.admission_on(day)
            place.price_per_person = math.ceil(admission.for_party(adults, children) / (adults + children))
            place.price_is_estimated = admission.basis != "공식"
            place.ticket_children = children
            place.ticket_day = day

    def party_price(self, place: PlaceCandidate, party_size: int) -> int:
        """What the party pays at this stop: a priced venue's exact gate total (per person is rounded up),
        anything else its price × party."""
        venue = self.by_key(place.ticket_venue)
        if venue is None or place.ticket_day is None or place.is_event:
            return place.price * party_size
        children = min(place.ticket_children, max(0, party_size - 1))
        return venue.admission_on(place.ticket_day).for_party(party_size - children, children)

    def restore(
        self, place: PlaceCandidate, est_price: int, party_size: int, request: Mapping[str, Any], day: date
    ) -> None:
        """A saved course's venue keeps the price it was planned at (a reorder or a swap re-times the day
        with it): the stored party price, and the children it counted (request › purposes · scene)."""
        if not place.ticket_venue or est_price <= 0 or party_size <= 0:
            return
        purposes = request.get("purposes") or []
        _, children = self.party_of(str(purposes[0]) if purposes else "", request.get("scene"), party_size)
        place.price_per_person = math.ceil(est_price / party_size)
        place.ticket_children = children
        place.ticket_day = day

    def line(self, place: PlaceCandidate) -> str | None:
        """The card's one line for a venue (its admission, for the party it was priced for) or for a place
        inside one (behind the gate)."""
        if (venue := self.by_key(place.ticket_venue)) is not None:
            return venue.admission_line(place.ticket_day, place.ticket_children)
        if (venue := self.by_key(place.inside_venue)) is not None:
            return venue.inside_line()
        return None

    def ends_day(self, place: PlaceCandidate) -> bool:
        """A venue stayed long enough that the day ends near its gate (WrapUp)."""
        return bool(place.ticket_venue) and place.default_stay_min >= self.wrap.long_stay_min


def _admission(a: Mapping[str, Any], base: Admission | None = None) -> Admission:
    """One price; an announced change carries over what it does not restate (the ticket, the basis)."""
    child = a.get("child", base.child if base else None)
    effective = date.fromisoformat(str(a["from"])) if a.get("from") else None
    return Admission(
        adult=int(a["adult"]),
        child=int(child) if child is not None else None,
        ticket=str(a.get("ticket", base.ticket if base else "")),
        as_of=str(a.get("as_of") or (effective.isoformat()[:7] if effective else "")),
        basis=str(a.get("basis", base.basis if base else "추정")),
        source=str(a.get("source", base.source if base else "")),
        effective=effective,
    )


def _venue(raw: Mapping[str, Any]) -> Venue:
    a = raw["admission"]
    inner = raw.get("inner") or {}
    exc = raw.get("exceptions") or {}
    base = _admission(a)
    changes = sorted(
        (_admission(c, base) for c in a.get("changes", [])), key=lambda c: c.effective or date.min
    )
    return Venue(
        key=str(raw["key"]),
        name=str(raw["name"]),
        place_ids=frozenset(int(i) for i in raw.get("place_ids", [])),
        names=frozenset(_compact(n) for n in [raw["name"], *raw.get("names", [])]),
        gate=GeoPoint(float(raw["gate"][0]), float(raw["gate"][1])),
        radius_m=float(raw.get("radius_m", 500)),
        admission=base,
        changes=tuple(changes),
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
    wrap, party = data.get("wrap_up") or {}, data.get("party") or {}
    w, p = WrapUp(), PartyRule()
    return TicketedVenues(
        venues=tuple(_venue(v) for v in data.get("venues", [])),
        inner_roles=frozenset(data.get("inner_roles", ["MEAL", "CAFE", "DESSERT", "BAR"])),
        leg_cap_min=float(data.get("leg_cap_min", 5)),
        wrap=WrapUp(
            long_stay_min=int(wrap.get("long_stay_min", w.long_stay_min)),
            roles=frozenset(wrap.get("roles", w.roles)),
            leg_max_min=float(wrap.get("leg_max_min", w.leg_max_min)),
            before_leg_max_min=float(wrap.get("before_leg_max_min", w.before_leg_max_min)),
        ),
        party=PartyRule(
            child_scenes={k: frozenset(v) for k, v in (party.get("child_scenes") or p.child_scenes).items()},
            adults_of_family=int(party.get("adults_of_family", p.adults_of_family)),
        ),
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


def after_long_venue(stops: Sequence[PlaceCandidate]) -> int | None:
    """How many stops came after the day's long venue (None: no such venue in `stops`)."""
    venues = ticketed_venues()
    for i, place in enumerate(stops):
        if venues.ends_day(place):
            return len(stops) - i - 1
    return None


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
