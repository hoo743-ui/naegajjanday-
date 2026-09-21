"""Map-facing directions: real walking geometry + "which subway exit / bus stop" access hints.

This is presentation data for the result page. It never feeds back into scoring or the optimizer
(those use `domain.routing.travel_time`), so a slow or dead router can only degrade the drawing:
the walking path falls back to straight segments and the course itself is unaffected.

Transit access hints come from an OpenStreetMap extract kept as plain TSV files under
`data/transit/` (ODbL — stored apart from our own place tables, attribution shown in the UI).
"""

from __future__ import annotations

import csv
import math
from collections import OrderedDict, defaultdict
from dataclasses import dataclass
from functools import lru_cache
from itertools import pairwise
from pathlib import Path
from typing import Any, ClassVar

import httpx
import structlog

from app.core.config import Settings, get_settings
from app.domain.models import GeoPoint
from app.domain.routing.travel_time import DETOUR_FACTOR, SPEED_KMH, haversine_m

log = structlog.get_logger(__name__)

CELL_DEG = 0.005  # ~550 m north-south; a 3x3 neighbourhood covers every search radius used below
SUBWAY_MAX_M = 900.0
BUS_MAX_M = 400.0
STATION_NAME_MAX_M = 450.0
ROUTE_CACHE_SIZE = 512


def walk_minutes(straight_m: float) -> int:
    path_m = straight_m * DETOUR_FACTOR["walk"]
    return max(1, round(path_m / 1000.0 / SPEED_KMH["walk"] * 60.0))


@dataclass(frozen=True, slots=True)
class TransitPoint:
    lat: float
    lng: float
    name: str
    ref: str


class _Grid:
    """Fixed-cell spatial hash. 100k bus stops load in well under a second and queries are O(1)."""

    def __init__(self, points: list[TransitPoint]) -> None:
        self._cells: dict[tuple[int, int], list[TransitPoint]] = defaultdict(list)
        for p in points:
            self._cells[self._key(p.lat, p.lng)].append(p)
        self.size = len(points)

    @staticmethod
    def _key(lat: float, lng: float) -> tuple[int, int]:
        return math.floor(lat / CELL_DEG), math.floor(lng / CELL_DEG)

    def nearest(self, at: GeoPoint, max_m: float) -> tuple[TransitPoint, float] | None:
        cy, cx = self._key(at.lat, at.lng)
        reach = max(1, math.ceil(max_m / 450.0))
        best: tuple[TransitPoint, float] | None = None
        for dy in range(-reach, reach + 1):
            for dx in range(-reach, reach + 1):
                for p in self._cells.get((cy + dy, cx + dx), ()):
                    d = haversine_m(at, GeoPoint(p.lat, p.lng))
                    if d <= max_m and (best is None or d < best[1]):
                        best = (p, d)
        return best


def _read_tsv(path: Path, columns: int) -> list[TransitPoint]:
    if not path.exists():
        return []
    points: list[TransitPoint] = []
    with path.open(encoding="utf-8", newline="") as fh:
        for row in csv.reader(fh, delimiter="\t"):
            if len(row) < 2:
                continue
            try:
                lat, lng = float(row[0]), float(row[1])
            except ValueError:
                continue
            cells = [*row[2:], "", ""][:columns]
            points.append(TransitPoint(lat, lng, *cells))
    return points


class TransitIndex:
    def __init__(self, directory: Path) -> None:
        # subway_entrances.tsv: lat, lon, ref(exit no.), name   · stations.tsv: lat, lon, name
        # bus_stops.tsv: lat, lon, name, ref(stop no.)
        entrances = [
            TransitPoint(p.lat, p.lng, name=p.ref, ref=p.name)
            for p in _read_tsv(directory / "subway_entrances.tsv", 2)
        ]
        self.entrances = _Grid(entrances)
        self.stations = _Grid(_read_tsv(directory / "stations.tsv", 2))
        self.bus_stops = _Grid(_read_tsv(directory / "bus_stops.tsv", 2))
        self._station_names: dict[str, tuple[float, float]] | None = None  # built on first search
        log.info(
            "transit.index_loaded",
            entrances=self.entrances.size,
            stations=self.stations.size,
            bus_stops=self.bus_stops.size,
        )

    def search_stations(self, query: str, limit: int = 8) -> list[dict[str, Any]]:
        """Stations whose name contains `query` — lets people plan around "신도림" or "반포" even though
        those are not administrative regions. One entry per name (lines share a station, OSM has a
        node per line); names that start with the query come first."""
        q = query.strip().removesuffix("역")
        if not q:
            return []
        if self._station_names is None:
            merged: dict[str, list[TransitPoint]] = defaultdict(list)
            for cell in self.stations._cells.values():
                for p in cell:
                    if p.name:
                        merged[p.name.removesuffix("역")].append(p)
            self._station_names = {
                name: (sum(p.lat for p in pts) / len(pts), sum(p.lng for p in pts) / len(pts))
                for name, pts in merged.items()
            }
        hits = sorted(
            (name for name in self._station_names if q in name),
            key=lambda name: (not name.startswith(q), len(name), name),
        )[:limit]
        return [
            {"name": f"{name}역", "lat": self._station_names[name][0], "lng": self._station_names[name][1]}
            for name in hits
        ]

    def subway(self, at: GeoPoint) -> dict[str, Any] | None:
        hit = self.entrances.nearest(at, SUBWAY_MAX_M)
        if hit is None:
            return None
        entrance, dist = hit
        station = entrance.name
        if not station:
            near = self.stations.nearest(GeoPoint(entrance.lat, entrance.lng), STATION_NAME_MAX_M)
            station = near[0].name if near else ""
        if not station:
            return None
        return {
            "station": station if station.endswith("역") else f"{station}역",
            "exit": entrance.ref or None,
            "lat": entrance.lat,
            "lng": entrance.lng,
            "distance_m": round(dist),
            "walk_min": walk_minutes(dist),
        }

    def bus(self, at: GeoPoint) -> dict[str, Any] | None:
        hit = self.bus_stops.nearest(at, BUS_MAX_M)
        if hit is None:
            return None
        stop, dist = hit
        return {
            "name": stop.name,
            "stop_no": stop.ref or None,
            "lat": stop.lat,
            "lng": stop.lng,
            "distance_m": round(dist),
            "walk_min": walk_minutes(dist),
        }


