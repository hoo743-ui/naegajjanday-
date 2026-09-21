"""Nationwide regions as DATA: 시도 (level 1) and 시군구 (level 2) are derived from the store file itself
(densest commercial centre + distance percentile), level-3 hotspots come from `regions_kr.json`.
Rows are upserted through the same `upsert_regions` the seed config uses — the engine never sees names."""

from __future__ import annotations

import math
from array import array
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.infra.db.models import Region
from app.infra.ingestion.config_loader import upsert_regions
from app.infra.ingestion.dedupe import distance_m

CENTER_CELL_DEG = 0.005  # ≈ 500 m buckets for the "densest centre" search
_INITIALS = [
    "g",
    "kk",
    "n",
    "d",
    "tt",
    "r",
    "m",
    "b",
    "pp",
    "s",
    "ss",
    "",
    "j",
    "jj",
    "ch",
    "k",
    "t",
    "p",
    "h",
]
_VOWELS = [
    "a", "ae", "ya", "yae", "eo", "e", "yeo", "ye", "o", "wa", "wae", "oe", "yo", "u", "wo", "we", "wi",
    "yu", "eu", "ui", "i",
]  # fmt: skip
_FINALS = [
    "", "k", "k", "k", "n", "n", "n", "t", "l", "k", "m", "l", "l", "l", "p", "l", "m", "p", "p", "t",
    "t", "ng", "t", "t", "k", "t", "p", "t",
]  # fmt: skip
_ADMIN_SUFFIXES = ("특별자치시", "특별자치도", "특별시", "광역시")


