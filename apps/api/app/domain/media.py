"""Place images as their own entity (docs/29 §16-27). Pure: no DB, no network.

Choosing places and showing them are separate jobs. The engine decides *where to go* without ever
looking at photos; this module decides *how to show* a place that was already chosen.

    identity evidence (source title / address / coordinates vs the place) → verification status
    relevance = identity + source reliability + geography + freshness − duplicate − ambiguity
    same photo = one key (the same file in two sizes, the same file under two URLs)

A photo is shown only when it is VERIFIED or LIKELY, its relevance passes `DISPLAY_MIN`, and no other place
owns the same photo. No photo beats a wrong photo: the UI then shows a small, labelled category example.
The relevance is internal and never shown to the user.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from difflib import SequenceMatcher
from urllib.parse import urlsplit

REAL_PLACE, MENU, INTERIOR, EXTERIOR, CATEGORY_EXAMPLE, UNKNOWN = (
    "REAL_PLACE", "MENU", "INTERIOR", "EXTERIOR", "CATEGORY_EXAMPLE", "UNKNOWN",
)  # fmt: skip
VERIFIED, LIKELY, UNVERIFIED, REJECTED = "VERIFIED", "LIKELY", "UNVERIFIED", "REJECTED"
SHOWABLE = frozenset({VERIFIED, LIKELY})

DISPLAY_MIN = 0.55
# visitkorea serves one photo in several sizes: .../resource/42/4111342_image2_1.jpg (large) and
# .../4111342_image3_1.jpg (small). Same number = same photo.
_TOURAPI_RE = re.compile(r"/cms/(resource\w*)/\d+/(\d+)_image\d+_\d+", re.IGNORECASE)
_BRACKETED = re.compile(r"[\[(]([^\])]+)[\])]")
_NAME_NOISE = re.compile(r"\[[^\]]*\]|\([^)]*\)|[\s\-_·.,&'\"!/]+")
SOURCE_RELIABILITY = {"upload": 1.0, "tourapi": 0.9}  # an operator's own photo, the tourism board's record


def image_key(url: str) -> str:
    """One key per photo, whatever size or URL spelling it is served under."""
    if m := _TOURAPI_RE.search(url):
        return f"tourapi:{m.group(1).lower()}:{m.group(2)}"
    parts = urlsplit(url.strip())
    canonical = f"{parts.netloc.lower()}{parts.path}"
    return "url:" + hashlib.sha1(canonical.encode()).hexdigest()[:20]


@dataclass(frozen=True, slots=True)
class Evidence:
    """How sure we are that the photo's source record describes this very place."""

    name_similarity: float  # source title vs place name, 0..1 (normalised, branch suffix ignored)
    distance_m: float | None  # source coordinates vs place coordinates
    address_match: bool  # same road / lot address (normalised)
    owner_upload: bool = False  # an operator attached it to this place by hand
    generic_name: bool = False  # a name too plain to identify anything ("카페", "공원")


def identity_name(name: str) -> str:
    """For telling places apart: labels in brackets ("[K드라마 촬영지]") and spacing go, the words stay.
    (The ingestion matcher also drops branch suffixes ending in "점" — which empties "대동백화점".)"""
    return _NAME_NOISE.sub("", unicodedata.normalize("NFKC", name)).lower()


def _name_forms(name: str) -> set[str]:
    """A name and what it says in brackets: "한려해상국립공원 (오동도)" is also "오동도",
    "서울 구 벨기에영사관 (현 서울시립 남서울미술관)" is also "서울시립 남서울미술관"."""
    forms = {identity_name(name)}
    for inner in _BRACKETED.findall(unicodedata.normalize("NFKC", name)):
        forms.add(identity_name(re.sub(r"^(현|구|옛)\s+", "", inner.strip())))
    return {f for f in forms if f}


def _similarity(na: str, nb: str) -> float:
    if na == nb:
        return 1.0
    ratio = SequenceMatcher(None, na, nb).ratio()
    if na in nb or nb in na:  # "공근혜갤러리" vs "공근혜갤러리 삼청"
        ratio = max(ratio, 0.9)
    return ratio


def name_similarity(a: str, b: str) -> float:
    forms_a, forms_b = _name_forms(a), _name_forms(b)
    if not forms_a or not forms_b:
        return 0.0
    return round(max(_similarity(x, y) for x in forms_a for y in forms_b), 3)


