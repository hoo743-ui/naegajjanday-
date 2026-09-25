"""Cinemas — multiplexes included — as places (docs/53, data gap A3 in docs/51).

Source: 전국영화상영관표준데이터 (행정안전부 인허가, data.go.kr 15107749; keyless — `ingest-bulk download
--source cinemas` follows the portal's own "전국 파일 다운로드" button at file.localdata.go.kr). One row
per **screen** ("CGV상봉1관", "CGV상봉2관" …), open and closed alike, with EPSG:5174 (Korean 1985 modified
central belt, Bessel) coordinates.

What this module does with it:
  * keeps rows whose 영업상태코드 is 01 (영업/정상), drops 자동차극장 (a car, not a date on foot);
  * folds the screens of one building into one theater: same coordinates (or road address when a row has
    none) and the same name stem;
  * names it the way people say it ("CGV 상봉", "메가박스 송파파크하비오", "롯데시네마 포항");
  * converts the coordinates to WGS84 (`tm5174_to_wgs84`, pure Python — no GIS dependency). A row without
    coordinates is placed at the median of our own places at the same road address (as universities.py
    does) or left out;
  * skips a theater another source already has nearby under a similar name (TourAPI lists some
    independent cinemas as culture.cinema).

The result is written as a delta file (data/bulk/delta/cinemas.json) that `ingest-bulk delta` loads here
and in production — the production disk has neither the raw file nor the place table this build needs.
"""

from __future__ import annotations

import math
import re
import statistics
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import select

from app.core.config import API_ROOT
from app.infra.db.models import Category, Place
from app.infra.db.session import Database
from app.infra.ingestion import dedupe
from app.infra.ingestion.bulk.common import BulkPlace, in_korea, iter_csv, load_json, to_float
from app.infra.ingestion.bulk.price_prior import PricePrior
from app.infra.ingestion.bulk.universities import _address_index, lot_key, road_key

Log = Callable[[str], None]
PROVIDER = "std_cinema"
CATEGORY = "activity.cinema"
RAW_FILENAME = "std_cinemas.csv"
DELTA_PATH = API_ROOT / "data" / "bulk" / "delta" / "cinemas.json"
ATTRIBUTION = (
    "행정안전부 · 전국영화상영관표준데이터(공공데이터포털 15107749, 이용허락범위 제한 없음). "
    "상영관(스크린) 행을 극장 하나로 묶고, 좌표는 EPSG:5174 → WGS84 변환."
)
OPEN_CODE = "01"
DUPLICATE_RADIUS_M = 300.0
DUPLICATE_NAME_MIN = 0.75
DUPLICATE_CATEGORIES = ("culture.cinema",)  # TourAPI files independent cinemas here
MERGE_RADIUS_M = 300.0
MAX_SPREAD_M = 400.0  # places at "one" address spread wider than a building → not trusted as its location

# --- EPSG:5174 → WGS84 ----------------------------------------------------------------------------
# Korean 1985 / Modified Central Belt: TM on Bessel 1841, lat0 38°, lon0 127°00'10.405", k 1,
# false easting 200 000, false northing 500 000; datum shift = the EPSG towgs84 7 parameters.
_BESSEL_A = 6377397.155
_BESSEL_F = 1 / 299.1528128
_WGS_A = 6378137.0
_WGS_F = 1 / 298.257223563
_LAT0 = math.radians(38.0)
_LON0 = math.radians(127.0 + 10.405 / 3600)
_X0, _Y0 = 200_000.0, 500_000.0
_TOWGS84 = (-115.80, 474.99, 674.11, 1.16, -2.31, -1.63, 6.43)  # m, m, m, ″, ″, ″, ppm


def _meridian_arc(phi: float, a: float, e2: float) -> float:
    e4, e6 = e2 * e2, e2 * e2 * e2
    return a * (
        (1 - e2 / 4 - 3 * e4 / 64 - 5 * e6 / 256) * phi
        - (3 * e2 / 8 + 3 * e4 / 32 + 45 * e6 / 1024) * math.sin(2 * phi)
        + (15 * e4 / 256 + 45 * e6 / 1024) * math.sin(4 * phi)
        - (35 * e6 / 3072) * math.sin(6 * phi)
    )