def romanize(text: str) -> str:
    """Syllable-wise Revised Romanization (no assimilation) — only used to build stable slugs."""
    out: list[str] = []
    for ch in text:
        code = ord(ch) - 0xAC00
        if 0 <= code < 11172:
            out.append(_INITIALS[code // 588] + _VOWELS[(code % 588) // 28] + _FINALS[code % 28])
        elif ch.isascii() and ch.isalnum():
            out.append(ch.lower())
    return "".join(out)


def _strip_admin_suffix(token: str) -> str:
    for suffix in _ADMIN_SUFFIXES:
        if token.endswith(suffix) and len(token) > len(suffix):
            return token[: -len(suffix)]
    if len(token) >= 2 and token[-1] in "시군구":
        return token[:-1]
    return token


def sigungu_slug(sido_slug: str, sigungu: str) -> str:
    """'마포구' → seoul-mapo, '수원시 팔달구' → gyeonggi-suwon-paldal."""
    parts = [romanize(_strip_admin_suffix(tok)) for tok in sigungu.split()]
    return "-".join([sido_slug, *[p for p in parts if p]])


@dataclass(slots=True)
class PointCloud:
    lats: array[float] = field(default_factory=lambda: array("d"))
    lngs: array[float] = field(default_factory=lambda: array("d"))

    def add(self, lat: float, lng: float) -> None:
        self.lats.append(lat)
        self.lngs.append(lng)

    def __len__(self) -> int:
        return len(self.lats)


class RegionStats:
    """Accumulates store coordinates per 시도 and per (시도, 시군구) while the file streams by."""

    def __init__(self) -> None:
        self.sido: dict[str, PointCloud] = defaultdict(PointCloud)
        self.sigungu: dict[tuple[str, str], PointCloud] = defaultdict(PointCloud)

    def add(self, sido: str, sigungu: str, lat: float, lng: float) -> None:
        if not sido or not sigungu:
            return
        self.sido[sido].add(lat, lng)
        self.sigungu[(sido, sigungu)].add(lat, lng)


def dense_center(cloud: PointCloud) -> tuple[float, float]:
    """Centre of the busiest ~1.5 km block: a county's town centre, not the empty mean between towns."""
    counts: dict[tuple[int, int], int] = defaultdict(int)
    for lat, lng in zip(cloud.lats, cloud.lngs, strict=True):
        counts[(int(lat // CENTER_CELL_DEG), int(lng // CENTER_CELL_DEG))] += 1

    def block(cell: tuple[int, int]) -> int:
        return sum(counts.get((cell[0] + di, cell[1] + dj), 0) for di in (-1, 0, 1) for dj in (-1, 0, 1))

    best = max(counts, key=lambda c: (block(c), counts[c], c))
    lat_sum = lng_sum = 0.0
    n = 0
    for lat, lng in zip(cloud.lats, cloud.lngs, strict=True):
        ci, cj = int(lat // CENTER_CELL_DEG), int(lng // CENTER_CELL_DEG)
        if abs(ci - best[0]) <= 1 and abs(cj - best[1]) <= 1:
            lat_sum, lng_sum, n = lat_sum + lat, lng_sum + lng, n + 1
    return round(lat_sum / n, 6), round(lng_sum / n, 6)


def percentile_radius(
    cloud: PointCloud, center: tuple[float, float], percentile: float, lo: int, hi: int
) -> int:
    dists = sorted(
        distance_m(center[0], center[1], lat, lng) for lat, lng in zip(cloud.lats, cloud.lngs, strict=True)
    )
    raw = dists[min(len(dists) - 1, int(len(dists) * percentile))] if dists else lo
    return int(max(lo, min(hi, math.ceil(raw / 100.0) * 100)))


def build_region_rows(spec: Mapping[str, Any], stats: RegionStats) -> list[dict[str, Any]]:
    """Rows in the `regions.json` shape, parents first. Only 시도 listed in the spec are generated."""
    rows: list[dict[str, Any]] = []
    sido_spec = {s["name"]: s for s in spec["sido"]}
    limits = spec["radius"]
    slugs: set[str] = set()
    sigungu_slugs: dict[tuple[str, str], str] = {}

    for name, cloud in sorted(stats.sido.items()):
        s = sido_spec.get(name)
        if s is None or not len(cloud):
            continue
        center = tuple(s["center"]) if s.get("center") else dense_center(cloud)
        lim = limits["sido"]
        radius = s.get("radius_m") or percentile_radius(
            cloud, (center[0], center[1]), lim["percentile"], lim["min_m"], lim["max_m"]
        )
        rows.append(_row(s["slug"], name, 1, None, (center[0], center[1]), int(radius), s.get("area_code")))
        slugs.add(s["slug"])

    for (sido, sigungu), cloud in sorted(stats.sigungu.items()):
        s = sido_spec.get(sido)
        if s is None or not len(cloud):
            continue
        slug = sigungu_slug(s["slug"], sigungu)
        if slug in slugs:  # 세종: the only 시군구 carries the 시도 name
            slug = f"{slug}-si"
        slugs.add(slug)
        sigungu_slugs[(sido, sigungu)] = slug
        center = dense_center(cloud)
        lim = limits["sigungu"]
        radius = percentile_radius(cloud, center, lim["percentile"], lim["min_m"], lim["max_m"])
        rows.append(_row(slug, sigungu, 2, s["slug"], center, radius, None))

    for h in spec.get("hotspots", []):
        parent = sigungu_slugs.get((h["sido"], h["sigungu"]))
        if parent is None:  # that 시도 is not loaded (yet)
            continue
        if h["slug"] in slugs:
            # Rows are upserted by slug: a hotspot named like its 시군구 ("busan-haeundae" for 해운대구)
            # would overwrite that row and end up as its own parent. Fail loudly — fix the data file.
            raise ValueError(f"hotspot slug '{h['slug']}' collides with a generated 시도/시군구 slug")
        slugs.add(h["slug"])
        keywords = [f"{h['name']} {w}" for w in ("맛집", "카페", "술집", "가볼만한곳")]
        rows.append(
            _row(h["slug"], h["name"], 3, parent, tuple(h["center"]), int(h["radius_m"]), None, keywords)
        )
    return rows


def _row(
    slug: str,
    name: str,
    level: int,
    parent: str | None,
    center: tuple[float, ...],
    radius_m: int,
    area_code: str | None,
    keywords: Iterable[str] = (),
) -> dict[str, Any]:
    return {
        "slug": slug,
        "name": name,
        "level": level,
        "parent": parent,
        "center_lat": float(center[0]),
        "center_lng": float(center[1]),
        "radius_m": radius_m,
        "area_code": area_code,
        "status": "active",
        "search_keywords": list(keywords),
    }


async def upsert_generated_regions(session: AsyncSession, rows: list[dict[str, Any]]) -> int:
    """Keeps hand-entered `area_code`s of rows that already exist (the generator does not know them)."""
    # A region that is its own parent is never valid, and the ORM cannot even flush such a row
    # (CircularDependencyError). Detach it first; the upsert below gives it the right parent again.
    await session.execute(update(Region).where(Region.parent_id == Region.id).values(parent_id=None))
    await session.flush()
    existing = {r.slug: r.area_code for r in (await session.scalars(select(Region))).all()}
    for row in rows:
        if row.get("area_code") is None:
            row["area_code"] = existing.get(row["slug"])
    return await upsert_regions(session, rows)


@dataclass(frozen=True, slots=True)
class _Spot:
    id: int
    lat: float
    lng: float
    radius_m: int


class RegionIndex:
    """place → most specific region: containing hotspot, else its 시군구, else the nearest 시군구."""

    def __init__(self, regions: Iterable[Region], sido_aliases: Mapping[str, str]) -> None:
        self._aliases = dict(sido_aliases)
        self._hotspots: list[_Spot] = []
        self._sigungu: dict[tuple[str, str], int] = {}
        self._level2: list[tuple[str, _Spot]] = []
        by_id = {r.id: r for r in regions}
        for r in by_id.values():
            spot = _Spot(r.id, r.center_lat, r.center_lng, r.radius_m)
            if r.level == 3:
                self._hotspots.append(spot)
            elif r.level == 2:
                parent = by_id.get(r.parent_id) if r.parent_id else None
                sido = parent.name if parent else ""
                self._sigungu[(sido, r.name)] = r.id
                self._level2.append((sido, spot))

    @classmethod
    async def load(cls, session: AsyncSession, spec: Mapping[str, Any]) -> RegionIndex:
        aliases = {a: s["name"] for s in spec["sido"] for a in (s["name"], *s.get("aliases", []))}
        return cls((await session.scalars(select(Region))).all(), aliases)

    def canonical_sido(self, sido: str | None) -> str | None:
        return self._aliases.get(sido or "", sido)

    def hotspot_at(self, lat: float, lng: float) -> int | None:
        """The containing hotspot; overlapping ones are ranked by distance relative to their radius."""
        best: tuple[float, int] | None = None
        for h in self._hotspots:
            if abs(lat - h.lat) > 0.03 or abs(lng - h.lng) > 0.03:
                continue
            ratio = distance_m(lat, lng, h.lat, h.lng) / h.radius_m
            if ratio <= 1.0 and (best is None or ratio < best[0]):
                best = (ratio, h.id)
        return best[1] if best is not None else None

    def locate(
        self, lat: float, lng: float, sido: str | None = None, sigungu: str | None = None
    ) -> int | None:
        hotspot = self.hotspot_at(lat, lng)
        if hotspot is not None:
            return hotspot
        canonical = self.canonical_sido(sido)
        if canonical and sigungu and (canonical, sigungu) in self._sigungu:
            return self._sigungu[(canonical, sigungu)]
        nearest: tuple[float, int] | None = None
        for _sido, spot in self._level2:
            d = (lat - spot.lat) ** 2 + ((lng - spot.lng) * 0.8) ** 2
            if nearest is None or d < nearest[0]:
                nearest = (d, spot.id)
        return nearest[1] if nearest else None
