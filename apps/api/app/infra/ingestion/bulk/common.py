"""Shared pieces of the bulk path: CSV streaming (zip / dir / file, UTF-8 or CP949), rule files, the
canonical `BulkPlace` row and a grid-bucket spatial index for cross-source duplicate detection."""

from __future__ import annotations

import codecs
import csv
import hashlib
import io
import json
import zipfile
from collections import defaultdict
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import IO, Any

from app.core.config import API_ROOT
from app.infra.ingestion import dedupe
from app.infra.ingestion.base import NormalizedHour, NormalizedMenu

BULK_DATA_DIR = API_ROOT / "data" / "bulk"
SNIFF_BYTES = 1 << 16
GRID_CELL_DEG = 0.001  # ≈ 110 m north-south, ≈ 90 m east-west at 36°N
KOREA_LAT = (32.5, 39.0)
KOREA_LNG = (124.0, 132.0)


def load_json(name: str, directory: Path = BULK_DATA_DIR) -> dict[str, Any]:
    data = json.loads((directory / name).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{name}: expected a JSON object")
    return data


def sniff_encoding(head: bytes) -> str:
    """Public CSVs come as UTF-8 (with or without BOM) or CP949. A cut multi-byte tail is not an error."""
    decoder = codecs.getincrementaldecoder("utf-8")()
    try:
        decoder.decode(head, final=False)
    except UnicodeDecodeError:
        return "cp949"
    return "utf-8-sig"


def _rows(stream: IO[bytes]) -> Iterator[dict[str, str]]:
    head = stream.read(SNIFF_BYTES)
    encoding = sniff_encoding(head)
    chained = io.BufferedReader(_Chain(head, stream))
    text = io.TextIOWrapper(chained, encoding=encoding, errors="replace", newline="")
    reader = csv.DictReader(text)
    for row in reader:
        yield {(k or "").strip(): (v or "").strip() for k, v in row.items() if k is not None}


class _Chain(io.RawIOBase):
    """Re-attach the sniffed head in front of a non-seekable stream (zip members cannot seek cheaply)."""

    def __init__(self, head: bytes, rest: IO[bytes]) -> None:
        self._head = head
        self._rest = rest

    def readable(self) -> bool:
        return True

    def readinto(self, buffer: Any) -> int:
        if self._head:
            n = min(len(buffer), len(self._head))
            buffer[:n] = self._head[:n]
            self._head = self._head[n:]
            return n
        chunk = self._rest.read(len(buffer))
        buffer[: len(chunk)] = chunk
        return len(chunk)


def zip_member_name(info: zipfile.ZipInfo) -> str:
    """Korean zip tools often store CP949 names without the UTF-8 flag."""
    if info.flag_bits & 0x800:
        return info.filename
    try:
        return info.filename.encode("cp437").decode("cp949")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return info.filename


def csv_members(path: Path) -> list[str]:
    """Logical CSV names inside `path` (zip members, files of a directory, or the file itself)."""
    if path.is_dir():
        return sorted(p.name for p in path.glob("*.csv"))
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as zf:
            return [zip_member_name(i) for i in zf.infolist() if zip_member_name(i).lower().endswith(".csv")]
    return [path.name]


def iter_csv(path: Path, member: str | None = None) -> Iterator[dict[str, str]]:
    """Stream rows as dicts; never loads a whole file. `member` selects one CSV of a zip / directory."""
    if path.is_dir():
        for name in csv_members(path):
            if member is None or name == member:
                with (path / name).open("rb") as fh:
                    yield from _rows(fh)
        return
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as zf:
            for info in zf.infolist():
                name = zip_member_name(info)
                if name.lower().endswith(".csv") and (member is None or name == member):
                    with zf.open(info) as fh:
                        yield from _rows(fh)
        return
    with path.open("rb") as fh:
        yield from _rows(fh)


def to_float(value: str | None) -> float | None:
    try:
        return float(value) if value else None
    except ValueError:
        return None


def in_korea(lat: float | None, lng: float | None) -> bool:
    if lat is None or lng is None:
        return False
    return KOREA_LAT[0] <= lat <= KOREA_LAT[1] and KOREA_LNG[0] <= lng <= KOREA_LNG[1]


@dataclass(slots=True)
class BulkPlace:
    provider: str
    external_id: str
    name: str
    category_code: str
    lat: float
    lng: float
    sido: str | None = None
    sigungu: str | None = None
    address: str | None = None
    road_address: str | None = None
    phone: str | None = None
    description: str | None = None
    price_per_person: int | None = None
    price_is_estimated: bool = False
    is_free: bool = False
    menus: list[NormalizedMenu] = field(default_factory=list)
    hours: list[NormalizedHour] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)
    merge_into_place_id: int | None = None  # cross-source duplicate → enrich that place instead
    thumbnail_url: str | None = None  # a real photo of THIS place (TourAPI); never a category stand-in
    images: list[str] = field(default_factory=list)

    @property
    def content_hash(self) -> str:
        blob = json.dumps(
            [
                self.name,
                self.category_code,
                round(self.lat, 6),
                round(self.lng, 6),
                self.address,
                self.road_address,
                self.phone,
                self.description,
                self.price_per_person,
                self.price_is_estimated,
                self.is_free,
                [(m.name, m.price) for m in self.menus],
                [(h.dow, h.open_time, h.close_time, h.is_closed) for h in self.hours],
                self.merge_into_place_id,
                self.thumbnail_url,
            ],
            ensure_ascii=False,
            separators=(",", ":"),
        )
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()


