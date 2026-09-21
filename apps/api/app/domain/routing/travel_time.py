"""Travel-time providers (doc 06 §6.3).

`HaversineEstimator` is the default and the fallback; it is synchronous and used for the hundreds of
candidate pairs inside the beam search. The HTTP adapters are only used to re-measure the legs of the
final top courses (≤ 12 calls per request) and raise a clear error when their key is missing.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

import httpx

from app.domain.models import GeoPoint, TransportMode

EARTH_RADIUS_M = 6_371_008.8
DETOUR_FACTOR: dict[str, float] = {"walk": 1.3, "transit": 1.4, "car": 1.4}
SPEED_KMH: dict[str, float] = {"walk": 4.5, "transit": 18.0, "car": 22.0}


@dataclass(frozen=True, slots=True)
class Leg:
    minutes: float
    distance_m: float
    source: str = "haversine"


class TravelTimeError(RuntimeError):
    pass


class TravelProviderNotConfiguredError(TravelTimeError):
    def __init__(self, provider: str, env_var: str) -> None:
        super().__init__(f"travel-time provider '{provider}' requires env {env_var}")


def haversine_m(a: GeoPoint, b: GeoPoint) -> float:
    p1, p2 = math.radians(a.lat), math.radians(b.lat)
    dphi, dlmb = p2 - p1, math.radians(b.lng - a.lng)
    h = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(h)))


@runtime_checkable
class TravelTimeProvider(Protocol):
    name: str

    async def leg(self, a: GeoPoint, b: GeoPoint, mode: TransportMode) -> Leg: ...


class HaversineEstimator:
    name = "haversine"

    def estimate(self, a: GeoPoint, b: GeoPoint, mode: TransportMode) -> Leg:
        path_m = haversine_m(a, b) * DETOUR_FACTOR[mode]
        minutes = path_m / 1000.0 / SPEED_KMH[mode] * 60.0
        return Leg(minutes=minutes, distance_m=path_m)

    async def leg(self, a: GeoPoint, b: GeoPoint, mode: TransportMode) -> Leg:
        return self.estimate(a, b, mode)


class _HttpProvider:
    name = "http"

    def __init__(self, client: httpx.AsyncClient | None = None, timeout_s: float = 3.0) -> None:
        self._client = client or httpx.AsyncClient(timeout=timeout_s)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _json(self, method: str, url: str, **kwargs: Any) -> dict[str, Any]:
        try:
            resp = await self._client.request(method, url, **kwargs)
            resp.raise_for_status()
            data: dict[str, Any] = resp.json()
            return data
        except (httpx.HTTPError, ValueError) as exc:
            raise TravelTimeError(f"{self.name}: {exc}") from exc


class KakaoMobilityProvider(_HttpProvider):
    """Kakao Mobility directions API — car only."""

    name = "kakao"
    URL = "https://apis-navi.kakaomobility.com/v1/directions"

    def __init__(self, api_key: str | None, client: httpx.AsyncClient | None = None) -> None:
        if not api_key:
            raise TravelProviderNotConfiguredError(self.name, "KAKAO_MOBILITY_API_KEY")
        super().__init__(client)
        self._key = api_key

    async def leg(self, a: GeoPoint, b: GeoPoint, mode: TransportMode) -> Leg:
        if mode != "car":
            raise TravelTimeError("kakao mobility supports car only")
        data = await self._json(
            "GET",
            self.URL,
            params={"origin": f"{a.lng},{a.lat}", "destination": f"{b.lng},{b.lat}"},
            headers={"Authorization": f"KakaoAK {self._key}"},
        )
        try:
            summary = data["routes"][0]["summary"]
            return Leg(summary["duration"] / 60.0, float(summary["distance"]), self.name)
        except (KeyError, IndexError, TypeError) as exc:
            raise TravelTimeError(f"kakao: unexpected response {data!r:.200}") from exc


class TmapProvider(_HttpProvider):
    """SK open API — pedestrian and transit routes."""

    name = "tmap"
    PEDESTRIAN_URL = "https://apis.openapi.sk.com/tmap/routes/pedestrian?version=1"
    TRANSIT_URL = "https://apis.openapi.sk.com/transit/routes"

    def __init__(self, app_key: str | None, client: httpx.AsyncClient | None = None) -> None:
        if not app_key:
            raise TravelProviderNotConfiguredError(self.name, "TMAP_APP_KEY")
        super().__init__(client)
        self._key = app_key

    async def leg(self, a: GeoPoint, b: GeoPoint, mode: TransportMode) -> Leg:
        headers = {"appKey": self._key, "Accept": "application/json"}
        body = {"startX": str(a.lng), "startY": str(a.lat), "endX": str(b.lng), "endY": str(b.lat)}
        try:
            if mode == "transit":
                data = await self._json("POST", self.TRANSIT_URL, json={**body, "count": 1}, headers=headers)
                it = data["metaData"]["plan"]["itineraries"][0]
                return Leg(it["totalTime"] / 60.0, float(it["totalDistance"]), self.name)
            if mode == "walk":
                payload = {**body, "startName": "start", "endName": "end"}
                data = await self._json("POST", self.PEDESTRIAN_URL, json=payload, headers=headers)
                props = data["features"][0]["properties"]
                return Leg(props["totalTime"] / 60.0, float(props["totalDistance"]), self.name)
        except (KeyError, IndexError, TypeError) as exc:
            raise TravelTimeError("tmap: unexpected response") from exc
        raise TravelTimeError("tmap adapter supports walk/transit only")


class GoogleRoutesProvider(_HttpProvider):
    name = "google"
    URL = "https://routes.googleapis.com/directions/v2:computeRoutes"
    MODES: dict[str, str] = {"walk": "WALK", "transit": "TRANSIT", "car": "DRIVE"}  # noqa: RUF012

    def __init__(self, api_key: str | None, client: httpx.AsyncClient | None = None) -> None:
        if not api_key:
            raise TravelProviderNotConfiguredError(self.name, "GOOGLE_ROUTES_API_KEY")
        super().__init__(client)
        self._key = api_key

    async def leg(self, a: GeoPoint, b: GeoPoint, mode: TransportMode) -> Leg:
        def wp(p: GeoPoint) -> dict[str, Any]:
            return {"location": {"latLng": {"latitude": p.lat, "longitude": p.lng}}}

        data = await self._json(
            "POST",
            self.URL,
            json={"origin": wp(a), "destination": wp(b), "travelMode": self.MODES[mode]},
            headers={
                "X-Goog-Api-Key": self._key,
                "X-Goog-FieldMask": "routes.duration,routes.distanceMeters",
            },
        )
        try:
            route = data["routes"][0]
            return Leg(
                float(str(route["duration"]).rstrip("s")) / 60.0, float(route["distanceMeters"]), self.name
            )
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise TravelTimeError("google routes: unexpected response") from exc


def encode_polyline(points: list[GeoPoint]) -> str:
    """Google encoded polyline (precision 5)."""
    out: list[str] = []
    prev_lat = prev_lng = 0
    for p in points:
        lat, lng = round(p.lat * 1e5), round(p.lng * 1e5)
        for delta in (lat - prev_lat, lng - prev_lng):
            v = ~(delta << 1) if delta < 0 else delta << 1
            while v >= 0x20:
                out.append(chr((0x20 | (v & 0x1F)) + 63))
                v >>= 5
            out.append(chr(v + 63))
        prev_lat, prev_lng = lat, lng
    return "".join(out)
