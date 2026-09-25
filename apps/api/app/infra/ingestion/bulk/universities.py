"""Universities and colleges as places — the anchor of a campus day (docs/34).

Source: 전국대학및전문대학정보표준데이터 (data.go.kr standard data 15107736, keyless; `ingest-bulk download
--source universities`). It has names, campuses and addresses but **no coordinates**, and we do not scrape
a map site for them. A campus is placed where our own nationwide data already has approved places at the
same road (or lot) address — the shops and facilities inside or at the gate of that campus. When that finds
nothing and KAKAO_REST_API_KEY is set, the official Kakao Local keyword API is asked, and its answer is
kept only if it is clearly that school (see `pick_kakao_match`). A school still unplaced is left out rather
than guessed.

Two steps, both idempotent:
  build : raw CSV + the place table  → data/anchors/universities.json   (reviewed, committed like
          data/sports/kbo_stadiums.json)
  load  : data/anchors/universities.json → places in `attraction.campus` (provider std_univ)

Run from apps/api:
  uv run python -m app.cli ingest-bulk universities --step build
  uv run python -m app.cli ingest-bulk universities --step load
"""

from __future__ import annotations

import asyncio
import csv
import json
import re
import statistics
from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import select

from app.core.config import API_ROOT
from app.infra.db.models import Place, PlaceSource
from app.infra.db.session import Database
from app.infra.ingestion.bulk.common import BulkPlace, BulkReport, load_json
from app.infra.ingestion.bulk.regions import RegionIndex
from app.infra.ingestion.bulk.writer import BulkWriter

Log = Callable[[str], None]
DATA_PATH = API_ROOT / "data" / "anchors" / "universities.json"
# Campus names and campuses the standard data does not list (2026-09-26, see its _note)
CAMPUSES_PATH = API_ROOT / "data" / "anchors" / "campuses.json"
# A campus read from a graduate school's address is only another campus when it is this far from the
# school's other campuses (서울대 치의학대학원 at 대학로 101 is 연건캠퍼스, not a third one)
MIN_CAMPUS_GAP_M = 1500.0
DERIVED = ("캠퍼스", "추가")
RAW_FILENAME = "std_universities.csv"
PROVIDER = "std_univ"
CATEGORY = "attraction.campus"
# Schools without a campus to walk around (online / broadcast) are not anchors of a day out
EXCLUDED_KINDS = ("사이버대학", "방송통신대학")
KEPT_LEVELS = ("대학", "전문대학")
# The key is city + road + number (one lot), so its places are one site — but a big campus is one lot
# too (서울대 관악로 1 spans ~2km). Take the median, and drop a match spread wider than any campus.
MAX_SPREAD_M = 3000.0
ATTRIBUTION = (
    "한국대학교육협의회 · 전국대학및전문대학정보표준데이터(공공데이터포털 15107736). "
    "좌표는 같은 주소에 있는 우리 장소 데이터의 중앙값, 없으면 카카오 로컬 검색(coord_source: kakao_local)."
)
CAMPUS_LABEL = {"제2캠퍼": "제2캠퍼스", "제3캠퍼": "제3캠퍼스", "제4캠퍼": "제4캠퍼스", "분교": "분교"}

KAKAO_KEYWORD_URL = "https://dapi.kakao.com/v2/local/search/keyword.json"
KAKAO_DELAY_S = 0.1  # polite pacing; 113 lookups are far below the daily quota
_ROAD_RE = re.compile(r"(\S+(?:로|길))\s*(\d+(?:-\d+)?)")
_LOT_RE = re.compile(r"(\S+(?:동|리|가|읍|면))\s+(산?\d+(?:-\d+)?)")


class UniversityIngestError(RuntimeError):
    pass


def _city(address: str) -> str:
    """The token after the province ("성남시", "강남구", "조치원읍"): short forms of the province differ
    between sources ("경기도" / "경기"), the city token does not."""
    parts = address.split()
    return parts[1] if len(parts) > 1 else ""