def _tm_inverse(x: float, y: float) -> tuple[float, float]:
    """(lat, lng) in radians on Bessel from TM easting x / northing y (Snyder 8-7 … 8-25)."""
    a, f = _BESSEL_A, _BESSEL_F
    e2 = 2 * f - f * f
    ep2 = e2 / (1 - e2)
    m = _meridian_arc(_LAT0, a, e2) + (y - _Y0)
    mu = m / (a * (1 - e2 / 4 - 3 * e2 * e2 / 64 - 5 * e2**3 / 256))
    e1 = (1 - math.sqrt(1 - e2)) / (1 + math.sqrt(1 - e2))
    phi1 = (
        mu
        + (3 * e1 / 2 - 27 * e1**3 / 32) * math.sin(2 * mu)
        + (21 * e1**2 / 16 - 55 * e1**4 / 32) * math.sin(4 * mu)
        + (151 * e1**3 / 96) * math.sin(6 * mu)
        + (1097 * e1**4 / 512) * math.sin(8 * mu)
    )
    sin1, cos1, tan1 = math.sin(phi1), math.cos(phi1), math.tan(phi1)
    c1 = ep2 * cos1 * cos1
    t1 = tan1 * tan1
    n1 = a / math.sqrt(1 - e2 * sin1 * sin1)
    r1 = a * (1 - e2) / (1 - e2 * sin1 * sin1) ** 1.5
    d = (x - _X0) / n1
    lat = phi1 - (n1 * tan1 / r1) * (
        d * d / 2
        - (5 + 3 * t1 + 10 * c1 - 4 * c1 * c1 - 9 * ep2) * d**4 / 24
        + (61 + 90 * t1 + 298 * c1 + 45 * t1 * t1 - 252 * ep2 - 3 * c1 * c1) * d**6 / 720
    )
    lng = (
        _LON0
        + (
            d
            - (1 + 2 * t1 + c1) * d**3 / 6
            + (5 - 2 * c1 + 28 * t1 - 3 * c1 * c1 + 8 * ep2 + 24 * t1 * t1) * d**5 / 120
        )
        / cos1
    )
    return lat, lng


def _to_ecef(lat: float, lng: float, a: float, f: float) -> tuple[float, float, float]:
    e2 = 2 * f - f * f
    n = a / math.sqrt(1 - e2 * math.sin(lat) ** 2)
    return (
        n * math.cos(lat) * math.cos(lng),
        n * math.cos(lat) * math.sin(lng),
        n * (1 - e2) * math.sin(lat),
    )


def _from_ecef(x: float, y: float, z: float, a: float, f: float) -> tuple[float, float]:
    e2 = 2 * f - f * f
    lng = math.atan2(y, x)
    p = math.hypot(x, y)
    lat = math.atan2(z, p * (1 - e2))
    for _ in range(6):
        n = a / math.sqrt(1 - e2 * math.sin(lat) ** 2)
        lat = math.atan2(z + e2 * n * math.sin(lat), p)
    return lat, lng


def tm5174_to_wgs84(x: float, y: float) -> tuple[float, float]:
    """(lat, lng) in degrees, WGS84, from EPSG:5174 easting / northing (position-vector 7-parameter shift)."""
    lat, lng = _tm_inverse(x, y)
    bx, by, bz = _to_ecef(lat, lng, _BESSEL_A, _BESSEL_F)
    tx, ty, tz, rx, ry, rz, ds = _TOWGS84
    rx, ry, rz = (math.radians(v / 3600) for v in (rx, ry, rz))
    s = 1 + ds * 1e-6
    wx = tx + s * (bx - rz * by + ry * bz)
    wy = ty + s * (rz * bx + by - rx * bz)
    wz = tz + s * (-ry * bx + rx * by + bz)
    wlat, wlng = _from_ecef(wx, wy, wz, _WGS_A, _WGS_F)
    return math.degrees(wlat), math.degrees(wlng)