@lru_cache(maxsize=1)
def get_transit_index() -> TransitIndex:
    return TransitIndex(get_settings().transit_dir)


def _leg_coordinates(leg: dict[str, Any]) -> list[list[float]]:
    """One leg's path as [lat, lng] pairs, stitched from its steps (consecutive steps share a vertex)."""
    out: list[list[float]] = []
    for step in leg.get("steps", ()):
        for lng, lat in step["geometry"]["coordinates"]:
            if not out or out[-1] != [lat, lng]:
                out.append([lat, lng])
    return out


class DirectionsService:
    """Walking geometry through an OSRM-compatible foot router, with a bounded in-process cache."""

    _cache: ClassVar[OrderedDict[str, dict[str, Any]]] = OrderedDict()

    def __init__(self, settings: Settings | None = None, client: httpx.AsyncClient | None = None) -> None:
        self._settings = settings or get_settings()
        self._client = client

    @staticmethod
    def straight(points: list[GeoPoint]) -> dict[str, Any]:
        legs = []
        for a, b in pairwise(points):
            d = haversine_m(a, b)
            legs.append(
                {
                    "distance_m": round(d * DETOUR_FACTOR["walk"]),
                    "duration_min": walk_minutes(d),
                    "coordinates": [[a.lat, a.lng], [b.lat, b.lng]],
                }
            )
        return {
            "source": "straight",
            "coordinates": [[p.lat, p.lng] for p in points],
            "legs": legs,
            "distance_m": sum(leg["distance_m"] for leg in legs),
            "duration_min": sum(leg["duration_min"] for leg in legs),
        }

    async def walk(self, points: list[GeoPoint]) -> dict[str, Any]:
        base = self._settings.osrm_foot_url.rstrip("/")
        if not base or len(points) < 2:
            return self.straight(points)
        key = ";".join(f"{p.lng:.5f},{p.lat:.5f}" for p in points)
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        url = f"{base}/route/v1/foot/{key}"
        # steps=true only for the per-leg geometry: the map colours each leg by its destination, and
        # guessing the leg boundary from the overview breaks when a course doubles back on one street.
        params = {"overview": "full", "geometries": "geojson", "steps": "true"}
        try:
            if self._client is not None:
                res = await self._client.get(url, params=params)
            else:
                async with httpx.AsyncClient(timeout=self._settings.directions_timeout_s) as client:
                    res = await client.get(url, params=params)
            res.raise_for_status()
            body = res.json()
            route = body["routes"][0]
            result = {
                "source": "osrm",
                # GeoJSON is [lng, lat]; the web map wants [lat, lng]
                "coordinates": [[lat, lng] for lng, lat in route["geometry"]["coordinates"]],
                "legs": [
                    {
                        "distance_m": round(leg["distance"]),
                        "duration_min": max(1, round(leg["duration"] / 60)),
                        "coordinates": _leg_coordinates(leg),
                    }
                    for leg in route["legs"]
                ],
                "distance_m": round(route["distance"]),
                "duration_min": max(1, round(route["duration"] / 60)),
            }
        except (httpx.HTTPError, KeyError, IndexError, ValueError) as exc:
            log.warning("directions.walk_fallback", error=str(exc)[:200])
            return self.straight(points)
        self._cache[key] = result
        if len(self._cache) > ROUTE_CACHE_SIZE:
            self._cache.popitem(last=False)
        return result
