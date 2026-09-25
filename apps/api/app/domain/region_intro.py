"""이런 동네예요 (2026-09-26): a few sentences on what the neighbourhood is like.

The 55 hotspots have an editorial text (data/regions/intros.json — character, who goes, what to do; no
numbers, those are the data's to tell). Every other place gets one sentence stitched from what the data
knows: how many shops, what the signs say unusually often, what people come to see.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.domain.signature import Signature

INTROS_PATH = Path(__file__).resolve().parents[2] / "data" / "regions" / "intros.json"


@dataclass(frozen=True, slots=True)
class RegionIntro:
    text: str
    keywords: tuple[str, ...]
    source: str  # editorial | data


@lru_cache(maxsize=1)
def editorial_intros(path: Path = INTROS_PATH) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {k: v for k, v in data.items() if not k.startswith("_")}


def _batchim(word: str) -> bool:
    """Whether the last syllable has a final consonant (을/를, 이/가 …)."""
    last = word.strip()[-1:] if word.strip() else ""
    if not ("가" <= last <= "힣"):
        return False
    return (ord(last) - ord("가")) % 28 != 0


def _obj(word: str) -> str:
    return f"{word}{'을' if _batchim(word) else '를'}"


def intro_for(slug: str | None, signature: Signature) -> RegionIntro | None:
    if slug and (edited := editorial_intros().get(slug)):
        return RegionIntro(str(edited["text"]), tuple(edited.get("keywords") or ()), "editorial")
    parts: list[str] = []
    if signature.shops >= 50:
        parts.append(f"가게 {signature.shops:,}곳이 모인 동네예요.")
    words = [s.word for s in signature.specialties[:2]]
    sights = [s.name for s in signature.sights[:2]]
    said = " · ".join(f"‘{w}’" for w in words) + ("이" if words and _batchim(words[-1]) else "가")
    if words and sights:
        parts.append(f"간판엔 {said} 유독 많고, 사람들은 주로 {_obj(' · '.join(sights))} 보러 와요.")
    elif words:
        parts.append(f"간판엔 {said} 유독 많아요.")
    elif sights:
        parts.append(f"사람들은 주로 {_obj(' · '.join(sights))} 보러 와요.")
    if not parts:
        return None
    return RegionIntro(" ".join(parts), tuple(words), "data")