# --- names ------------------------------------------------------------------------------------------
_CORP = re.compile(r"\(주\)|㈜|주식회사|\(유\)|유한회사")
_BRANDS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"(?:씨제이|CJ)?\s*(?:씨지브이|시\.?지\.?브이|CGV)", re.IGNORECASE), "CGV"),
    (re.compile(r"(?:롯데컬처웍스\s*)?롯데\s*시네마|롯데컬처웍스"), "롯데시네마"),
    (re.compile(r"메가박스\s*(?:중앙)?"), "메가박스"),
    (re.compile(r"씨네큐(?!브)|씨네\s*Q|CINE\s*Q", re.IGNORECASE), "씨네Q"),  # 씨네큐브 is another cinema
)
BRANDS = ("CGV", "롯데시네마", "메가박스", "씨네Q")
# words that name a screen, not a theater ("컴포트3관", "키즈A관", "샤롯데관") — Korean words are listed so
# that "영화관" / "시민회관" / "작은영화관" are never taken for a screen
_SCREEN_WORDS = (
    "컴포트|키즈[A-Z]?|샤롯데|스위트|프레시|아트|부티크|르\\s*리클라이너|리클라이너|프라이빗|골드클래스"
    "|템퍼시네마|수퍼플렉스|슈퍼플렉스|광음시네마|씨네커플|스윗박스|더부티크|돌비시네마|스트레스리스\\s*시네마"
)
_SCREEN_TAIL = re.compile(
    rf"[\s(\[<]*(?:제(?=\d))?(?:(?:{_SCREEN_WORDS}|[A-Za-z0-9|&.+]+호?)\s*)+(?:상영관|관|룸)\s*[A-Z]?"
    r"(?:\s*\([^)]*\))?[\s)\]>]*$"
)
_HALL_TAIL = re.compile(r"\s*[소대]?상영관\s*[A-Z0-9ⅠⅡⅢⅣⅤ]?$")  # "코엑스 소상영관 A"
_LATIN_TAIL = re.compile(r"(?:\s+[A-Z][A-Z0-9+]{2,})+$")  # "CGV 신세계경기 DOLBY ATMOS"
# "[CGV아트하우스]", "<<1,2,5관>>", "(THE BOUTIQUE)" — never part of the theater's name
_BRACKETS = re.compile(r"\[[^\]]*\]|<<[^>]*>>|<[^>]*>|\([A-Za-z0-9\s+&.]*\)")
# a trailing screen count is not part of the name either: "CGV인천14" is CGV 인천
_TRAILING_JUNK = " 0123456789(-_·,[<|"


def split_brand(raw_name: str) -> tuple[str | None, str]:
    """("CGV", "상봉1관") from "씨지브이(주) 상봉1관"; (None, name) for an independent cinema. The brand may
    sit mid-name ("(주)써니트 롯데시네마 수유", "창동 메가박스 5관"): the branch is then what follows it,
    or what precedes it when only a screen follows."""
    name = " ".join(_CORP.sub(" ", raw_name).split())
    for pattern, brand in _BRANDS:
        m = pattern.search(name)
        if m:
            after = name[m.end() :].strip(" -_")
            before = name[: m.start()].strip(" -_")
            if m.start() == 0 or _stem(after):
                return brand, after
            return brand, before
    return None, name


def _stem(name: str) -> str:
    """One screen's name without its screen part: "상봉1관" → "상봉", "하비오점(9관)" → "하비오점".
    Empty when the name is nothing but a screen ("3관", "제1관")."""
    s = _BRACKETS.sub(" ", name).strip()
    prev = None
    while prev != s:
        prev = s
        s = _HALL_TAIL.sub("", _SCREEN_TAIL.sub("", s)).rstrip(_TRAILING_JUNK).strip()
    return s


def _compact(text: str) -> str:
    return "".join(text.split())


def _tidy(name: str) -> str:
    """Stray punctuation left by a cut screen name: "도계작은영화관(가람영화관" → "도계작은영화관",
    "포천)클라우드시네마" → "클라우드시네마", "김해장유 제1관~" → "김해장유"."""
    name = re.sub(r"\s+with$", "", name.replace("~", " "), flags=re.IGNORECASE)  # "보은영화관 with 씨네큐"
    name = re.sub(r"\([^)]*관\)$", "", name)  # "작은별영화관(고추관)" — a screen in brackets
    name = re.sub(r"\s*(?:더\s*부티크)?\s*\d+호$", "", name)  # "센트럴 더부티크 101호" — a suite
    if name.count("(") > name.count(")"):
        name = name[: name.rfind("(")]
    if name.count(")") > name.count("("):
        name = name[name.find(")") + 1 :]
    return " ".join(_stem(name).split()) if name.strip() else ""


