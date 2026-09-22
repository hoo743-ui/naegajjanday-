"""Course route (Route Intelligence, docs/27): one model the map, the cards and the mobile sheet all read."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

Mode = Literal["walk", "transit", "car"]


class RouteStopOut(BaseModel):
    sequence: int
    place_id: str
    name: str
    address: str | None = None
    lat: float | None
    lng: float | None
    arrive_at: datetime
    leave_at: datetime
    stay_min: int
    price: int


class RouteLegOut(BaseModel):
    """The leg that arrives at stop `to_seq`."""

    from_seq: int
    to_seq: int
    origin: str
    destination: str
    mode: Mode
    distance_m: int | None = None
    duration_min: int | None = None
    path: list[tuple[float, float]] = Field(default_factory=list, description="[lat, lng] along the way")
    source: Literal["naver", "osrm", "estimate", "unavailable"] = Field(
        description="naver = NAVER Directions (car) · osrm = measured walking path · "
        "estimate = engine estimate (straight line × detour) · unavailable = could not be computed"
    )
    geometry: Literal["road", "straight", "none"]
    hop_to: str | None = None


class RouteIssueOut(BaseModel):
    code: str
    severity: Literal["error", "warning", "info"]
    message: str
    stop: int | None = None
    leg: int | None = None


class RouteTotals(BaseModel):
    travel_min: int
    distance_m: int
    measured: bool = Field(description="every leg was measured on real roads/paths (no estimates)")


class RouteProviders(BaseModel):
    walk: Literal["osrm", "estimate"]
    car: Literal["naver", "estimate"]
    transit: Literal["estimate"] = "estimate"


class CourseRouteOut(BaseModel):
    course_id: str
    transport: Mode
    stops: list[RouteStopOut]
    legs: list[RouteLegOut]
    totals: RouteTotals
    issues: list[RouteIssueOut]
    feasible: bool
    providers: RouteProviders
    computed_at: datetime
