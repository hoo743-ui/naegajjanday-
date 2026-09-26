"""구경하는 가게 (docs/62): retail codes of the 소상공인 file, let in only where the name says what to browse.

The whole 소매 section was left out of the nationwide load (supermarkets, pharmacies, phone shops). A
character shop, a vintage shop, a 소품샵 or a brand's flagship is a destination for people in their 20s and
30s, but its code (장난감 · 여성 의류 · 기념품점 …) says nothing: a 카카오프렌즈 flagship and a toy
wholesaler share one. `data/bulk/shop_rules.json` lists, per kind of shop, the codes to look in, the words
and brands a name must carry and the words that veto it. They become ordinary `NameGate`s of the SEMAS
mapper, so the full load, `delta-export` and a later reload agree on every row.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from functools import lru_cache
from typing import Any

from app.domain.models import GeoPoint
from app.domain.routing.travel_time import haversine_m
from app.infra.ingestion.bulk.common import load_json
from app.infra.ingestion.bulk.semas_store import NameGate

RULES_FILE = "shop_rules.json"
SHOP_PREFIX = "shop"


def _compact_upper(text: str) -> str:
    return text.replace(" ", "").upper()


@lru_cache(maxsize=1)
def shop_rules() -> dict[str, Any]:
    return load_json(RULES_FILE)


def gates(rules: Mapping[str, Any] | None = None) -> dict[str, tuple[NameGate, ...]]:
    """{소분류코드: gates in the order of `types`} — one kind of shop per gate, first match wins."""
    rules = shop_rules() if rules is None else rules
    veto = [str(w) for w in rules.get("exclude_all") or ()]
    out: dict[str, list[NameGate]] = {}
    for kind in rules.get("types") or ():
        words = [*map(str, kind.get("names") or ()), *map(str, (kind.get("brands") or {}).keys())]
        by_code: Mapping[str, Sequence[str]] = kind.get("names_by_code") or {}
        for code in kind.get("codes") or ():
            out.setdefault(str(code), []).append(
                NameGate.from_data(
                    {
                        "category": kind["category"],
                        "names": [*words, *by_code.get(str(code), ())],
                        "exclude": [*veto, *map(str, kind.get("exclude") or ())],
                    }
                )
            )
    return {code: tuple(g) for code, g in out.items()}


def is_shop(category_code: str) -> bool:
    return category_code == SHOP_PREFIX or category_code.startswith(SHOP_PREFIX + ".")


def brand_of(name: str, rules: Mapping[str, Any] | None = None) -> tuple[str, str] | None:
    """(kind of shop, what the brand is — "산리오 캐릭터") when the name carries a listed brand."""
    rules = shop_rules() if rules is None else rules
    compact = _compact_upper(name)
    for kind in rules.get("types") or ():
        for brand, label in (kind.get("brands") or {}).items():
            if _compact_upper(str(brand)) in compact:
                return str(kind["category"]), str(label)
    return None


def dedupe_rows(rows: Iterable[Mapping[str, Any]], within_m: float) -> list[Mapping[str, Any]]:
    """The file lists one store twice under two ids ("라인프렌즈스퀘어성수" ×2, 12 m apart): keep the first
    of the same name within `within_m`, so a course never walks from a shop into the same shop."""
    kept: list[Mapping[str, Any]] = []
    seen: dict[str, list[GeoPoint]] = {}
    for row in rows:
        key = _compact_upper(str(row["name"]))
        here = GeoPoint(lat=float(row["lat"]), lng=float(row["lng"]))
        if any(haversine_m(here, other) <= within_m for other in seen.get(key, ())):
            continue
        seen.setdefault(key, []).append(here)
        kept.append(row)
    return kept
