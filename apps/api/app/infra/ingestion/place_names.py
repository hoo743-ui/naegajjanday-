"""Place names joined with ";" (backlog 6): "신의주찹쌀순대;황소곱창;장충왕족발".

The 소상공인 상가정보 (SEMAS) file writes a comma inside a store name as ";" — the same store in
the restaurant licence data reads "지금,여기", "카페,메쥬", "나연이네족탕,삼계탕",
"흥부찜닭,공수간,삼겹본능 신림점".
So a ";" is one of three things, and the name shown should be:

- **a comma in one name** — "지금;여기", "셀프사진관예뻐서;봄 동탄점", "1;2;3게임장", "10;000원의행복":
  the first part is too short to be a name by itself, the next starts with a one-letter word, or digits meet
  digits → the comma comes back ("지금,여기", "1,2,3게임장").
- **a name and its menu** — "잭아저씨족발;보쌈", "청와삼대족발;보쌈;칼국수" → the name ("잭아저씨족발").
- **several businesses at one address** — "신의주찹쌀순대;황소곱창;장충왕족발", "원콜전자;오백냥노래연습실" →
  the one that is what the place is filed as (a karaoke → the 노래연습장), otherwise the first.

A branch written after the last part ("담소소사골순대;육개장 문정점") stays with the name shown. Idempotent: a
name without ";" is returned as it is.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.infra.db.session import Database

SEP = ";"
MIN_NAME_LEN = 4  # "팔천순대" is a name by itself, "지금" / "카페" / "오늘" are not
_BRANCH = re.compile(r"\s+(\S{2,}점)$")
# "…점" words that are not a branch, or only the tail of one ("영남대 병원점")
_NOT_A_BRANCH = frozenset({"전문점", "직영점", "병원점", "본점", "지점", "분점", "매점", "상점", "체인점"})
# the word that says what a place filed under a category is — to pick it among several businesses
_CATEGORY_WORDS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("activity.karaoke", re.compile(r"노래|코인|싱어")),
    ("activity.photo", re.compile(r"사진|포토|스튜디오|photo", re.I)),
    ("activity.arcade", re.compile(r"게임|오락|뽑기|아케이드")),
    ("activity.sports", re.compile(r"당구|볼링|탁구|스크린|골프")),
    ("activity.craft", re.compile(r"공방|도예|체험|클래스")),
    ("dessert.bakery", re.compile(r"빵|베이커리|제과|bakery", re.I)),
    ("dessert", re.compile(r"떡|디저트|케이크|빙수|아이스크림")),
    ("cafe", re.compile(r"카페|까페|커피|다방|cafe|coffee", re.I)),
    ("food.brunch", re.compile(r"브런치|토스트|샌드위치|베이글")),
    ("food.bbq", re.compile(r"고기|갈비|구이|곱창|막창|삼겹|한우|숯불|식당")),
    ("bar", re.compile(r"술|호프|포차|주점|이자카야|펍|와인|바$")),
)


# a part that is only what the place is ("노래연습장"), not a name: never picked over a real name
_GENERIC = re.compile(
    r"(?:코인)?(?:노래(?:연습장|연습실|방|타운)|게임장|오락실|당구장|(?:셀프)?사진관|카페|커피숍?|공방|식당)"
)


def _compact_len(s: str) -> int:
    return len(re.sub(r"\s+", "", s))


def _strip_open_paren(s: str) -> str:
    """ "식사이어티(풍국면" → "식사이어티": a bracket the split left open."""
    if s.count("(") > s.count(")"):
        s = s[: s.rfind("(")]
    if s.count(")") > s.count("("):
        s = s[s.find(")") + 1 :]
    return s.strip()


def _join_numbers(parts: list[str]) -> list[str]:
    """ "1;2;3게임장" / "10;000원" / "9;900원": digits on both sides of ";" are one number or list."""
    out = [parts[0]]
    for p in parts[1:]:
        if out[-1][-1:].isdigit() and p[:1].isdigit():
            out[-1] = f"{out[-1]},{p}"
        else:
            out.append(p)
    return out


def _wanted(category_code: str) -> re.Pattern[str] | None:
    for code, words in _CATEGORY_WORDS:
        if category_code == code or category_code.startswith(code + "."):
            return words
    return None


def _pick(parts: list[str], category_code: str) -> str:
    """Several businesses (or a name and its menu): the one the place is filed as, else the first."""
    words = _wanted(category_code)
    if words is not None and not words.search(parts[0]):
        hits = [
            p
            for p in parts[1:]
            if words.search(p) and _compact_len(p) >= MIN_NAME_LEN and not _GENERIC.fullmatch(p.strip())
        ]
        if hits:
            return hits[0]
    return parts[0]


def display_name(name: str, category_code: str = "") -> str:
    """The name to show for a place whose source wrote ";" in it (see the module doc)."""
    if SEP not in name:
        return name
    # "(1호점;2호점;)" — a list inside brackets is a note, not the name
    tidy = re.sub(r"\([^()]*;[^()]*\)", " ", name)
    parts = [p.strip() for p in tidy.split(SEP) if p.strip()]
    if not parts:
        return name.replace(SEP, ",").strip()
    parts = _join_numbers(parts)
    if len(parts) == 1:
        return re.sub(r"\s+", " ", parts[0]).strip()
    first_word_next = parts[1].split()[0] if parts[1].split() else ""
    if _compact_len(_strip_open_paren(parts[0])) < MIN_NAME_LEN or _compact_len(first_word_next) <= 1:
        return re.sub(r"\s+", " ", ",".join(parts)).strip()  # one name with a comma in it
    branch = _BRANCH.search(parts[-1])
    chosen = _strip_open_paren(_pick(parts, category_code))
    if len(chosen) < 2:
        chosen = _strip_open_paren(parts[0]) or parts[0]
    if (
        branch
        and branch.group(1) not in _NOT_A_BRANCH
        and branch.group(1) not in chosen
        and not _BRANCH.search(chosen)
    ):
        chosen = f"{chosen} {branch.group(1)}"
    return re.sub(r"\s+", " ", chosen).strip()


async def tidy_stored(db: Database, *, log: Callable[[str], None] = print) -> str:
    """Rename the places already stored with ";" in their name (data sync `rules/place_names`, docs/57).
    Idempotent: a tidied name has no ";" left, so a second run finds nothing."""
    from sqlalchemy import select, update

    from app.infra.db.models import Category, Place

    seen = changed = 0
    async with db.sessionmaker() as session:
        rows = (
            await session.execute(
                select(Place.id, Place.name, Category.code)
                .join(Category, Category.id == Place.category_id)
                .where(Place.name.contains(SEP))
            )
        ).all()
        todo = []
        for pid, name, code in rows:
            seen += 1
            new = display_name(name, code)
            if new and new != name:
                todo.append({"id": pid, "name": new})
        for start in range(0, len(todo), 2_000):
            await session.execute(update(Place), todo[start : start + 2_000])
            await session.commit()
            changed += len(todo[start : start + 2_000])
    line = f"names: seen={seen} renamed={changed}"
    log(line)
    return line
