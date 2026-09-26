"""소상공인시장진흥공단 상가(상권)정보 — nationwide open stores (data.go.kr 15083033, file data).

One CSV per 시도 inside a zip (~1.4 GB unpacked, ~2.8 M rows). Rows are streamed straight out of the
zip; only 소분류 codes listed in `category.provider_mapping.semas` are kept (food, cafes, bars and a
few date-friendly activities) and name keywords from `bulk_rules.json` drop canteens, caterers, etc.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.infra.ingestion import place_names
from app.infra.ingestion.bulk.common import BulkPlace, BulkReport, csv_members, in_korea, iter_csv, to_float
from app.infra.ingestion.bulk.price_prior import PricePrior
from app.infra.ingestion.bulk.regions import RegionStats

PROVIDER = "semas"
MAPPING_KEY = "semas"
# load order when time is short: the owner's priority regions first, then the rest alphabetically
SIDO_PRIORITY = ("서울", "부산", "제주", "경기")

COL_ID = "상가업소번호"
COL_NAME = "상호명"
COL_BRANCH = "지점명"
COL_CODE = "상권업종소분류코드"
COL_CODE_NAME = "상권업종소분류명"
COL_SIDO = "시도명"
COL_SIGUNGU = "시군구명"
COL_DONG = "법정동명"
COL_ADDRESS = "지번주소"
COL_ROAD_ADDRESS = "도로명주소"
COL_FLOOR = "층정보"
COL_LNG = "경도"
COL_LAT = "위도"


def ordered_members(path: Path, only: Sequence[str] = ()) -> list[str]:
    """CSV members in priority order; `only` filters by 시도 short name as it appears in the file name."""
    names = csv_members(path)
    if only:
        names = [n for n in names if any(token in n for token in only)]

    def rank(name: str) -> tuple[int, str]:
        for i, token in enumerate(SIDO_PRIORITY):
            if token in name:
                return i, name
        return len(SIDO_PRIORITY), name

    return sorted(names, key=rank)


def code_to_category(categories: Iterable[tuple[str, Mapping[str, Any]]]) -> dict[str, str]:
    """{소분류코드: category.code} from `provider_mapping.semas` — mapping lives in DATA, not here."""
    out: dict[str, str] = {}
    for code, mapping in categories:
        for semas_code in (mapping or {}).get(MAPPING_KEY) or []:
            out[str(semas_code)] = code
    return out


def _compact_upper(text: str) -> str:
    return text.replace(" ", "").upper()


@dataclass(frozen=True, slots=True)
class NameGate:
    """A code kept (or moved) only for names that say what it is: 사진촬영업 → 셀프 사진관 when the name has
    "인생네컷". `exclude` words veto a match (an academy named "…도예공방" is not a one-day class)."""

    category: str
    names: tuple[str, ...]
    override: bool = False
    exclude: tuple[str, ...] = ()

    def matches(self, compact_name: str) -> bool:
        return any(w in compact_name for w in self.names) and not any(w in compact_name for w in self.exclude)

    @classmethod
    def from_data(cls, g: Mapping[str, Any]) -> NameGate:
        return cls(
            category=str(g["category"]),
            names=tuple(_compact_upper(str(w)) for w in g.get("names") or ()),
            override=bool(g.get("override")),
            exclude=tuple(_compact_upper(str(w)) for w in g.get("exclude") or ()),
        )


@dataclass(frozen=True, slots=True)
class SemasMapper:
    categories: Mapping[str, str]
    exclude_keywords: tuple[str, ...]
    prior: PricePrior
    # {code: gates}; one code may lead to several kinds by name (기타 오락장 → 방탈출 · 보드게임카페)
    gated: Mapping[str, tuple[NameGate, ...]] = field(default_factory=dict)

    @classmethod
    def from_data(
        cls, categories: Mapping[str, str], rules: Mapping[str, Any], prior: PricePrior
    ) -> SemasMapper:
        keywords = tuple(rules.get("semas", {}).get("exclude_name_keywords", []))
        gated = {
            str(code): tuple(NameGate.from_data(g) for g in (spec if isinstance(spec, list) else [spec]))
            for code, spec in (rules.get("semas", {}).get("name_gated_codes") or {}).items()
            if not str(code).startswith("_")
        }
        return cls(categories=categories, exclude_keywords=keywords, prior=prior, gated=gated)

    def gate_for(self, row: Mapping[str, str]) -> NameGate | None:
        gates = self.gated.get(row.get(COL_CODE, ""))
        if not gates:
            return None
        name = _compact_upper(row.get(COL_NAME, "") or "")
        return next((g for g in gates if g.matches(name)), None)

    def category_for(self, row: Mapping[str, str]) -> str | None:
        gate = self.gate_for(row)
        if gate is not None:
            return gate.category  # 셀프 사진관 · 타로 카페: the name says what the code does not
        return self.categories.get(row.get(COL_CODE, ""))

    def skip_reason(self, row: Mapping[str, str]) -> str | None:
        if self.category_for(row) is None:
            return "unmapped_category"
        name = row.get(COL_NAME, "")
        if not name or not row.get(COL_ID):
            return "no_name"
        if any(k in name for k in self.exclude_keywords):
            return "excluded_name"
        if not in_korea(to_float(row.get(COL_LAT)), to_float(row.get(COL_LNG))):
            return "bad_coord"
        return None

    def to_place(self, row: Mapping[str, str]) -> BulkPlace | None:
        return None if self.skip_reason(row) is not None else self.build(row)

    def build(self, row: Mapping[str, str]) -> BulkPlace:
        """Caller has already checked `skip_reason(row) is None`."""
        code = row[COL_CODE]
        category = self.category_for(row)
        assert category is not None
        sido = row.get(COL_SIDO) or None
        lat, lng = to_float(row.get(COL_LAT)), to_float(row.get(COL_LNG))
        assert lat is not None and lng is not None
        name = display_name(row.get(COL_NAME, ""), row.get(COL_BRANCH, ""), category)
        # a place moved by its name (타로 카페) is priced as what it is, not as the code it was filed under
        moved = category != self.categories.get(code)
        price = self.prior.estimate(category, sido, None if moved else code, name)
        return BulkPlace(
            provider=PROVIDER,
            external_id=row[COL_ID],
            name=name,
            category_code=category,
            lat=lat,
            lng=lng,
            sido=sido,
            sigungu=row.get(COL_SIGUNGU) or None,
            address=row.get(COL_ADDRESS) or None,
            road_address=row.get(COL_ROAD_ADDRESS) or None,
            price_per_person=price,
            price_is_estimated=price is not None,
            raw={
                "code": code,
                "code_name": row.get(COL_CODE_NAME, ""),
                "sido": sido,
                "sigungu": row.get(COL_SIGUNGU, ""),
                "dong": row.get(COL_DONG, ""),
                "floor": row.get(COL_FLOOR, ""),
            },
        )


# 지점명 칸에 지점이 아니라 법인 꼬리가 들어온 행이 있다 ("커피빈홍대역8번출구점" + "코리아").
# 그대로 붙이면 "커피빈홍대역8번출구점 코리아"가 되어 지도 앱에서 검색되지 않는다.
NOT_A_BRANCH = frozenset({"코리아", "주", "(주)", "㈜", "주식회사", "유한회사", "본사", "법인"})


def display_name(name: str, branch: str, category_code: str = "") -> str:
    # the file writes a comma in a store name as ";" — and several stores at one address the same way
    name, branch = place_names.display_name(name.strip(), category_code), branch.strip()
    if branch and branch not in name and branch not in NOT_A_BRANCH:
        return f"{name} {branch}"
    return name


def iter_places(
    path: Path, mapper: SemasMapper, report: BulkReport, members: Sequence[str]
) -> Iterator[BulkPlace]:
    for member in members:
        for row in iter_csv(path, member):
            report.read += 1
            reason = mapper.skip_reason(row)
            if reason is not None:
                report.skip(reason)
                continue
            report.mapped += 1
            yield mapper.build(row)


def collect_region_stats(path: Path, mapper: SemasMapper, members: Sequence[str]) -> RegionStats:
    """Pass 1: where the (kept) stores are, per 시도 / 시군구 — input for `build_region_rows`."""
    stats = RegionStats()
    for member in members:
        for row in iter_csv(path, member):
            if mapper.skip_reason(row) is None:
                lat, lng = to_float(row.get(COL_LAT)), to_float(row.get(COL_LNG))
                assert lat is not None and lng is not None
                stats.add(row.get(COL_SIDO, ""), row.get(COL_SIGUNGU, ""), lat, lng)
    return stats