def road_key(address: str | None) -> tuple[str, str, str] | None:
    if not address:
        return None
    found = _ROAD_RE.findall(address.split("(")[0])
    if not found:
        return None
    road, number = found[-1]
    return (_city(address), road, number)


def lot_key(address: str | None) -> tuple[str, str, str] | None:
    if not address:
        return None
    found = _LOT_RE.findall(address)
    if not found:
        return None
    area, number = found[-1]
    return (_city(address), area, number)


def slugify(text: str) -> str:
    return re.sub(r"-{2,}", "-", re.sub(r"[^a-z0-9]+", "-", text.lower())).strip("-")


@dataclass(slots=True)
class School:
    name: str
    eng_name: str
    campus: str  # 본교 · 분교 · 제2캠퍼 …
    level: str  # 대학 · 전문대학
    kind: str  # 대학교 · 전문대학 · 교육대학 …
    sido: str
    road_address: str
    lot_address: str
    homepage: str
    phone: str
    label: str = ""  # 캠퍼스 이름 (campuses.json): "메디컬캠퍼스"

    @property
    def display_name(self) -> str:
        """캠퍼스 이름을 알면 "가천대학교 메디컬캠퍼스". 모르면 본교는 학교 이름 그대로, 다른 캠퍼스는
        이름에 캠퍼스가 없으면 시군구를 붙인다 ("홍익대학교 (조치원읍)")."""
        if self.label:
            return f"{self.name} {self.label}"
        if self.campus == "본교" or "(" in self.name or "캠퍼스" in self.name:
            return self.name
        return f"{self.name} ({_city(self.road_address) or self.sido})"


def _clean_address(address: str) -> str:
    return re.sub(r"\s*\([^)]*\)\s*$", "", address).strip()


def campus_label(labels: Mapping[str, Mapping[str, str]], school: str, road_address: str) -> str:
    for where, label in (labels.get(school) or {}).items():
        if re.search(re.escape(where) + r"(?!\d)", road_address):
            return label
    return ""


def load_campuses(path: Path = CAMPUSES_PATH) -> dict[str, Any]:
    if not path.exists():
        return {"labels": {}, "extra": []}
    return json.loads(path.read_text(encoding="utf-8"))


def other_campuses(
    rows: Iterable[Mapping[str, str]],
    kept: Iterable[School],
    extra: Iterable[Mapping[str, str]],
    skip: Mapping[str, Any] | None = None,
) -> list[School]:
    """Campuses that are not rows of their own: a graduate school of a kept university at an address
    none of its campuses has (가천대학교 보건대학원 → 함박뫼로 191, the medical campus), and the
    hand-listed `extra` ones. One per address."""
    main = {s.name: s for s in kept if s.campus == "본교"}
    seen = {(s.name, road_key(s.road_address)) for s in kept}
    found: list[School] = []

    def add(school: School) -> None:
        key = (school.name, road_key(school.road_address))
        if key[1] is None or key in seen or not _city(school.road_address).endswith(("시", "군", "구", "읍")):
            return
        if any(where in school.road_address for where in (skip or {}).get(school.name) or ()):
            return
        seen.add(key)
        found.append(school)

    for row in rows:
        if (row.get("대학구분명") or "").strip() != "대학원":
            continue
        base = (row.get("학교명") or "").strip().split(" ")[0]
        if (head := main.get(base)) is None:
            continue
        add(
            School(
                name=base,
                eng_name=head.eng_name,
                campus="캠퍼스",
                level=head.level,
                kind=head.kind,
                sido=(row.get("시도명") or head.sido).strip(),
                road_address=_clean_address((row.get("소재지도로명주소") or "").strip()),
                lot_address=(row.get("소재지지번주소") or "").strip(),
                homepage=head.homepage,
                phone="",
            )
        )
    for entry in extra:
        head = main.get(str(entry["school"]))
        add(
            School(
                name=str(entry["school"]),
                eng_name=str(entry.get("eng_name") or (head.eng_name if head else "")),
                campus="추가",
                level=head.level if head else "대학",
                kind=head.kind if head else "대학교",
                sido=str(entry.get("sido") or ""),
                road_address=str(entry["road_address"]),
                lot_address=str(entry.get("lot_address") or ""),
                homepage=str(entry.get("homepage") or (head.homepage if head else "")),
                phone="",
            )
        )
    return found


