"""이런 동네예요 (2026-09-26): a few sentences on what the neighbourhood is like.

The 55 hotspots have an editorial text (data/regions/intros.json — character, who goes, what to do; no
numbers, those are the data's to tell). Every other place gets a few sentences stitched from what the data
knows — how many shops, what the signs say unusually often, which sights the shops are named after —
each followed by what that means for a day there (docs/54 voice), never more than the data backs.
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


def _subj(word: str) -> str:
    return f"{word}{'이' if _batchim(word) else '가'}"


def _scale(shops: int) -> str:
    """What the number of shops means for the day, not just the number."""
    if shops >= 1000:
        return f"가게가 {shops:,}곳이라, 미리 정해 두지 않고 걸어도 하루가 채워져요."
    if shops >= 300:
        return f"가게 {shops:,}곳이 모여 있어, 가려던 곳 옆에 한 곳쯤 더 들르기 쉬워요."
    return f"가게 {shops:,}곳 남짓한 아담한 동네라, 몇 곳에 오래 머무는 하루가 어울려요."


def intro_for(slug: str | None, signature: Signature) -> RegionIntro | None:
    if slug and (edited := editorial_intros().get(slug)):
        return RegionIntro(str(edited["text"]), tuple(edited.get("keywords") or ()), "editorial")
    parts: list[str] = []
    if signature.shops >= 50:
        parts.append(_scale(signature.shops))
    words = [s.word for s in signature.specialties[:2]]
    sights = [s.name for s in signature.sights[:2]]
    said = " · ".join(f"‘{w}’" for w in words) + ("이" if words and _batchim(words[-1]) else "가")
    named = " · ".join(sights)
    # docs/54: say what the data shows, then what it means — never more than the data can back
    if words and sights:
        parts.append(f"간판엔 {said} 유독 많고, 가게 이름엔 {_subj(named)} 자주 붙어요.")
        parts.append("뭘 먹을지는 간판이, 어디를 볼지는 가게 이름이 먼저 알려 주는 동네예요.")
    elif words:
        parts.append(f"간판엔 {said} 유독 많아요. 여기서 뭘 먹을지는 동네가 먼저 말해 주는 셈이에요.")
    elif sights:
        parts.append(f"가게 이름에 {_subj(named)} 자주 붙어요.")
        parts.append("동네가 스스로를 그 이름으로 소개하는 셈이에요.")
    if not parts:
        return None
    return RegionIntro(" ".join(parts), tuple(words), "data")