def verify(e: Evidence) -> str:
    if e.owner_upload:
        return VERIFIED
    near = e.distance_m is not None and e.distance_m <= 100
    close = e.distance_m is not None and e.distance_m <= 300
    far = e.distance_m is not None and e.distance_m > 1000
    if e.name_similarity < 0.5 or far:
        return REJECTED
    if e.generic_name and not (near and (e.address_match or e.name_similarity >= 0.99)):
        return UNVERIFIED  # "카페" 200 m away could be any café
    if (e.name_similarity >= 0.9 and near) or (e.address_match and e.name_similarity >= 0.8):
        return VERIFIED
    if e.name_similarity >= 0.75 and (close or e.address_match):
        return LIKELY
    if e.address_match and near and e.name_similarity >= 0.55:  # "선심갈비" at 선심참숯갈비's door
        return LIKELY
    return UNVERIFIED


def relevance(
    e: Evidence,
    source: str,
    *,
    modified: datetime | None = None,
    now: datetime | None = None,
    duplicate: bool = False,
) -> float:
    identity = 1.0 if e.owner_upload else e.name_similarity
    geo = 1.0 if e.owner_upload else (0.0 if e.distance_m is None else max(0.0, 1.0 - e.distance_m / 300.0))
    if e.address_match:
        geo = max(geo, 0.9)
    fresh = 0.5
    if modified is not None and now is not None:
        years = (now - modified).days / 365.0
        fresh = 1.0 if years <= 2 else 0.6 if years <= 5 else 0.3
    score = (
        0.5 * identity
        + 0.2 * SOURCE_RELIABILITY.get(source, 0.5)
        + 0.2 * geo
        + 0.1 * fresh
        - (0.4 if duplicate else 0.0)
        - (0.15 if e.generic_name else 0.0)
    )
    return round(max(0.0, min(1.0, score)), 3)


@dataclass(slots=True)
class Candidate:
    """One photo of one place, before the cross-place check."""

    place_id: int
    url: str
    source: str
    evidence: Evidence
    source_place_id: str | None = None
    sizes: list[str] = field(default_factory=list)  # other URLs of the same photo (smaller sizes)
    image_type: str = REAL_PLACE
    modified: datetime | None = None
    status: str = UNVERIFIED
    score: float = 0.0
    note: str | None = None

    @property
    def key(self) -> str:
        return image_key(self.url)


def judge(candidates: Iterable[Candidate], now: datetime) -> list[Candidate]:
    """Verification + relevance for each, then one owner per photo across all places (docs/29 §20).

    When several places carry the same photo, the one whose record matches it best keeps it; for the others
    it is rejected — the same picture under two different names is wrong for at least one of them."""
    items = list(candidates)
    for c in items:
        c.status = verify(c.evidence)
        c.score = relevance(c.evidence, c.source, modified=c.modified, now=now)
    by_key: dict[str, list[Candidate]] = {}
    for c in items:
        by_key.setdefault(c.key, []).append(c)
    for group in by_key.values():
        owners = {c.place_id for c in group}
        if len(owners) < 2:
            continue
        best = max(group, key=lambda c: (c.status in SHOWABLE, c.score, -c.place_id))
        for c in group:
            if c.place_id != best.place_id:
                c.status, c.note = REJECTED, f"same photo as place {best.place_id}"
                c.score = relevance(c.evidence, c.source, modified=c.modified, now=now, duplicate=True)
    return items


def showable(c: Candidate) -> bool:
    return c.status in SHOWABLE and c.score >= DISPLAY_MIN and c.image_type != CATEGORY_EXAMPLE


def projection(candidates: Sequence[Candidate]) -> tuple[str | None, list[str]]:
    """What a place row shows: its best showable photo as the cover and each showable photo once
    (largest size only). Operator uploads come first."""
    good = sorted(
        (c for c in candidates if showable(c)),
        key=lambda c: (c.source != "upload", -c.score, c.url),
    )
    seen: set[str] = set()
    urls: list[str] = []
    for c in good:
        if c.key not in seen:
            seen.add(c.key)
            urls.append(c.url)
    return (urls[0] if urls else None), urls


def distinct_photos(urls: Sequence[str | None]) -> list[str | None]:
    """In one course no photo appears twice (docs/29 §21): the first stop that shows it keeps it,
    a later stop with the same photo shows none (and the UI falls back to the small category tile)."""
    seen: set[str] = set()
    out: list[str | None] = []
    for url in urls:
        if not url:
            out.append(None)
            continue
        key = image_key(url)
        out.append(None if key in seen else url)
        seen.add(key)
    return out
