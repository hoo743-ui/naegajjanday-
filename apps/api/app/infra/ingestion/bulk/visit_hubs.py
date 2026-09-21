"""Where people really go: the tourism board's "hub destinations" per district (`data/bulk/visit_hubs.json`).

The list is measured, not scraped: navigation trips that actually reached the destination, ranked 1-100
for every district, under an unrestricted licence (docs/20). It fills the one signal the public data
never had — popularity — and adds well-known places we were missing.

It is car navigation, so a lane of small shops never shows up. The rank therefore only ever lifts a
place; being absent says nothing and costs nothing.

Run from apps/api (both steps are re-runnable):
    uv run python -m app.infra.ingestion.bulk.visit_hubs fetch   # raw JSON → <data dir>/raw/visit_hubs/
    uv run python -m app.infra.ingestion.bulk.visit_hubs load    # match / insert, popularity, the tag
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
import time
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import delete, insert, select, update
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.infra.db.models import Category, Place, PlaceSource, PlaceStats, PlaceTag, Tag
from app.infra.db.session import Database
from app.infra.ingestion.bulk.common import BulkPlace, BulkReport, chunked, load_json
from app.infra.ingestion.bulk.download import default_raw_dir
from app.infra.ingestion.bulk.price_prior import PricePrior
from app.infra.ingestion.bulk.regions import RegionIndex
from app.infra.ingestion.bulk.venues import similarity
from app.infra.ingestion.bulk.writer import BulkWriter
from app.infra.ingestion.dedupe import ExistingPlace, distance_m

Log = Callable[[str], None]
SPEC_FILE = "visit_hubs.json"
DEG_PER_M = 1 / 111_000  # bbox pre-filter only; the real distance check follows
ID_CHUNK = 500
LOCK_RETRIES = 8
LOCK_WAIT_S = 5.0
NETWORK_TRIES = 4
NETWORK_WAIT_S = 3.0
_SPLIT = re.compile(r"[/()\[\]]+")
_BRACKETED = re.compile(r"[(\[]([^)\]]+)[)\]]")


class VisitHubError(RuntimeError):
    pass


# --- fetch --------------------------------------------------------------------------------------


@dataclass(slots=True)
class FetchReport:
    month: str = ""
    districts: int = 0
    fetched: int = 0
    cached: int = 0
    empty: int = 0
    calls: int = 0
    stopped_at_cap: bool = False

    def line(self) -> str:
        cap = " · stopped at the daily cap, run again tomorrow" if self.stopped_at_cap else ""
        return (
            f"month={self.month} districts={self.districts} fetched={self.fetched} cached={self.cached} "
            f"empty={self.empty} calls={self.calls}{cap}"
        )


class _Api:
    """data.go.kr gateway. The key goes in the query string (their contract) and never into a log."""

    def __init__(self, spec: Mapping[str, Any], cap: int) -> None:
        self._spec, self._cap, self.calls = spec, cap, 0
        self._client = httpx.Client(timeout=40.0, follow_redirects=True)

    def close(self) -> None:
        self._client.close()

    @property
    def spent(self) -> bool:
        return self.calls >= self._cap

    def _send(self, path: str, query: Mapping[str, str]) -> httpx.Response:
        """The gateway stalls now and then: a slow answer is tried again, anything else is not."""
        for attempt in range(1, NETWORK_TRIES + 1):
            try:
                return self._client.get(f"{self._spec['base_url']}/{path}", params=dict(query))
            except httpx.TransportError as exc:
                if attempt == NETWORK_TRIES:
                    # never let the exception text out: it carries the URL, and the URL carries the key
                    raise VisitHubError(f"{path}: {type(exc).__name__} after {attempt} tries") from None
                time.sleep(NETWORK_WAIT_S * attempt)
        raise AssertionError("unreachable")

    def get(self, path: str, key: str, **params: str) -> list[dict[str, Any]]:
        self.calls += 1
        query = {
            "serviceKey": key,
            "MobileOS": "ETC",
            "MobileApp": str(self._spec["app_name"]),
            "_type": "json",
            "numOfRows": str(self._spec["rows"]),
            "pageNo": "1",
            **params,
        }
        resp = self._send(path, query)
        if resp.status_code != 200:
            raise VisitHubError(f"{path}: HTTP {resp.status_code} (is the key approved for this service?)")
        try:
            body = resp.json()["response"]
        except (ValueError, KeyError) as exc:  # the gateway answers errors as XML with status 200
            raise VisitHubError(f"{path}: not a JSON answer: {resp.text[:120]!r}") from exc
        if body["header"].get("resultCode") != "0000":
            raise VisitHubError(f"{path}: {body['header']}")
        items = body.get("body", {}).get("items") or {}
        rows = items.get("item", []) if isinstance(items, Mapping) else []
        return list(rows) if isinstance(rows, list) else [rows]


def _months(today: date, back: int) -> list[str]:
    """Last month first: the current month is never published yet."""
    out: list[str] = []
    year, month = today.year, today.month
    for _ in range(back):
        month -= 1
        if month == 0:
            year, month = year - 1, 12
        out.append(f"{year}{month:02d}")
    return out


def _keys(settings: Settings) -> tuple[str, str]:
    hub, codes = settings.data_go_kr_service_key, settings.tourapi_service_key
    if not hub:
        raise VisitHubError("DATA_GO_KR_SERVICE_KEY is empty (the key of the account approved for 15128559)")
    return hub, codes or hub


def fetch(settings: Settings, *, raw_dir: Path | None = None, log: Log = print) -> FetchReport:
    spec = load_json(SPEC_FILE)
    hub_key, codes_key = _keys(settings)
    root = (raw_dir or default_raw_dir()) / "visit_hubs"
    root.mkdir(parents=True, exist_ok=True)
    api = _Api(spec, int(spec["daily_call_cap"]))
    report = FetchReport()
    try:
        codes_file = root / "codes.json"
        if codes_file.exists():
            districts = json.loads(codes_file.read_text(encoding="utf-8"))
        else:
            districts = []
            for area in api.get(str(spec["codes_path"]), codes_key, lDongListYn="N"):
                for row in api.get(str(spec["codes_path"]), codes_key, lDongRegnCd=str(area["code"])):
                    districts.append(
                        {
                            "area": str(area["code"]),
                            "area_name": area["name"],
                            "district": f"{area['code']}{row['code']}",
                            "name": row["name"],
                        }
                    )
            codes_file.write_text(json.dumps(districts, ensure_ascii=False, indent=1), encoding="utf-8")
        report.districts = len(districts)
        if not districts:
            raise VisitHubError("no district codes came back")

        probe = districts[0]
        for month in _months(date.today(), int(spec["months_back"])):
            if api.get(
                str(spec["hub_path"]), hub_key, baseYm=month, areaCd=probe["area"], signguCd=probe["district"]
            ):
                report.month = month
                break
        if not report.month:
            raise VisitHubError("no month with data in the look-back window")
        log(f"month {report.month} · {len(districts)} districts")

        folder = root / report.month
        folder.mkdir(exist_ok=True)
        for d in districts:
            target = folder / f"{d['district']}.json"
            if target.exists():
                report.cached += 1
                continue
            if api.spent:
                report.stopped_at_cap = True
                break
            rows = api.get(
                str(spec["hub_path"]), hub_key, baseYm=report.month, areaCd=d["area"], signguCd=d["district"]
            )
            target.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
            report.fetched += 1
            report.empty += 0 if rows else 1
            if report.fetched % 25 == 0:
                log(f"  {report.fetched} fetched … {d['area_name']} {d['name']}")
    finally:
        report.calls = api.calls
        api.close()
    return report


# --- load ---------------------------------------------------------------------------------------


@dataclass(slots=True)
class Hub:
    code: str
    name: str
    lat: float
    lng: float
    rank: int
    month: str
    sido: str
    sigungu: str
    large: str
    middle: str
    names: tuple[str, ...] = field(default_factory=tuple)


def name_parts(name: str) -> tuple[str, ...]:
    """What the destination may be called in our data. The list writes "<place>/<branch>" and
    "<scene>/(<better known name>)": the whole name, the part before the slash, and whatever stands in
    brackets. A bare branch ("<district> branch") is never a name of its own — it matched other shops."""
    whole = " ".join(_SPLIT.split(name)).strip()
    head = name.split("/", 1)[0].strip()
    aliases = [m.strip() for m in _BRACKETED.findall(name)]
    return tuple(dict.fromkeys(n for n in (whole, head, *aliases) if len(n) >= 2))


def read_hubs(folder: Path) -> list[Hub]:
    """One entry per destination: a place listed by two districts keeps its better rank."""
    best: dict[str, Hub] = {}
    for file in sorted(folder.glob("*.json")):
        for row in json.loads(file.read_text(encoding="utf-8")):
            try:
                hub = Hub(
                    code=str(row["hubTatsCd"]),
                    name=str(row["hubTatsNm"]).strip(),
                    lat=float(row["mapY"]),
                    lng=float(row["mapX"]),
                    rank=int(row["hubRank"]),
                    month=str(row["baseYm"]),
                    sido=str(row.get("areaNm") or ""),
                    sigungu=str(row.get("signguNm") or ""),
                    large=str(row.get("hubCtgryLclsNm") or ""),
                    middle=str(row.get("hubCtgryMclsNm") or ""),
                )
            except (KeyError, TypeError, ValueError):
                continue
            if not hub.name or not (33 <= hub.lat <= 39 and 124 <= hub.lng <= 132):
                continue
            hub.names = name_parts(hub.name)
            if hub.code not in best or hub.rank < best[hub.code].rank:
                best[hub.code] = hub
    return list(best.values())


def popularity_of(rank: int, ranks: int) -> float:
    return round(max(0.0, 1.0 - (rank - 1) / ranks), 4)


def pick_existing(
    hub: Hub, candidates: Iterable[ExistingPlace], *, radius_m: float, min_similarity: float
) -> ExistingPlace | None:
    best: tuple[float, float, ExistingPlace] | None = None
    for cand in candidates:
        dist = distance_m(hub.lat, hub.lng, cand.lat, cand.lng)
        if dist > radius_m:
            continue
        score = max((similarity(name, cand.name) for name in hub.names or (hub.name,)), default=0.0)
        if score >= min_similarity and (best is None or (score, -dist) > (best[0], -best[1])):
            best = (score, dist, cand)
    return best[2] if best else None


async def _nearby(
    session: AsyncSession, hub: Hub, radius_m: float, roles: Sequence[str], provider: str
) -> list[ExistingPlace]:
    d_lat = radius_m * DEG_PER_M
    d_lng = d_lat * 1.4
    own = select(PlaceSource.place_id).where(
        PlaceSource.provider == provider, PlaceSource.match_confidence >= 1.0
    )
    rows = await session.execute(
        select(Place.id, Place.name, Place.lat, Place.lng, Place.phone)
        .join(Category, Category.id == Place.category_id)
        .where(
            Place.lat.between(hub.lat - d_lat, hub.lat + d_lat),
            Place.lng.between(hub.lng - d_lng, hub.lng + d_lng),
            Place.status == "approved",
            Category.course_role.in_(roles),
            Place.id.not_in(own),
        )
    )
    return [ExistingPlace(pid, name, lat, lng, phone) for pid, name, lat, lng, phone in rows]


def _bulk_place(hub: Hub, spec: Mapping[str, Any], category: str, prior: PricePrior | None) -> BulkPlace:
    price = prior.estimate(category, hub.sido or None, None, hub.name) if prior else None
    return BulkPlace(
        provider=str(spec["provider"]),
        external_id=hub.code,
        name=hub.name,
        category_code=category,
        lat=hub.lat,
        lng=hub.lng,
        sido=hub.sido or None,
        sigungu=hub.sigungu or None,
        price_per_person=price,
        price_is_estimated=price is not None,
        is_free=price == 0,
        raw={"rank": hub.rank, "month": hub.month, "class": [hub.large, hub.middle], "district": hub.sigungu},
    )


async def load(
    db: Database, *, raw_dir: Path | None = None, month: str | None = None, log: Log = print
) -> BulkReport:
    spec = load_json(SPEC_FILE)
    root = (raw_dir or default_raw_dir()) / "visit_hubs"
    months = sorted(p.name for p in root.iterdir() if p.is_dir()) if root.exists() else []
    if not months:
        raise VisitHubError(f"nothing fetched yet under {root} — run `fetch` first")
    folder = root / (month or months[-1])
    hubs = read_hubs(folder)
    log(f"{folder.name}: {len(hubs)} destinations")

    provider = str(spec["provider"])
    merge = spec["merge"]
    radius_m, min_similarity = float(merge["radius_m"]), float(merge["min_similarity"])
    roles = [str(r) for r in merge["roles"]]
    by_class: Mapping[str, str] = spec["category_by_class"]
    regions_spec = load_json("regions_kr.json")
    prior = PricePrior.from_data(load_json("price_prior.json"), regions_spec)

    async with db.sessionmaker() as session:
        writer = BulkWriter(session, provider, await RegionIndex.load(session, regions_spec))
        await writer.prepare()
        places: list[BulkPlace] = []
        for hub in hubs:
            writer.report.read += 1
            category = by_class.get(hub.middle)
            match = pick_existing(
                hub,
                await _nearby(session, hub, radius_m, roles, provider),
                radius_m=radius_m,
                min_similarity=min_similarity,
            )
            if match is None and (category is None or not writer.has_category(category)):
                writer.report.skip("class_not_mapped")  # lodging / food we do not already have
                continue
            place = _bulk_place(hub, spec, category or "attraction", prior)
            if match is not None:
                place.merge_into_place_id = match.id
            places.append(place)
        report = await writer.write_all(places)
        await _apply_popularity(session, spec, folder.name, log)
    return report


async def _apply_popularity(session: AsyncSession, spec: Mapping[str, Any], month: str, log: Log) -> None:
    """popularity (every ranked place) and the tag (the top of each district). Both are rebuilt from the
    sources on every run, so a place that fell off the list loses them."""
    provider, ranks = str(spec["provider"]), int(spec["popularity"]["ranks"])
    tag_name, top_rank = str(spec["tag"]["name"]), int(spec["tag"]["top_rank"])
    rows = await session.execute(
        select(PlaceSource.place_id, PlaceSource.raw).where(
            PlaceSource.provider == provider, PlaceSource.place_id.is_not(None)
        )
    )
    best: dict[int, int] = {}
    for place_id, raw in rows:
        if not isinstance(raw, Mapping) or raw.get("month") != month:
            continue
        rank = int(raw.get("rank") or ranks)
        best[place_id] = min(rank, best.get(place_id, rank))

    await session.execute(update(PlaceStats).where(PlaceStats.popularity > 0).values(popularity=0.0))
    known = set()
    for chunk in chunked(list(best), ID_CHUNK):
        known |= set(
            (await session.scalars(select(PlaceStats.place_id).where(PlaceStats.place_id.in_(chunk)))).all()
        )
    missing = [{"place_id": pid, "aspect_scores": {}} for pid in best if pid not in known]
    if missing:
        await session.execute(insert(PlaceStats), missing)
    updates = [{"place_id": pid, "popularity": popularity_of(rank, ranks)} for pid, rank in best.items()]
    for batch in chunked(updates, ID_CHUNK):
        await session.execute(update(PlaceStats), list(batch))

    tag_id = await session.scalar(select(Tag.id).where(Tag.name == tag_name))
    if tag_id is None:
        tag = Tag(name=tag_name, group="feature", is_selectable=False)
        session.add(tag)
        await session.flush()
        tag_id = tag.id
    await session.execute(delete(PlaceTag).where(PlaceTag.tag_id == tag_id))
    tagged = [
        {"place_id": pid, "tag_id": tag_id, "weight": 1.0, "source": "provider"}
        for pid, rank in best.items()
        if rank <= top_rank
    ]
    for tag_batch in chunked(tagged, ID_CHUNK):
        await session.execute(insert(PlaceTag), list(tag_batch))
    await session.commit()
    log(f"popularity on {len(best)} places · '{tag_name}' on {len(tagged)}")


# --- entry --------------------------------------------------------------------------------------


async def _load_with_retry() -> None:
    db = Database(get_settings())
    try:
        for attempt in range(1, LOCK_RETRIES + 1):
            try:
                print((await load(db)).line())
                return
            except OperationalError as exc:
                if "locked" not in str(exc).lower() or attempt == LOCK_RETRIES:
                    raise
                print(f"database is locked — retry {attempt}/{LOCK_RETRIES} in {LOCK_WAIT_S:.0f}s")
                await asyncio.sleep(LOCK_WAIT_S)
    finally:
        await db.dispose()


def main(argv: Sequence[str]) -> int:
    step = argv[1] if len(argv) > 1 else ""
    if step == "fetch":
        print(fetch(get_settings()).line())
    elif step == "load":
        asyncio.run(_load_with_retry())
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
