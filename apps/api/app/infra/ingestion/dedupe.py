"""Cross-provider duplicate detection: name similarity + distance < 50 m → confidence score."""

from __future__ import annotations

import math
import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass
from difflib import SequenceMatcher

MAX_DISTANCE_M = 50.0
MATCH_THRESHOLD = 0.82
_BRANCH_RE = re.compile(r"(본점|직영점|[가-힣A-Za-z0-9]+점)$")
_NOISE_RE = re.compile(r"[\s\-_·.,()\[\]&'\"!/]+")


@dataclass(frozen=True, slots=True)
class ExistingPlace:
    id: int
    name: str
    lat: float
    lng: float
    phone: str | None = None


@dataclass(frozen=True, slots=True)
class Match:
    place_id: int
    confidence: float
    distance_m: float


def normalize_name(name: str) -> str:
    text = unicodedata.normalize("NFKC", name).lower().strip()
    text = _BRANCH_RE.sub("", text)
    return _NOISE_RE.sub("", text)


def name_similarity(a: str, b: str) -> float:
    na, nb = normalize_name(a), normalize_name(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    ratio = SequenceMatcher(None, na, nb).ratio()
    if na in nb or nb in na:  # "코인 로스터리" vs "코인 로스터리 홍대"
        ratio = max(ratio, 0.9)
    return ratio


def distance_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    # equirectangular approximation — exact enough below 1 km
    x = math.radians(lng2 - lng1) * math.cos(math.radians((lat1 + lat2) / 2))
    y = math.radians(lat2 - lat1)
    return math.hypot(x, y) * 6_371_000.0


def _digits(phone: str | None) -> str:
    return re.sub(r"\D", "", phone or "")


def confidence(name_sim: float, dist_m: float, same_phone: bool) -> float:
    proximity = max(0.0, 1.0 - dist_m / MAX_DISTANCE_M)
    score = 0.7 * name_sim + 0.3 * proximity
    if same_phone:
        score = min(1.0, score + 0.15)
    return round(score, 4)


def find_match(
    name: str, lat: float, lng: float, phone: str | None, existing: Iterable[ExistingPlace]
) -> Match | None:
    best: Match | None = None
    for e in existing:
        d = distance_m(lat, lng, e.lat, e.lng)
        if d >= MAX_DISTANCE_M:
            continue
        same_phone = bool(_digits(phone)) and _digits(phone) == _digits(e.phone)
        c = confidence(name_similarity(name, e.name), d, same_phone)
        if c >= MATCH_THRESHOLD and (best is None or c > best.confidence):
            best = Match(e.id, c, d)
    return best