def read_schools(path: Path, campuses: Mapping[str, Any] | None = None) -> list[School]:
    campuses = load_campuses() if campuses is None else campuses
    if not path.exists():
        raise UniversityIngestError(f"{path} 가 없어요 — `ingest-bulk download --source universities` 먼저")
    with path.open(encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))
    kept: dict[tuple[str, str], School] = {}
    for row in rows:
        level = (row.get("대학구분명") or "").strip()
        kind = (row.get("학교구분명") or "").strip()
        if level not in KEPT_LEVELS or any(kind.startswith(k) for k in EXCLUDED_KINDS):
            continue
        school = School(
            name=(row.get("학교명") or "").strip(),
            eng_name=(row.get("학교 영문명") or "").strip(),
            campus=(row.get("본분교구분명") or "본교").strip(),
            level=level,
            kind=kind,
            sido=(row.get("시도명") or "").strip(),
            road_address=(row.get("소재지도로명주소") or "").strip(),
            lot_address=(row.get("소재지지번주소") or "").strip(),
            homepage=(row.get("홈페이지주소") or "").strip(),
            phone=(row.get("대표전화번호") or "").strip(),
        )
        # the same school listed twice at one address ("남서울대학교" · "남서울대학교(산업대)") is one campus
        key = (school.name.split("(")[0], school.road_address)
        if not school.name:
            continue
        if key not in kept or len(school.name) < len(kept[key].name):  # the plain name wins
            kept[key] = school
    schools = list(kept.values())
    schools += other_campuses(rows, schools, campuses.get("extra") or [], campuses.get("skip"))
    labels = campuses.get("labels") or {}
    for school in schools:
        school.label = campus_label(labels, school.name, school.road_address)
    return schools


def _gap_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    return (((a[0] - b[0]) * 111_000) ** 2 + ((a[1] - b[1]) * 88_000) ** 2) ** 0.5


def drop_close_campuses(
    located: list[tuple[School, tuple[float, float, str]]],
) -> tuple[list[tuple[School, tuple[float, float, str]]], list[str]]:
    """A campus found from a graduate school's address that sits next to another campus of the same
    school is that campus (a hospital or a building across the road), not a new one."""
    ordered = sorted(located, key=lambda item: item[0].campus in DERIVED)  # official rows first
    kept: list[tuple[School, tuple[float, float, str]]] = []
    dropped: list[str] = []
    for school, spot in ordered:
        if school.campus in DERIVED and any(
            other.name == school.name and _gap_m(spot[:2], where[:2]) < MIN_CAMPUS_GAP_M
            for other, where in kept
        ):
            dropped.append(f"{school.display_name} · {school.road_address}")
            continue
        kept.append((school, spot))
    return kept, dropped


def _spread_m(points: list[tuple[float, float]]) -> float:
    lats, lngs = [p[0] for p in points], [p[1] for p in points]
    return max((max(lats) - min(lats)) * 111_000, (max(lngs) - min(lngs)) * 88_000)


def locate(
    school: School,
    by_road: Mapping[tuple[str, str, str], list[tuple[float, float]]],
    by_lot: Mapping[tuple[str, str, str], list[tuple[float, float]]],
) -> tuple[float, float, str] | None:
    """(lat, lng, how) from places at the same address; None when nothing (or nothing coherent) matches."""
    for how, key, index in (
        ("road_address", road_key(school.road_address), by_road),
        ("lot_address", lot_key(school.lot_address), by_lot),
    ):
        points = index.get(key) if key else None
        if not points or _spread_m(points) > MAX_SPREAD_M:
            continue
        return statistics.median(p[0] for p in points), statistics.median(p[1] for p in points), how
    return None


def _compact(text: str) -> str:
    return "".join(ch for ch in text if ch.isalnum())


