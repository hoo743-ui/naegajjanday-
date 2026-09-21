"""행정안전부 착한가격업소 현황 (data.go.kr 3045247) — the only public source with real MENU + PRICE.

The file has addresses but no coordinates and we have no geocoder key, so coordinates come from an
address join with the 상가(상권)정보 file: same 시군구 + road name + building number ⇒ same building.
A good-price row that also matches an already loaded store by name enriches that place (measured
price, menus, phone); otherwise it becomes a new place at the building's coordinates. Rows whose
address is not in the store file are skipped.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from app.infra.ingestion.base import NormalizedMenu
from app.infra.ingestion.bulk.common import BulkPlace, BulkReport, GridIndex, to_float
from app.infra.ingestion.bulk.semas_store import COL_LAT, COL_LNG, COL_ROAD_ADDRESS
from app.infra.ingestion.price import price_per_person

PROVIDER = "goodprice"
MAPPING_KEY = "goodprice"
MENU_SLOTS = 4
_PAREN_RE = re.compile(r"\([^)]*\)")
_ROAD_RE = re.compile(r"([가-힣A-Za-z0-9·.]+(?:로|길))\s*(\d+(?:-\d+)?)")
_SIGUNGU_RE = re.compile(r"([가-힣]+(?:시|군|구))\s")
_PRICE_RE = re.compile(r"\d+")

AddressKey = tuple[str, str, str, str]


def address_key(address: str, sido_aliases: Mapping[str, str] | None = None) -> AddressKey | None:
    """('서울특별시', '종로구', '대학로5길', '5') from '서울특별시 종로구 대학로5길 5 (연건동)'.

    `sido_aliases` folds old / short 시도 names onto the canonical one so both files agree.
    None when the text is not a road address.
    """
    text = _PAREN_RE.sub(" ", address or "").replace(",", " ").strip()
    road = _ROAD_RE.search(text)
    if road is None:
        return None
    districts = _SIGUNGU_RE.findall(text[: road.start()] + " ")
    if not districts:
        return None
    sido = text.split(" ", 1)[0]
    sido = (sido_aliases or {}).get(sido, sido)
    return sido, districts[-1], road.group(1), road.group(2)


def parse_price(value: str) -> int | None:
    digits = "".join(_PRICE_RE.findall((value or "").replace(",", "")))
    if not digits:
        return None
    price = int(digits)
    return price if 500 <= price <= 300_000 else None


def parse_menus(row: Mapping[str, str]) -> list[NormalizedMenu]:
    menus: list[NormalizedMenu] = []
    for i in range(1, MENU_SLOTS + 1):
        name, price = row.get(f"메뉴{i}", "").strip(), parse_price(row.get(f"가격{i}", ""))
        if name and price is not None:
            menus.append(NormalizedMenu(name=name, price=price, is_signature=i == 1))
    return menus


@dataclass(frozen=True, slots=True)
class GoodPriceRow:
    external_id: str
    name: str
    kind: str
    sido: str
    sigungu: str
    address: str
    phone: str | None
    menus: list[NormalizedMenu]
    key: AddressKey


def parse_rows(
    rows: Iterable[Mapping[str, str]],
    rules: Mapping[str, Any],
    report: BulkReport,
    sido_aliases: Mapping[str, str] | None = None,
) -> list[GoodPriceRow]:
    food_kinds = set(rules["food_kinds"])
    out: list[GoodPriceRow] = []
    for row in rows:
        report.read += 1
        name, kind, address = row.get("업소명", ""), row.get("업종", ""), row.get("주소", "")
        if kind not in food_kinds:
            report.skip("not_food")
            continue
        menus = parse_menus(row)
        key = address_key(address, sido_aliases)
        if not name or not menus:
            report.skip("no_menu")
            continue
        if key is None:
            report.skip("no_road_address")
            continue
        digest = hashlib.sha1(f"{name}|{address}".encode()).hexdigest()[:20]
        out.append(
            GoodPriceRow(
                external_id=digest,
                name=name,
                kind=kind,
                sido=row.get("시도", ""),
                sigungu=row.get("시군", ""),
                address=_PAREN_RE.sub("", address).strip(),
                phone=row.get("연락처") or None,
                menus=menus,
                key=key,
            )
        )
    return out


def building_coords(
    store_rows: Iterable[Mapping[str, str]],
    wanted: set[AddressKey],
    sido_aliases: Mapping[str, str] | None = None,
) -> dict[AddressKey, tuple[float, float]]:
    """Address join against the store file (every business type — we only need the building)."""
    sums: dict[AddressKey, tuple[float, float, int]] = {}
    for row in store_rows:
        key = address_key(row.get(COL_ROAD_ADDRESS, ""), sido_aliases)
        if key is None or key not in wanted:
            continue
        lat, lng = to_float(row.get(COL_LAT)), to_float(row.get(COL_LNG))
        if lat is None or lng is None:
            continue
        a, b, n = sums.get(key, (0.0, 0.0, 0))
        sums[key] = (a + lat, b + lng, n + 1)
    return {k: (round(a / n, 7), round(b / n, 7)) for k, (a, b, n) in sums.items()}


def category_for(row: GoodPriceRow, by_kind: Mapping[str, str], rules: Mapping[str, Any]) -> str:
    if row.kind in by_kind:
        return by_kind[row.kind]
    text = " ".join(m.name for m in row.menus) + " " + row.name
    for code, keywords in rules.get("other_menu_keywords", {}).items():
        if any(k in text for k in keywords):
            return str(code)
    return str(rules.get("other_default_category", "food"))


def to_places(
    rows: Sequence[GoodPriceRow],
    coords: Mapping[AddressKey, tuple[float, float]],
    existing: GridIndex,
    by_kind: Mapping[str, str],
    rules: Mapping[str, Any],
    report: BulkReport,
) -> Iterator[BulkPlace]:
    for row in rows:
        point = coords.get(row.key)
        if point is None:
            report.skip("address_not_in_store_file")
            continue
        match = existing.best_by_name(
            row.name,
            point[0],
            point[1],
            radius_m=float(rules.get("match_radius_m", 60)),
            min_similarity=float(rules.get("name_match_min", 0.75)),
        )
        report.mapped += 1
        yield BulkPlace(
            provider=PROVIDER,
            external_id=row.external_id,
            name=row.name,
            category_code=category_for(row, by_kind, rules),
            lat=point[0],
            lng=point[1],
            sido=row.sido or None,
            sigungu=row.sigungu or None,
            road_address=row.address or None,
            phone=row.phone,
            price_per_person=price_per_person(row.menus),
            price_is_estimated=False,
            menus=row.menus,
            raw={"kind": row.kind, "sido": row.sido, "sigungu": row.sigungu, "address": row.address},
            merge_into_place_id=match.id if match else None,
        )
