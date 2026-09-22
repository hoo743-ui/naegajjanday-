"""NAVER Cloud Platform · Maps — Directions 5/15 (driving) and Geocoding (docs/27).

What NAVER actually offers, and what we therefore do not pretend:
- Directions 5 / Directions 15 route **cars** only (live traffic). There is no public NAVER walking or transit
  routing API. Walking geometry comes from the OSRM foot router; transit stays the engine's estimate and the
  UI hands the user to the NAVER Map app for real lines.
- Directions 5 takes up to 5 waypoints, Directions 15 up to 15. Longer courses are split into overlapping
  chunks (the last point of one chunk is the first of the next) and joined back into one itinerary.
- Keys live on the server (`NAVER_MAP_CLIENT_ID` / `NAVER_MAP_CLIENT_SECRET`); the browser never sees them.

Response shape used (Directions): route.<option>[0].summary.{distance(m), duration(ms), waypoints[{distance,
duration, pointIndex}]} and route.<option>[0].path [[lng, lat], ...]. Waypoint distance/duration are measured
from the previous point, pointIndex marks where each waypoint sits in `path`, so the path can be cut per leg.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import httpx

from app.core.config import Settings
from app.domain.models import GeoPoint

D5_MAX_WAYPOINTS = 5
D15_MAX_WAYPOINTS = 15
OPTION = "traoptimal"  # NAVER's "실시간 최적"

# NAVER Directions result codes (0 = ok)
NAVER_CODES = {
    1: "출발지와 도착지가 같아요",
    2: "출발지나 도착지가 도로 가까이에 있지 않아요",
    3: "자동차 길찾기 결과를 줄 수 없는 구간이에요",
    4: "경유지가 도로 가까이에 있지 않아요",
    5: "경로가 너무 길어요",
}


class NaverMapsError(RuntimeError):
    def __init__(self, message: str, code: int | None = None) -> None:
        super().__init__(message)
        self.code = code


@dataclass(slots=True)
class DrivenLeg:
    distance_m: int
    duration_min: int
    path: list[tuple[float, float]] = field(default_factory=list)  # [lat, lng]


def chunk_points(points: list[GeoPoint], max_waypoints: int = D15_MAX_WAYPOINTS) -> list[list[GeoPoint]]:
    """Split A..Z into requests of at most start + max_waypoints + goal, sharing the boundary point."""
    if len(points) < 2:
        return []
    step = max_waypoints + 1  # legs per request
    chunks: list[list[GeoPoint]] = []
    i = 0
    while i < len(points) - 1:
        chunks.append(points[i : i + step + 1])
        i += step
    return chunks


def split_route(route: dict[str, Any], leg_count: int) -> list[DrivenLeg]:
    """One NAVER route (start, waypoints…, goal) -> one DrivenLeg per consecutive pair."""
    summary = route["summary"]
    path_lnglat: list[list[float]] = route.get("path") or []
    path = [(float(lat), float(lng)) for lng, lat in path_lnglat]
    waypoints: list[dict[str, Any]] = list(summary.get("waypoints") or [])
    if len(waypoints) != leg_count - 1:
        raise NaverMapsError(f"expected {leg_count - 1} waypoints in summary, got {len(waypoints)}")
    cuts = [0] + [int(w["pointIndex"]) for w in waypoints] + [max(0, len(path) - 1)]
    legs: list[DrivenLeg] = []
    used_m, used_ms = 0, 0
    for k in range(leg_count):
        if k < len(waypoints):
            d_m, d_ms = int(waypoints[k]["distance"]), int(waypoints[k]["duration"])
        else:  # the goal: whatever is left of the whole route
            d_m, d_ms = int(summary["distance"]) - used_m, int(summary["duration"]) - used_ms
        used_m, used_ms = used_m + d_m, used_ms + d_ms
        segment = path[cuts[k] : cuts[k + 1] + 1]
        legs.append(
            DrivenLeg(distance_m=max(0, d_m), duration_min=max(1, round(d_ms / 60_000)), path=segment)
        )
    return legs


def _lnglat(p: GeoPoint) -> str:
    return f"{p.lng:.6f},{p.lat:.6f}"


class NaverMapsClient:
    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        self._settings = settings
        self._client = client

    @property
    def configured(self) -> bool:
        return bool(self._settings.naver_map_client_id and self._settings.naver_map_client_secret)

    def _headers(self) -> dict[str, str]:
        return {
            "x-ncp-apigw-api-key-id": self._settings.naver_map_client_id or "",
            "x-ncp-apigw-api-key": self._settings.naver_map_client_secret or "",
        }

    async def _get(self, path: str, params: dict[str, str]) -> dict[str, Any]:
        if not self.configured:
            raise NaverMapsError("NAVER Maps keys are not configured")
        url = self._settings.naver_maps_base_url.rstrip("/") + path
        try:
            if self._client is not None:
                res = await self._client.get(url, params=params, headers=self._headers())
            else:
                async with httpx.AsyncClient(timeout=self._settings.naver_timeout_s) as client:
                    res = await client.get(url, params=params, headers=self._headers())
            res.raise_for_status()
            body: dict[str, Any] = res.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise NaverMapsError(f"NAVER request failed: {str(exc)[:160]}") from exc
        return body

    async def driving(self, points: list[GeoPoint]) -> list[DrivenLeg]:
        """Car legs for A → B → … in order. Picks Directions 5 or 15 by waypoint count; chunks beyond 15."""
        legs: list[DrivenLeg] = []
        for chunk in chunk_points(points):
            waypoints = chunk[1:-1]
            path = (
                "/map-direction/v1/driving"
                if len(waypoints) <= D5_MAX_WAYPOINTS
                else "/map-direction-15/v1/driving"
            )
            params = {"start": _lnglat(chunk[0]), "goal": _lnglat(chunk[-1]), "option": OPTION}
            if waypoints:
                params["waypoints"] = "|".join(_lnglat(p) for p in waypoints)
            body = await self._get(path, params)
            code = int(body.get("code", -1))
            if code != 0:
                raise NaverMapsError(NAVER_CODES.get(code, body.get("message") or f"NAVER code {code}"), code)
            try:
                route = body["route"][OPTION][0]
                legs.extend(split_route(route, len(chunk) - 1))
            except (KeyError, IndexError, TypeError, ValueError) as exc:
                raise NaverMapsError(f"unexpected NAVER response: {str(exc)[:120]}") from exc
        return legs

    async def geocode(self, address: str) -> GeoPoint | None:
        body = await self._get("/map-geocode/v2/geocode", {"query": address})
        if body.get("status") != "OK":
            return None
        for item in body.get("addresses") or []:
            try:
                return GeoPoint(float(item["y"]), float(item["x"]))
            except (KeyError, TypeError, ValueError):
                continue
        return None
