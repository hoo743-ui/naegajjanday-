"""Place image canonicalisation (docs/29 §17-27) — `python -m app.cli images-canonicalize`.

Every TourAPI photo was attached at ingestion time by a name + 50 m match and stored as bare URLs on the
place row: no source record, no verification, and the same photo twice (large + small size). This job:

1. reads the TourAPI records we downloaded (title, address, coordinates, photo URLs) from the raw cache,
2. compares each record with the place its photo sits on → evidence → VERIFIED / LIKELY / UNVERIFIED /
   REJECTED and an internal relevance score (`domain.media`),
3. gives every photo one owner across all places (the best-matching one keeps it),
4. writes one `place_image` row per photo, and re-projects `place.thumbnail_url` / `images` to the
   showable photos only (largest size, once each; operator uploads first).

Without `--apply` it only reports what would change. `place_image` keeps every photo, rejected ones too, so
the projection can always be rebuilt.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import unicodedata
from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import delete, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import media
from app.infra.db.models import Place, PlaceImage, PlaceSource
from app.infra.ingestion.dedupe import distance_m

Log = Callable[[str], None]
CHUNK = 2000
_ADDR_NOISE = re.compile(r"[\s,()\-·]+")
_ADDR_TAIL = re.compile(r"\d+(-\d+)?$")


@dataclass(slots=True)
class ImageReport:
    places: int = 0
    photos: int = 0
    statuses: Counter[str] = field(default_factory=Counter)
    showable: int = 0
    shared_photos: int = 0  # photos found on more than one place
    size_duplicates: int = 0  # the same photo stored twice on one place (large + small)
    no_record: int = 0  # a photo whose TourAPI record is not in the raw cache
    cover_lost: int = 0  # places that showed a photo and now show none
    cover_changed: int = 0
    examples: dict[str, list[str]] = field(default_factory=dict)

    def note(self, kind: str, text: str, limit: int = 6) -> None:
        bucket = self.examples.setdefault(kind, [])
        if len(bucket) < limit:
            bucket.append(text)

    def render(self) -> str:
        lines = [
            f"장소 {self.places:,} · 사진 {self.photos:,}"
            f" (같은 사진의 작은 크기 {self.size_duplicates:,}장은 하나로)",
            "검증: " + " · ".join(f"{k} {v:,}" for k, v in sorted(self.statuses.items())),
            f"보여 줄 수 있는 사진 {self.showable:,} · 여러 장소가 나눠 쓰던 사진 {self.shared_photos:,}"
            f" · 원본 기록이 없는 사진 {self.no_record:,}",
            f"대표 사진이 사라지는 장소 {self.cover_lost:,} · 대표 사진이 바뀌는 장소 {self.cover_changed:,}",
        ]
        for kind, rows in self.examples.items():
            lines.append(f"  [{kind}]")
            lines.extend(f"    - {r}" for r in rows)
        return "\n".join(lines)


def _https(url: Any) -> str | None:
    text = str(url or "").strip()
    if not text:
        return None
    return "https://" + text.removeprefix("http://") if text.startswith("http://") else text


def _address(value: str | None) -> str:
    return _ADDR_NOISE.sub("", unicodedata.normalize("NFKC", value or "")).lower()


def address_match(a: str | None, b: str | None) -> bool:
    """Same road / lot address. Building numbers vary by source ("70" vs "70-1"), so both the full string
    and the street without its number are tried; a street alone is not enough (a long road has many)."""
    na, nb = _address(a), _address(b)
    if not na or not nb:
        return False
    if na == nb or (len(na) > 12 and (na in nb or nb in na)):
        return True
    ta, tb = _ADDR_TAIL.search(na), _ADDR_TAIL.search(nb)
    if not ta or not tb:
        return False
    return na[: ta.start()] == nb[: tb.start()] and ta.group(0).split("-")[0] == tb.group(0).split("-")[0]


def load_records(raw_dir: Path) -> dict[str, dict[str, Any]]:
    """contentid → TourAPI item, from every cached page (places, stays, festivals)."""
    out: dict[str, dict[str, Any]] = {}
    for path in sorted(raw_dir.glob("*_*.json")):
        try:
            items = json.loads(path.read_text("utf-8"))
        except (OSError, ValueError):
            continue
        for item in items if isinstance(items, list) else []:
            if isinstance(item, dict) and item.get("contentid"):
                out[str(item["contentid"])] = item
    return out


def _modified(item: dict[str, Any]) -> datetime | None:
    raw = str(item.get("modifiedtime") or "")
    try:
        return datetime.strptime(raw[:14], "%Y%m%d%H%M%S").replace(tzinfo=UTC)
    except ValueError:
        return None


def candidates_for(
    place_id: int,
    name: str,
    address: str | None,
    lat: float,
    lng: float,
    stored: Iterable[str],
    contentid: str,
    record: dict[str, Any] | None,
) -> list[media.Candidate]:
    """The photos of one place from one TourAPI record, one candidate per photo (all sizes folded in)."""
    urls = (
        [u for u in (_https(record.get("firstimage")), _https(record.get("firstimage2"))) if u]
        if record
        else []
    )
    if not urls:  # no record in the cache: what the row stores, with no evidence either way
        urls = [u for u in stored if u]
    if not urls:
        return []
    if record:
        try:
            dist: float | None = distance_m(lat, lng, float(record["mapy"]), float(record["mapx"]))
        except (KeyError, TypeError, ValueError):
            dist = None
        title = str(record.get("title") or "")
        evidence = media.Evidence(
            name_similarity=media.name_similarity(title, name),
            distance_m=None if dist is None else round(dist, 1),
            address_match=address_match(record.get("addr1"), address),
            generic_name=len(media.identity_name(title)) <= 2,
        )
    else:
        evidence = media.Evidence(name_similarity=0.0, distance_m=None, address_match=False)
    by_key: dict[str, list[str]] = {}
    for u in urls:
        by_key.setdefault(media.image_key(u), []).append(u)
    return [
        media.Candidate(
            place_id=place_id,
            url=group[0],  # the first listed is the large one (firstimage)
            source="tourapi",
            evidence=evidence,
            source_place_id=contentid,
            sizes=group[1:],
            modified=_modified(record) if record else None,
            note=None if record else "no source record in the cache",
        )
        for group in by_key.values()
    ]


async def canonicalize(
    session: AsyncSession, raw_dir: Path, *, apply: bool, log: Log = print, now: datetime | None = None
) -> ImageReport:
    now = now or datetime.now(UTC)
    report = ImageReport()
    records = load_records(raw_dir)
    log(f"TourAPI 원본 기록 {len(records):,}건 ({raw_dir})")
    rows = (
        await session.execute(
            select(
                PlaceSource.external_id,
                Place.id,
                Place.name,
                Place.road_address,
                Place.address,
                Place.lat,
                Place.lng,
                Place.thumbnail_url,
                Place.images,
            )
            .join(Place, Place.id == PlaceSource.place_id)
            .where(PlaceSource.provider == "tourapi")
        )
    ).all()
    places: dict[int, dict[str, Any]] = {}
    cands: list[media.Candidate] = []
    for contentid, pid, name, road, addr, lat, lng, thumb, images in rows:
        stored = [thumb, *(images or [])]
        record = records.get(str(contentid))
        found = candidates_for(pid, name, road or addr, lat, lng, stored, str(contentid), record)
        if not found:
            continue
        places.setdefault(pid, {"name": name, "thumb": thumb, "images": list(images or [])})
        if not record:
            report.no_record += len(found)
        report.size_duplicates += sum(len(c.sizes) for c in found)
        cands.extend(found)
    uploads = (
        await session.execute(
            select(PlaceImage.place_id, PlaceImage.url, PlaceImage.image_type).where(
                PlaceImage.source == "upload"
            )
        )
    ).all()
    for pid, url, kind in uploads:
        cands.append(
            media.Candidate(
                place_id=pid,
                url=url,
                source="upload",
                evidence=media.Evidence(1.0, 0.0, True, owner_upload=True),
                image_type=kind,
            )
        )
    judged = media.judge(cands, now)
    # what fetching the files found out (`images-fingerprint`) survives a re-run: the hashes, and a photo that
    # was broken or turned out to be another place's file stays rejected
    kept = {
        (r.place_id, r.image_key): r
        for r in (await session.execute(select(PlaceImage).where(PlaceImage.source == "tourapi"))).scalars()
    }
    for c in judged:
        old = kept.get((c.place_id, c.key))
        note = str((old.evidence or {}).get("note") or "") if old else ""
        if old and (note == "broken image" or note.endswith("(file)")):
            c.status, c.note = media.REJECTED, note
    per_place: dict[int, list[media.Candidate]] = {}
    for c in judged:
        per_place.setdefault(c.place_id, []).append(c)
    owners: dict[str, set[int]] = {}
    for c in judged:
        owners.setdefault(c.key, set()).add(c.place_id)
    report.shared_photos = sum(1 for ids in owners.values() if len(ids) > 1)
    report.places, report.photos = len(per_place), len(judged)
    report.statuses = Counter(c.status for c in judged)
    report.showable = sum(1 for c in judged if media.showable(c))
    projections: dict[int, tuple[str | None, list[str]]] = {}
    for pid, group in per_place.items():
        cover, urls = media.projection(group)
        projections[pid] = (cover, urls)
        before = places.get(pid, {}).get("thumb")
        name = places.get(pid, {}).get("name", pid)
        if before and not cover:
            report.cover_lost += 1
            why = next((c.note or c.status for c in group if c.source == "tourapi"), "")
            e = group[0].evidence
            report.note("사라짐", f"{name} · {why} · 이름 {e.name_similarity:.2f} · 거리 {e.distance_m}m")
        elif before and cover and media.image_key(before) != media.image_key(cover):
            report.cover_changed += 1
    for c in judged:
        if c.status == media.REJECTED and c.note and c.note.startswith("same photo"):
            report.note("여러 장소가 같은 사진", f"{places.get(c.place_id, {}).get('name')} · {c.note}")
    log(report.render())
    if not apply:
        log("(보고만 했어요. 반영하려면 --apply)")
        return report

    await session.execute(delete(PlaceImage).where(PlaceImage.source == "tourapi"))
    values = [
        {
            "file_hash": kept[(c.place_id, c.key)].file_hash if (c.place_id, c.key) in kept else None,
            "phash": kept[(c.place_id, c.key)].phash if (c.place_id, c.key) in kept else None,
            "place_id": c.place_id,
            "image_key": c.key,
            "url": c.url,
            "source": c.source,
            "source_place_id": c.source_place_id,
            "source_query": f"tourapi contentid {c.source_place_id}",
            "collected_at": c.modified or now,
            "image_type": c.image_type,
            "verification_status": c.status,
            "relevance": c.score,
            "evidence": {
                "name_similarity": c.evidence.name_similarity,
                "distance_m": c.evidence.distance_m,
                "address_match": c.evidence.address_match,
                "generic_name": c.evidence.generic_name,
                "sizes": c.sizes,
                "note": c.note,
            },
        }
        for c in judged
        if c.source == "tourapi"
    ]
    # one place can carry two TourAPI records of itself (a stay and a sight): one row per photo
    unique: list[dict[str, Any]] = []
    seen: set[tuple[Any, Any]] = set()
    for v in values:
        pair = (v["place_id"], v["image_key"])
        if pair not in seen:
            seen.add(pair)
            unique.append(v)
    for i in range(0, len(unique), CHUNK):
        await session.execute(insert(PlaceImage), unique[i : i + CHUNK])
    # re-score the upload rows too (their status never changes, but a shared photo can lose to them)
    for c in judged:
        if c.source == "upload":
            await session.execute(
                update(PlaceImage)
                .where(PlaceImage.place_id == c.place_id, PlaceImage.url == c.url)
                .values(verification_status=c.status, relevance=c.score)
            )
    changed = [
        {"id": pid, "thumbnail_url": cover, "images": urls}
        for pid, (cover, urls) in projections.items()
        if places.get(pid, {}).get("thumb") != cover or places.get(pid, {}).get("images") != urls
    ]
    for i in range(0, len(changed), CHUNK):
        await session.execute(update(Place), changed[i : i + CHUNK])
    await session.commit()
    log(f"반영: place_image {len(unique):,}행 · 장소 {len(changed):,}곳의 표시 사진")
    return report


def dhash(data: bytes) -> str | None:
    """64-bit difference hash: the same photo re-compressed or slightly cropped lands a few bits away."""
    try:
        from PIL import Image  # optional: `uv sync --extra images`
    except ImportError:
        return None
    try:
        img = Image.open(io.BytesIO(data)).convert("L").resize((9, 8))
    except Exception:
        return None
    px = list(img.getdata())
    bits = 0
    for row in range(8):
        for col in range(8):
            bits = (bits << 1) | (px[row * 9 + col] > px[row * 9 + col + 1])
    return f"{bits:016x}"


def hamming(a: str, b: str) -> int:
    return bin(int(a, 16) ^ int(b, 16)).count("1")


async def fingerprint(
    session: AsyncSession, *, limit: int, place_ids: Iterable[int] | None = None, log: Log = print
) -> dict[str, int]:
    """Fetches showable photos that have no fingerprint yet: sha256 of the bytes (exact copies under
    different URLs) and a difference hash (near copies). Near copies across places are rejected on the later
    place and the projection is rebuilt by the next `images-canonicalize --apply`."""
    query = select(PlaceImage).where(
        PlaceImage.verification_status.in_(tuple(media.SHOWABLE)), PlaceImage.file_hash.is_(None)
    )
    if place_ids is not None:
        query = query.where(PlaceImage.place_id.in_(list(place_ids)))
    rows = list((await session.execute(query.limit(limit))).scalars())
    fetched = 0
    async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
        for row in rows:
            try:
                res = await client.get(row.url)
                res.raise_for_status()
            except httpx.HTTPError:
                row.verification_status = media.REJECTED  # a broken image is never shown (docs/29 §27)
                row.evidence = {**(row.evidence or {}), "note": "broken image"}
                continue
            row.file_hash = hashlib.sha256(res.content).hexdigest()
            row.phash = dhash(res.content)
            fetched += 1
    await session.flush()
    known = list(
        (
            await session.execute(
                select(PlaceImage).where(
                    PlaceImage.file_hash.is_not(None),
                    PlaceImage.verification_status.in_(tuple(media.SHOWABLE)),
                )
            )
        ).scalars()
    )
    known.sort(key=lambda r: (-r.relevance, r.place_id))
    touched = {r.place_id for r in rows}
    owners_by_hash: dict[str, int] = {}
    hashes: list[tuple[str, int]] = []
    duplicates = 0
    for r in known:
        owner = owners_by_hash.get(r.file_hash or "")
        near = next(
            (pid for h, pid in hashes if r.phash and pid != r.place_id and hamming(h, r.phash) <= 6), None
        )
        other = owner if owner is not None and owner != r.place_id else near
        if other is not None:
            r.verification_status = media.REJECTED
            r.evidence = {**(r.evidence or {}), "note": f"same photo as place {other} (file)"}
            duplicates += 1
            touched.add(r.place_id)
            continue
        owners_by_hash.setdefault(r.file_hash or "", r.place_id)
        if r.phash:
            hashes.append((r.phash, r.place_id))
    await session.flush()
    await reproject(session, touched)
    await session.commit()
    log(f"받은 사진 {fetched} / {len(rows)} · 다른 장소와 같은 파일 · 거의 같은 사진 {duplicates}")
    return {"fetched": fetched, "checked": len(rows), "duplicates": duplicates}


async def reproject(session: AsyncSession, place_ids: Iterable[int]) -> int:
    """Rebuilds `place.thumbnail_url` / `images` of these places from their `place_image` rows."""
    ids = list(place_ids)
    if not ids:
        return 0
    rows = list((await session.execute(select(PlaceImage).where(PlaceImage.place_id.in_(ids)))).scalars())
    grouped: dict[int, list[media.Candidate]] = {pid: [] for pid in ids}
    for r in rows:
        c = media.Candidate(
            place_id=r.place_id,
            url=r.url,
            source=r.source,
            evidence=media.Evidence(0.0, None, False),
            image_type=r.image_type,
            status=r.verification_status,
            score=r.relevance,
        )
        grouped[r.place_id].append(c)
    for pid, group in grouped.items():
        cover, urls = media.projection(group)
        await session.execute(update(Place).where(Place.id == pid).values(thumbnail_url=cover, images=urls))
    return len(grouped)


async def backfill_credits(
    session: AsyncSession, raw_dir: Path, *, apply: bool, log: Callable[[str], None] = print
) -> Counter[str]:
    """TourAPI 사진마다 출처 · 라이선스 · 작은 크기를 채운다 (docs/43). 원본 캐시의 `cpyrhtDivCd` 로
    공공누리 제1유형(출처표시)과 제3유형(출처표시 · 변경금지)을 가른다. 이미 채운 칸은 덮지 않는다."""
    from app.domain.image_ref import TOURAPI_CREDIT, TOURAPI_HOME, TOURAPI_LICENSE, TOURAPI_LICENSE_BY_CODE

    records = load_records(raw_dir)
    counts: Counter[str] = Counter()
    rows = list(
        (
            await session.execute(
                select(PlaceImage).where(PlaceImage.source == "tourapi", PlaceImage.license.is_(None))
            )
        ).scalars()
    )
    for r in rows:
        item = records.get(r.source_place_id or "")
        code = str((item or {}).get("cpyrhtDivCd") or "")
        counts[code or ("기록 없음" if item is None else "유형 칸 비어 있음")] += 1
        if not apply:
            continue
        r.license = TOURAPI_LICENSE_BY_CODE.get(code, TOURAPI_LICENSE)
        r.photographer = "한국관광공사"
        r.source_url = TOURAPI_HOME
        r.attribution_text = TOURAPI_CREDIT
        if item and _https(item.get("firstimage")) == r.url:
            r.thumbnail_url = _https(item.get("firstimage2")) or r.url
        else:
            r.thumbnail_url = r.url
    log(
        f"출처를 채울 TourAPI 사진 {len(rows):,}장 · "
        + " · ".join(f"{k or '?'} {v:,}" for k, v in counts.most_common())
        + ("" if apply else "  (보고만 했다. 반영하려면 --apply)")
    )
    if apply:
        await session.commit()
    return counts