def branch_name(brand: str | None, stem: str) -> str:
    stem = _tidy(stem)
    if brand is None:
        return stem
    # "구의이스트폴지점" → "구의이스트폴"; "(오산중앙)" → "오산중앙"
    base = re.sub(r"(?:지점|(?<!백화)점)$", "", _LATIN_TAIL.sub("", stem)).strip(" ()")
    base = base.replace("(", " ").replace(")", " ").strip()
    if brand == "롯데시네마" and len(base) > 2:
        base = re.sub(r"(?<!영화)관$", "", base)  # "건대입구관" → "건대입구" (how the chain itself writes it)
    return " ".join(f"{brand} {base}".split())


def looks_like_a_cinema(name: str, brand: str | None, words: Sequence[str]) -> bool:
    """A chain is a cinema by its brand; an independent one must say so in its name ("…극장", "…시네마",
    "…영화관"). What is left is a hall or an office that registered a screen ("하늘관", "케이엠티브이")."""
    return brand is not None or any(w.upper() in name.upper() for w in words)


def cluster_screens(raw_names: Sequence[str]) -> list[tuple[str | None, str, list[int]]]:
    """Screens at one spot → theaters: [(brand, stem, member indexes)]. Screens whose name is only a screen
    ("롯데시네마 3관", "1관") join the biggest named theater there; a stem that is the start of another
    ("평택" · "평택소사") is the same theater."""
    parsed = [split_brand(n) for n in raw_names]
    stems = [(_stem(rest), brand) for brand, rest in parsed]
    groups: dict[str, list[int]] = defaultdict(list)
    generic: list[int] = []
    for i, (stem, _) in enumerate(stems):
        key = _compact(stem)
        if len(key) < 2:
            generic.append(i)
        else:
            groups[key].append(i)
    keys = sorted(groups, key=len)
    for i, short in enumerate(keys):  # fold a prefix into the longer stem that has more screens
        longer = [k for k in keys[i + 1 :] if k.startswith(short) and k in groups]
        if longer and short in groups:
            target = max(longer, key=lambda k: len(groups[k]))
            groups[target].extend(groups.pop(short))
    if generic:
        if groups:
            groups[max(groups, key=lambda k: len(groups[k]))].extend(generic)
        else:
            groups[""] = generic
    out: list[tuple[str | None, str, list[int]]] = []
    for members in groups.values():
        named = Counter(stems[i][0] for i in members if len(_compact(stems[i][0])) >= 2)
        stem = min(named, key=lambda s: (-named[s], len(s))) if named else ""
        brand = next((stems[i][1] for i in members if stems[i][1]), None)
        out.append((brand, stem, sorted(members)))
    return out


# --- rows → theaters -------------------------------------------------------------------------------
@dataclass(slots=True)
class Theater:
    external_id: str
    name: str
    brand: str | None
    raw_names: list[str]
    road_address: str
    lot_address: str
    phone: str
    xy: tuple[float, float] | None
    licensed_on: str
    screens: int = 0


def _road_base(address: str) -> str:
    return address.split(",")[0].split("(")[0].strip()


def _dong(address: str) -> str:
    """ "… 천호옛길 85 (성내동)" → "성내동"."""
    m = re.search(r"\(([^,)]+?(?:동|가|읍|면|리))[,)]", address)
    return m.group(1) if m else ""


def _where(row: Mapping[str, str]) -> str:
    x, y = to_float(row.get("좌표정보(X)")), to_float(row.get("좌표정보(Y)"))
    if x and y:
        return f"{round(x)}:{round(y)}"
    return _road_base(row.get("도로명주소") or row.get("지번주소") or "")


