"""Official marks for places we already have: designations (백년가게, 모범음식점) and licence facts
(인허가일자 → how long the place has been open, 단란주점 / 유흥주점 → not a course candidate).

None of these files creates a place. Each row is matched to an existing place and leaves
  * a `place_source` row (provider = the mark) — provenance, and what a re-run replaces,
  * optionally a `place_tag` (source = "provider"),
  * optionally `place.status = "hidden"` (adult entertainment venues).

Matching is an ADDRESS JOIN, the same idea as 착한가격업소: same 시도 + 시군구 + road name + building
number ⇒ same building, then the shop name decides. The licence files do carry coordinates, but in
EPSG:5174 without the correction term and several of these files have none at all, so the address
is both simpler and more exact. Everything tunable lives in `bulk_rules.json › marks`.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from app.infra.ingestion import dedupe
from app.infra.ingestion.bulk.common import BulkReport
from app.infra.ingestion.bulk.goodprice import AddressKey, address_key


@dataclass(frozen=True, slots=True)
class MarkRow:
    external_id: str
    name: str
    key: AddressKey
    raw: dict[str, Any]
    licensed_on: date | None = None


@dataclass(frozen=True, slots=True)
class MarkMatch:
    row: MarkRow
    place_id: int
    similarity: float

    @property
    def content_hash(self) -> str:
        blob = json.dumps([self.row.name, self.row.raw, self.place_id], ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def parse_date(value: str | None) -> date | None:
    """'1993-11-12', '19931112' or '1993.11.12' — anything else (or an impossible date) is None."""
    digits = "".join(ch for ch in (value or "") if ch.isdigit())
    if len(digits) != 8:
        return None
    try:
        return date(int(digits[:4]), int(digits[4:6]), int(digits[6:]))
    except ValueError:
        return None


def is_current(row: Mapping[str, str], spec: Mapping[str, Any]) -> bool:
    """Open for business, and — for a designation — not revoked (a later re-designation wins)."""
    status_col = spec.get("status_column")
    if status_col and row.get(status_col, "") not in set(spec.get("open_values", [])):
        return False
    revoked_col = spec.get("revoked_column")
    if revoked_col:
        revoked = parse_date(row.get(revoked_col))
        again = parse_date(row.get(str(spec.get("redesignated_column", ""))))
        if revoked is not None and (again is None or again <= revoked):
            return False
    return True


def iter_rows(
    rows: Iterable[Mapping[str, str]],
    spec: Mapping[str, Any],
    report: BulkReport,
    sido_aliases: Mapping[str, str] | None = None,
) -> Iterator[MarkRow]:
    name_col, id_col = str(spec["name_column"]), spec.get("id_column")
    address_cols = [str(c) for c in spec["address_columns"]]
    keep = [str(c) for c in spec.get("keep_columns", [])]
    licensed_col = spec.get("licensed_column")
    for row in rows:
        report.read += 1
        if not is_current(row, spec):
            report.skip("not_current")
            continue
        name = row.get(name_col, "").strip()
        key = next((k for c in address_cols if (k := address_key(row.get(c, ""), sido_aliases))), None)
        if not name:
            report.skip("no_name")
            continue
        if key is None:
            report.skip("no_road_address")
            continue
        address = next((row[c] for c in address_cols if row.get(c)), "")
        external_id = (row.get(str(id_col), "") if id_col else "") or hashlib.sha1(
            f"{name}|{address}".encode()
        ).hexdigest()[:20]
        yield MarkRow(
            external_id=external_id,
            name=name,
            key=key,
            raw={"name": name, "address": address, **{c: row[c] for c in keep if row.get(c)}},
            licensed_on=parse_date(row.get(str(licensed_col))) if licensed_col else None,
        )


@dataclass(slots=True)
class PlaceAddressIndex:
    """building → the places in it. ~800k short tuples: fine in memory, and one pass over `place`."""

    _by_key: dict[AddressKey, list[tuple[int, str]]] = field(default_factory=lambda: defaultdict(list))

    def add(self, place_id: int, name: str, road_address: str | None, aliases: Mapping[str, str]) -> None:
        key = address_key(road_address or "", aliases)
        if key is not None:
            self._by_key[key].append((place_id, name))

    def __len__(self) -> int:
        return len(self._by_key)

    def best(self, row: MarkRow, min_similarity: float) -> tuple[int, float] | None:
        best: tuple[int, float] | None = None
        for place_id, name in self._by_key.get(row.key, ()):
            sim = dedupe.name_similarity(row.name, name)
            if sim >= min_similarity and (best is None or sim > best[1]):
                best = (place_id, sim)
        return best


def match_rows(
    rows: Iterable[MarkRow], index: PlaceAddressIndex, min_similarity: float, report: BulkReport
) -> list[MarkMatch]:
    """One mark per place: when two rows claim the same place the closer name keeps it."""
    by_place: dict[int, MarkMatch] = {}
    seen: set[str] = set()
    for row in rows:
        if row.external_id in seen:
            report.skip("duplicate_id")
            continue
        seen.add(row.external_id)
        found = index.best(row, min_similarity)
        if found is None:
            report.skip("no_matching_place")
            continue
        report.mapped += 1
        current = by_place.get(found[0])
        if current is None or found[1] > current.similarity:
            by_place[found[0]] = MarkMatch(row, found[0], round(found[1], 3))
    return list(by_place.values())


def years_open(licensed_on: date | None, today: date) -> int | None:
    if licensed_on is None or licensed_on > today:
        return None
    before_anniversary = (today.month, today.day) < (licensed_on.month, licensed_on.day)
    return today.year - licensed_on.year - int(before_anniversary)


def tags_for(match: MarkMatch, spec: Mapping[str, Any], today: date) -> dict[str, float]:
    """`tag` = every matched place gets it; `age_tags` = only places licensed that many years ago."""
    out: dict[str, float] = {}
    if spec.get("tag"):
        out[str(spec["tag"])] = float(spec.get("tag_weight", 1.0))
    age = years_open(match.row.licensed_on, today)
    if age is not None:
        for rule in sorted(spec.get("age_tags", []), key=lambda r: -int(r["min_years"])):
            if age >= int(rule["min_years"]):
                out[str(rule["tag"])] = float(rule.get("weight", 1.0))
                break
    return out