@dataclass(slots=True)
class BulkEvent:
    provider: str
    external_id: str
    title: str
    category_code: str
    lat: float
    lng: float
    starts_on: date
    ends_on: date
    description: str | None = None
    address: str | None = None
    booking_url: str | None = None
    images: list[str] = field(default_factory=list)


@dataclass(slots=True)
class BulkReport:
    read: int = 0
    mapped: int = 0
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    merged: int = 0
    skipped: int = 0
    closed: int = 0
    reopened: int = 0
    skip_reasons: dict[str, int] = field(default_factory=lambda: defaultdict(int))

    def skip(self, reason: str) -> None:
        self.skipped += 1
        self.skip_reasons[reason] += 1

    def line(self) -> str:
        reasons = ", ".join(f"{k}={v}" for k, v in sorted(self.skip_reasons.items(), key=lambda t: -t[1]))
        return (
            f"read={self.read} mapped={self.mapped} created={self.created} updated={self.updated} "
            f"unchanged={self.unchanged} merged={self.merged} closed={self.closed} reopened={self.reopened} "
            f"skipped={self.skipped}" + (f" ({reasons})" if reasons else "")
        )


class GridIndex:
    """Spatial pre-filter for duplicate detection: ~100 m buckets, 3×3 neighbourhood lookup.

    Same scoring as `dedupe.find_match` (name similarity + distance < 50 m) without its linear scan.
    """

    def __init__(self, cell_deg: float = GRID_CELL_DEG) -> None:
        self._cell = cell_deg
        self._cells: dict[tuple[int, int], list[dedupe.ExistingPlace]] = defaultdict(list)

    def cell_of(self, lat: float, lng: float) -> tuple[int, int]:
        return int(lat // self._cell), int(lng // self._cell)

    def neighbourhood(self, lat: float, lng: float) -> list[tuple[int, int]]:
        ci, cj = self.cell_of(lat, lng)
        return [(ci + di, cj + dj) for di in (-1, 0, 1) for dj in (-1, 0, 1)]

    def add(self, place: dedupe.ExistingPlace) -> None:
        self._cells[self.cell_of(place.lat, place.lng)].append(place)

    def __len__(self) -> int:
        return sum(len(v) for v in self._cells.values())

    def near(self, lat: float, lng: float) -> list[dedupe.ExistingPlace]:
        out: list[dedupe.ExistingPlace] = []
        for cell in self.neighbourhood(lat, lng):
            out.extend(self._cells.get(cell, ()))
        return out

    def find_match(self, name: str, lat: float, lng: float, phone: str | None = None) -> dedupe.Match | None:
        return dedupe.find_match(name, lat, lng, phone, self.near(lat, lng))

    def best_by_name(
        self, name: str, lat: float, lng: float, *, radius_m: float, min_similarity: float
    ) -> dedupe.ExistingPlace | None:
        """Address-joined sources share the building, so the name decides; distance only bounds it."""
        best: tuple[float, dedupe.ExistingPlace] | None = None
        for cand in self.near(lat, lng):
            if dedupe.distance_m(lat, lng, cand.lat, cand.lng) > radius_m:
                continue
            sim = dedupe.name_similarity(name, cand.name)
            if sim >= min_similarity and (best is None or sim > best[0]):
                best = (sim, cand)
        return best[1] if best else None


def chunked[T](items: Sequence[T], size: int) -> Iterator[Sequence[T]]:
    for i in range(0, len(items), size):
        yield items[i : i + size]