def read_theaters(rows: Iterable[Mapping[str, str]], rules: Mapping[str, Any] | None = None) -> list[Theater]:
    rules = rules if rules is not None else load_json("bulk_rules.json").get("cinemas", {})
    excluded_kinds = set(rules.get("exclude_kinds") or ())
    excluded_words = tuple(rules.get("exclude_name_keywords") or ())
    excluded_names = set(rules.get("exclude_names") or ())
    cinema_words = tuple(rules.get("independent_name_words") or ("극장", "시네마", "씨네", "영화"))
    spots: dict[str, list[Mapping[str, str]]] = defaultdict(list)
    for row in rows:
        name = (row.get("사업장명") or "").strip()
        if (row.get("영업상태코드") or "").strip() != OPEN_CODE or not name:
            continue
        if (row.get("공연장형태구분명") or "").strip() in excluded_kinds:
            continue
        if any(w in name for w in excluded_words):
            continue
        spots[_where(row)].append(row)
    theaters: list[Theater] = []
    for rows_here in spots.values():
        rows_here = sorted(rows_here, key=lambda r: r.get("관리번호") or "")
        for brand, stem, members in cluster_screens([str(r.get("사업장명") or "") for r in rows_here]):
            located = [i for i in members if to_float(rows_here[i].get("좌표정보(X)"))]
            first = rows_here[(located or members)[0]]
            road = str(first.get("도로명주소") or "").strip()
            if not stem:  # nothing but screen names: a chain is known by its brand and neighbourhood
                if brand is None or not _dong(road):
                    continue
                stem = _dong(road)
            name = branch_name(brand, stem)
            if len(_compact(name)) < 2 or not looks_like_a_cinema(name, brand, cinema_words):
                continue
            if name in excluded_names:
                continue
            x, y = to_float(first.get("좌표정보(X)")), to_float(first.get("좌표정보(Y)"))
            theaters.append(
                Theater(
                    external_id=f"{first.get('개방자치단체코드') or ''}-{first.get('관리번호') or ''}",
                    name=name,
                    brand=brand,
                    raw_names=[str(rows_here[i].get("사업장명") or "") for i in members],
                    road_address=road,
                    lot_address=str(first.get("지번주소") or "").strip(),
                    phone=str(first.get("전화번호") or "").strip(),
                    xy=(x, y) if x and y else None,
                    licensed_on=str(first.get("인허가일자") or ""),
                    screens=len(members),
                )
            )
    return merge_same_name(theaters)


def merge_same_name(theaters: Sequence[Theater]) -> list[Theater]:
    """One theater registered in two buildings ("메가박스 원주혁신" 601호 · 608호, a screen filed without
    coordinates) is still one theater: the same name within MERGE_RADIUS_M (or at the same road address)
    folds into the one with more screens."""
    out: list[Theater] = []
    for t in sorted(theaters, key=lambda t: (-t.screens, t.xy is None, t.external_id)):
        home = next((o for o in out if o.name == t.name and _same_site(o, t)), None)
        if home is None:
            out.append(t)
        else:
            home.screens += t.screens
            home.raw_names.extend(t.raw_names)
    return out


def _same_site(a: Theater, b: Theater) -> bool:
    if a.xy is not None and b.xy is not None:
        return math.dist(a.xy, b.xy) <= MERGE_RADIUS_M  # EPSG:5174 is in metres
    return bool(a.road_address) and _road_base(a.road_address) == _road_base(b.road_address)


def _sido_sigungu(address: str) -> tuple[str | None, str | None]:
    parts = address.split()
    return (parts[0] if parts else None), (parts[1] if len(parts) > 1 else None)


def short_address(address: str) -> str:
    """ "서울특별시 마포구 양화로 176, 동교동 스타피카소 8층 (동교동)" → the road address up to the number."""
    return _road_base(address)


def to_place(theater: Theater, lat: float, lng: float, prior: PricePrior, coord_source: str) -> BulkPlace:
    name = theater.name
    address = theater.road_address or theater.lot_address
    sido, sigungu = _sido_sigungu(address)
    price = prior.estimate(CATEGORY, sido, None, name)
    screens = f"상영관 {theater.screens}개" if theater.screens > 1 else "상영관 1개"
    return BulkPlace(
        provider=PROVIDER,
        external_id=theater.external_id,
        name=name,
        category_code=CATEGORY,
        lat=round(lat, 7),
        lng=round(lng, 7),
        sido=sido,
        sigungu=sigungu,
        address=theater.lot_address or None,
        road_address=theater.road_address or None,
        phone=theater.phone or None,
        description=f"영화관 · {screens}",
        price_per_person=price,
        price_is_estimated=price is not None,
        raw={
            "brand": theater.brand,
            "screens": theater.screens,
            "licensed_on": theater.licensed_on,
            "coord_source": coord_source,
            "attribution": ATTRIBUTION,
        },
    )