def pick_kakao_match(school: School, documents: Iterable[Mapping[str, Any]]) -> tuple[float, float] | None:
    """The campus among Kakao Local's keyword results, or None. Accepted only when it IS that school:
    a university category, a name that starts with the school's name (not "<shop> <school>점"), and the
    same city as the official address (a branch campus must not borrow the main campus). The shortest
    such name wins — "가천대학교 글로벌캠퍼스", not one of its buildings."""
    base = _compact(school.name.split("(")[0])
    city = _city(school.road_address or school.lot_address)
    best: tuple[int, float, float] | None = None
    for doc in documents:
        name = _compact(str(doc.get("place_name") or ""))
        category = str(doc.get("category_name") or "")
        address = f"{doc.get('road_address_name') or ''} {doc.get('address_name') or ''}"
        if "대학" not in category or not name.startswith(base) or (city and city not in address):
            continue
        try:
            lat, lng = float(doc["y"]), float(doc["x"])
        except (KeyError, TypeError, ValueError):
            continue
        if best is None or len(name) < best[0]:
            best = (len(name), lat, lng)
    return (best[1], best[2]) if best else None


async def _kakao_locate(client: httpx.AsyncClient, key: str, school: School) -> tuple[float, float] | None:
    """Kakao Local keyword search (official API, docs/34) for a school our own data could not place."""
    resp = await client.get(
        KAKAO_KEYWORD_URL,
        params={"query": f"{school.name.split('(')[0]} {school.label}".strip(), "size": 15},
        headers={"Authorization": f"KakaoAK {key}"},
    )
    resp.raise_for_status()
    return pick_kakao_match(school, resp.json().get("documents") or [])


def assign_ids(
    schools: Iterable[tuple[School, Any]], known: Mapping[tuple[str, str], str] | None = None
) -> dict[int, str]:
    """Stable, readable ids from the English name; a second campus with the same English name gets -2, -3 …
    An id already given in the previous file is kept (it is the place's external id — never reshuffled)."""
    ids: dict[int, str] = {}
    known = known or {}
    rows = list(schools)
    used: set[str] = {known[(s.name, s.road_address)] for s, _ in rows if (s.name, s.road_address) in known}
    for i, (school, _) in enumerate(rows):
        if (kept := known.get((school.name, school.road_address))) is not None:
            ids[i] = kept
            continue
        base = slugify(school.eng_name) or f"school-{i}"
        slug = base
        n = 2
        while slug in used:
            slug = f"{base}-{n}"
            n += 1
        used.add(slug)
        ids[i] = slug
    return ids


async def _address_index(
    db: Database,
) -> tuple[
    dict[tuple[str, str, str], list[tuple[float, float]]],
    dict[tuple[str, str, str], list[tuple[float, float]]],
]:
    by_road: dict[tuple[str, str, str], list[tuple[float, float]]] = defaultdict(list)
    by_lot: dict[tuple[str, str, str], list[tuple[float, float]]] = defaultdict(list)
    async with db.sessionmaker() as session:
        # our own campus inserts are not evidence of where a campus is (a re-run must not feed on itself)
        own = select(PlaceSource.place_id).where(PlaceSource.provider == PROVIDER)
        stmt = select(Place.road_address, Place.address, Place.lat, Place.lng).where(
            Place.status == "approved", Place.id.not_in(own)
        )
        async for road, lot, lat, lng in await session.stream(stmt.execution_options(yield_per=20_000)):
            if (key := road_key(road)) is not None:
                by_road[key].append((lat, lng))
            if (key := lot_key(lot)) is not None:
                by_lot[key].append((lat, lng))
    return by_road, by_lot


def previous_ids(path: Path) -> dict[tuple[str, str], str]:
    """(school, road address) → id from the file a previous build wrote."""
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {(str(e["school"]), str(e["road_address"])): str(e["id"]) for e in data.get("universities", [])}


