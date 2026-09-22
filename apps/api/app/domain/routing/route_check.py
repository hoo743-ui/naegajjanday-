"""Route validation — before a course is drawn as a real route, check the day is walkable (docs/27).

The engine already builds feasible days from its own estimates. This layer re-checks the *final* order against
the *measured* legs (OSRM / NAVER) and against the places' hours, and says clearly what breaks:
coordinates missing or outside Korea, the same place twice, stops out of order, a leg that is far too far,
a leg that makes the next arrival late, a stop that is closed at its visit time, and a delay that cascades
until a later stop can no longer be visited. Pure functions: no I/O, easy to test.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from itertools import pairwise
from typing import Literal

from app.domain.models import GeoPoint, OpeningPeriod, TransportMode
from app.domain.recommendation.features import is_open
from app.domain.routing.travel_time import haversine_m

Severity = Literal["error", "warning", "info"]
LegSource = Literal["naver", "osrm", "estimate", "unavailable"]

# 한국 본토 · 제주 · 울릉 · 독도를 넉넉히 감싸는 사각형
KOREA_LAT = (33.0, 38.7)
KOREA_LNG = (124.5, 132.0)
DUPLICATE_M = 15.0
# 한 구간이 이보다 길면 "너무 먼 장소가 연속으로" (동네를 옮기는 구간은 더 넉넉하게)
TOO_FAR_M: dict[str, float] = {"walk": 3_000, "transit": 25_000, "car": 60_000}
TOO_FAR_HOP_M: dict[str, float] = {"walk": 5_000, "transit": 45_000, "car": 90_000}
UNREALISTIC_MIN = 180  # 한 구간에 3시간 넘게 걸리면 하루 코스가 아니다
LATE_SLACK_MIN = 10  # 이만큼 늦는 것은 걷는 속도 차이로 본다
BREAKS_AFTER_MIN = 45  # 늦어진 시간이 쌓여 이만큼 넘으면 뒤 일정이 무너진다


@dataclass(slots=True)
class CheckStop:
    sequence: int
    place_id: str
    name: str
    lat: float | None
    lng: float | None
    arrive_at: datetime
    leave_at: datetime
    opening_hours: Sequence[OpeningPeriod] = ()

    @property
    def stay_min(self) -> int:
        return max(0, round((self.leave_at - self.arrive_at).total_seconds() / 60))

    @property
    def point(self) -> GeoPoint | None:
        if self.lat is None or self.lng is None or not has_coordinates(self.lat, self.lng):
            return None
        return GeoPoint(self.lat, self.lng)


@dataclass(slots=True)
class CheckLeg:
    """The leg that arrives at stop `to_seq` from stop `from_seq`."""

    from_seq: int
    to_seq: int
    mode: TransportMode
    duration_min: int | None  # None = could not be measured
    distance_m: int | None
    source: LegSource
    hop: bool = False


@dataclass(slots=True)
class RouteIssue:
    code: str
    severity: Severity
    message: str
    stop: int | None = None  # sequence of the stop it is about
    leg: int | None = None  # sequence of the stop the leg arrives at


@dataclass(slots=True)
class CheckResult:
    issues: list[RouteIssue] = field(default_factory=list)

    @property
    def feasible(self) -> bool:
        return not any(i.severity == "error" for i in self.issues)


def has_coordinates(lat: float | None, lng: float | None) -> bool:
    if lat is None or lng is None:
        return False
    return KOREA_LAT[0] <= lat <= KOREA_LAT[1] and KOREA_LNG[0] <= lng <= KOREA_LNG[1]


def check_stops(stops: Sequence[CheckStop]) -> list[RouteIssue]:
    issues: list[RouteIssue] = []
    for s in stops:
        if s.lat is None or s.lng is None or (s.lat == 0 and s.lng == 0):
            issues.append(
                RouteIssue(
                    "NO_COORDINATES",
                    "error",
                    f"{s.name}의 위치를 찾지 못해 지도에 그릴 수 없어요.",
                    stop=s.sequence,
                )
            )
        elif not has_coordinates(s.lat, s.lng):
            issues.append(
                RouteIssue(
                    "BAD_COORDINATES", "error", f"{s.name}의 위치가 한국 밖으로 찍혀 있어요.", stop=s.sequence
                )
            )
    seen: dict[str, CheckStop] = {}
    for s in stops:
        twin = seen.get(s.place_id) or next(
            (
                o
                for o in seen.values()
                if o.point and s.point and o.name == s.name and haversine_m(o.point, s.point) < DUPLICATE_M
            ),
            None,
        )
        if twin is not None:
            issues.append(
                RouteIssue(
                    "DUPLICATE_STOP",
                    "warning",
                    f"{s.name}이(가) {twin.sequence}번과 {s.sequence}번에 두 번 들어 있어요.",
                    stop=s.sequence,
                )
            )
        seen.setdefault(s.place_id, s)
    for prev, cur in pairwise(stops):
        if cur.sequence != prev.sequence + 1 or cur.arrive_at < prev.leave_at:
            issues.append(
                RouteIssue(
                    "ORDER_BROKEN",
                    "error",
                    f"{prev.name} 다음에 {cur.name}(으)로 가는 순서가 맞지 않아요.",
                    stop=cur.sequence,
                )
            )
    for s in stops:
        if s.opening_hours and not is_open(s.opening_hours, s.arrive_at, s.stay_min):
            issues.append(
                RouteIssue(
                    "CLOSED_AT_VISIT",
                    "warning",
                    f"{s.name}은(는) {s.arrive_at:%H:%M}에 문을 닫았거나 곧 닫아요.",
                    stop=s.sequence,
                )
            )
    return issues


def check_legs(stops: Sequence[CheckStop], legs: Sequence[CheckLeg]) -> list[RouteIssue]:
    by_seq = {s.sequence: s for s in stops}
    issues: list[RouteIssue] = []
    delay = 0.0  # minutes the day has slipped so far
    for leg in legs:
        a, b = by_seq.get(leg.from_seq), by_seq.get(leg.to_seq)
        if a is None or b is None:
            continue
        if leg.source == "unavailable" or leg.duration_min is None:
            issues.append(
                RouteIssue(
                    "ROUTE_UNAVAILABLE",
                    "info",
                    f"{a.name} → {b.name} 경로 정보를 불러오지 못했어요.",
                    leg=b.sequence,
                )
            )
            continue
        far = (TOO_FAR_HOP_M if leg.hop else TOO_FAR_M)[leg.mode]
        if leg.distance_m is not None and leg.distance_m > far:
            issues.append(
                RouteIssue(
                    "LEG_TOO_FAR",
                    "warning",
                    f"{a.name}에서 {b.name}까지 {leg.distance_m / 1000:.1f}km 떨어져 있어요.",
                    leg=b.sequence,
                )
            )
        if leg.duration_min > UNREALISTIC_MIN and not leg.hop:
            issues.append(
                RouteIssue(
                    "UNREALISTIC_LEG",
                    "error",
                    f"{a.name}에서 {b.name}까지 {leg.duration_min}분이 걸려 하루 코스로 이어지지 않아요.",
                    leg=b.sequence,
                )
            )
            continue
        gap = (b.arrive_at - a.leave_at).total_seconds() / 60
        late = leg.duration_min - gap
        if late > LATE_SLACK_MIN:
            issues.append(
                RouteIssue(
                    "LEG_TOO_LONG",
                    "warning",
                    f"{a.name} → {b.name} 이동이 {leg.duration_min}분이라, "
                    f"{b.name}에 {round(late)}분 늦게 도착해요.",
                    leg=b.sequence,
                )
            )
        # 늦은 만큼 뒤로 밀린다. 다음 구간의 여유 시간이 조금씩 흡수한다
        delay = max(0.0, delay + late)
        if delay > LATE_SLACK_MIN:
            shifted = b.arrive_at + timedelta(minutes=delay)
            if b.opening_hours and not is_open(b.opening_hours, shifted, b.stay_min):
                issues.append(
                    RouteIssue(
                        "SCHEDULE_BREAKS",
                        "error",
                        f"이 일정은 이동시간이 길어 {b.name} 방문이 어려워요.",
                        stop=b.sequence,
                    )
                )
            elif delay > BREAKS_AFTER_MIN:
                issues.append(
                    RouteIssue(
                        "SCHEDULE_BREAKS",
                        "error",
                        f"이 일정은 이동시간이 길어 {b.name}에 {round(delay)}분 늦게 도착해요.",
                        stop=b.sequence,
                    )
                )
    return _dedupe(issues)


def _dedupe(issues: list[RouteIssue]) -> list[RouteIssue]:
    """SCHEDULE_BREAKS is said once (at the first stop where the day breaks)."""
    out: list[RouteIssue] = []
    broke = False
    for i in issues:
        if i.code == "SCHEDULE_BREAKS":
            if broke:
                continue
            broke = True
        out.append(i)
    return out


def check_route(stops: Sequence[CheckStop], legs: Sequence[CheckLeg]) -> CheckResult:
    return CheckResult(issues=[*check_stops(stops), *check_legs(stops, legs)])