# --- build: raw CSV + our place table → delta file ------------------------------------------------
async def _existing(db: Database, codes: Sequence[str]) -> list[dedupe.ExistingPlace]:
    """Places another source already files as a screen venue. Only those: against every sight the loose
    name test matched "코엑스" with 코엑스 아쿠아리움 and "명보" with 명보게임장."""
    async with db.sessionmaker() as session:
        stmt = (
            select(Place.id, Place.name, Place.lat, Place.lng, Place.phone)
            .join(Category, Category.id == Place.category_id)
            .where(Category.code.in_(codes), Place.status == "approved")
        )
        return [dedupe.ExistingPlace(*row) for row in (await session.execute(stmt)).all()]


def find_duplicate(place: BulkPlace, existing: Iterable[dedupe.ExistingPlace]) -> dedupe.ExistingPlace | None:
    for e in existing:
        if dedupe.distance_m(place.lat, place.lng, e.lat, e.lng) > DUPLICATE_RADIUS_M:
            continue
        if dedupe.name_similarity(place.name, e.name) >= DUPLICATE_NAME_MIN:
            return e
    return None


async def build(db: Database, raw_path: Path, *, out: Path = DELTA_PATH, log: Log = print) -> dict[str, int]:
    from app.infra.ingestion.bulk.delta import write_delta

    theaters = read_theaters(iter_csv(raw_path))
    prior = PricePrior.from_data(load_json("price_prior.json"), load_json("regions_kr.json"))
    by_road, by_lot = await _address_index(db)
    existing = await _existing(db, DUPLICATE_CATEGORIES)
    places: list[BulkPlace] = []
    counts: dict[str, int] = defaultdict(int)
    offsets: list[float] = []
    for t in theaters:
        counts["theaters"] += 1
        spot = locate_theater(t, by_road, by_lot)
        if t.xy is not None:
            lat, lng = tm5174_to_wgs84(*t.xy)
            how = "epsg5174"
            if spot is not None:
                offsets.append(dedupe.distance_m(lat, lng, spot[0], spot[1]))
        elif spot is not None:
            lat, lng, how = spot
        else:
            counts["unlocated"] += 1
            continue
        if not in_korea(lat, lng):
            counts["bad_coord"] += 1
            continue
        place = to_place(t, lat, lng, prior, how)
        dup = find_duplicate(place, existing)
        if dup is not None:
            counts["duplicate_of_other_source"] += 1
            log(f"  duplicate: {place.name} ≈ {dup.name} (place {dup.id})")
            continue
        places.append(place)
        counts[how] += 1
    if offsets:
        log(
            f"  converted vs same-address places: median {statistics.median(offsets):.0f} m, "
            f"90th {sorted(offsets)[int(len(offsets) * 0.9)]:.0f} m over {len(offsets)} theaters"
        )
    write_delta(out, PROVIDER, places, note=ATTRIBUTION, complete=True)
    counts["written"] = len(places)
    log(f"cinemas: {dict(counts)} → {out}")
    return dict(counts)


def locate_theater(
    t: Theater,
    by_road: Mapping[tuple[str, str, str], list[tuple[float, float]]],
    by_lot: Mapping[tuple[str, str, str], list[tuple[float, float]]],
) -> tuple[float, float, str] | None:
    """The median of our own places at the theater's road (or lot) address — universities.py's method.
    A cinema is one building, so the places there must sit within MAX_SPREAD_M of each other."""
    for how, key, index in (
        ("road_address", road_key(short_address(t.road_address)), by_road),
        ("lot_address", lot_key(t.lot_address), by_lot),
    ):
        points = index.get(key) if key else None
        if not points:
            continue
        lats, lngs = [p[0] for p in points], [p[1] for p in points]
        if max((max(lats) - min(lats)) * 111_000, (max(lngs) - min(lngs)) * 88_000) > MAX_SPREAD_M:
            continue
        return statistics.median(lats), statistics.median(lngs), how
    return None