async def build(
    db: Database,
    raw_path: Path,
    *,
    out: Path = DATA_PATH,
    kakao_key: str | None = None,
    log: Log = print,
) -> dict[str, int]:
    schools = read_schools(raw_path)
    by_road, by_lot = await _address_index(db)
    located: list[tuple[School, tuple[float, float, str]]] = []
    missing: list[str] = []
    async with httpx.AsyncClient(timeout=10.0) as client:
        for school in schools:
            spot = locate(school, by_road, by_lot)
            if spot is None and kakao_key:  # our own data had nothing at that address: ask Kakao Local
                found = await _kakao_locate(client, kakao_key, school)
                if found is not None:
                    spot = (found[0], found[1], "kakao_local")
                await asyncio.sleep(KAKAO_DELAY_S)
            if spot is None:
                missing.append(school.display_name)
            else:
                located.append((school, spot))
    located, close = drop_close_campuses(located)
    ids = assign_ids(located, previous_ids(out))
    entries = [
        {
            "id": ids[i],
            "name": school.display_name,
            "school": school.name,
            "eng_name": school.eng_name,
            "campus": school.label or CAMPUS_LABEL.get(school.campus, school.campus),
            "level": school.level,
            "kind": school.kind,
            "sido": school.sido,
            "sigungu": " ".join(school.road_address.split()[1:2]),
            "road_address": school.road_address,
            "homepage": school.homepage,
            "lat": round(lat, 7),
            "lng": round(lng, 7),
            "coord_source": how,
        }
        for i, (school, (lat, lng, how)) in enumerate(located)
    ]
    payload = {
        "_attribution": ATTRIBUTION,
        "_note": "`ingest-bulk universities --step build` 가 만든다. 손으로 고치면 coord_source: manual",
        "provider": PROVIDER,
        "category": CATEGORY,
        "universities": sorted(entries, key=lambda e: (e["sido"], e["name"])),
        "unlocated": sorted(missing),
        "same_as_another_campus": sorted(close),
    }
    write_json(out, payload)
    log(f"universities: {len(schools)} schools · located {len(entries)} · unlocated {len(missing)} → {out}")
    return {"schools": len(schools), "located": len(entries), "unlocated": len(missing)}


def write_json(out: Path, payload: Mapping[str, Any]) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def load_spec(path: Path = DATA_PATH) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("universities"), list):
        raise UniversityIngestError(f"{path.name}: expected an object with a `universities` list")
    return data


def build_place(entry: Mapping[str, Any], spec: Mapping[str, Any]) -> BulkPlace:
    kind = str(entry.get("kind") or "대학")
    campus = str(entry.get("campus") or "")
    description = " · ".join(
        x for x in (kind, campus if campus != "본교" else "", entry.get("homepage") or "") if x
    )
    return BulkPlace(
        provider=str(spec.get("provider", PROVIDER)),
        external_id=str(entry["id"]),
        name=str(entry["name"]),
        category_code=str(spec.get("category", CATEGORY)),
        lat=float(entry["lat"]),
        lng=float(entry["lng"]),
        sido=entry.get("sido"),
        sigungu=entry.get("sigungu"),
        address=entry.get("road_address"),
        road_address=entry.get("road_address"),
        description=description or None,
        price_per_person=0,
        is_free=True,
        raw={
            "anchor": "university",
            "school": entry.get("school"),
            "campus": campus,
            "kind": kind,
            "homepage": entry.get("homepage"),
            "coord_source": entry.get("coord_source"),
            "attribution": spec.get("_attribution"),
            "sido": entry.get("sido"),
        },
    )


async def load(db: Database, *, path: Path = DATA_PATH, log: Log = print) -> BulkReport:
    spec = load_spec(path)
    async with db.sessionmaker() as session:
        writer = BulkWriter(
            session,
            str(spec.get("provider", PROVIDER)),
            await RegionIndex.load(session, load_json("regions_kr.json")),
        )
        await writer.prepare()
        if not writer.has_category(str(spec.get("category", CATEGORY))):
            raise UniversityIngestError(f"category {CATEGORY} is missing — run `seed-config` first")
        places = []
        for entry in spec["universities"]:
            writer.report.read += 1
            places.append(build_place(entry, spec))
            writer.report.mapped += 1
        await writer.write_all(places)
    log(writer.report.line())
    return writer.report
