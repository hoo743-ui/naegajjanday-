"""Bars filed as restaurants (docs/59 #14 · docs/60 §1): the licence says what the place pours.

The 소상공인 상가정보 (SEMAS) file only knows two drinking codes (I21103 생맥주 · I21104 요리 주점), so
a 호프, a 소주방 or a 7080 라이브카페 it filed under 한식 · 경양식 · 카페 is a restaurant to us —
14,257 of them (docs/60 measured) — and no bar had a kind: 와인바 · 칵테일바 · 이자카야 · 포차 · 막걸리
held 0 places.
The restaurant / café licence rows attached by `ingest-bulk marks` (`place_source` lic_restaurant · lic_cafe)
carry the licence's own kind, `업태구분명`. This module reads it, with the name as the second witness:

- **a drinking licence** (호프/통닭 · 정종/대포집/소주방 · 감성주점 · 라이브카페) on a restaurant →
  - the name says a meal ("…감자탕", "…국밥", "…참치", "…양꼬치") → it stays a restaurant, tagged 술자리
    (they pour: a family's meal does not go there — purposes.json family never_tags);
  - 호프/통닭 and the name says chicken ("…치킨", "…통닭") without 호프 · 비어 · 맥주 → a 치킨집:
    stays, 술자리;
  - otherwise → a bar. Restaurants whose kind is already a strong meal (중식 · 고기 · 분식 · 면 …) move only
    when the name says so ("중식주점연", "태양포차").
- **a café** moves only when the name says bar ("금성호프", "달빛커피호프" — a 커피호프 is a bar,
  "보스라이브카페"); a café name with only a loose bar word ("…커피BAR", "카페라운지") stays a café,
  tagged 술자리; a name that says nothing stays as it is (the licence may be an older business at that
  address; SEMAS is the fresher survey).
- **the kind of bar** — the name first (이자카야 · 사케 → bar.izakaya, 와인 → bar.wine,
  칵테일 · 위스키 · 하이볼 → bar.cocktail, 막걸리 · 전통주 · 주막 → bar.makgeolli,
  포차 · 소주방 · 다찌 → bar.pocha, 호프 · 비어 · 맥주 · 펍 → bar.pub), then the licence (호프/통닭 → bar.pub,
  정종/대포집/소주방 → bar.pocha, a Japanese restaurant with a drinking licence → bar.izakaya);
  감성주점 · 라이브카페 without a word stay plain `bar`.
  Every place already in `bar` gets its kind the same way (the name alone when it has no licence row); a
  `bar.pub` (SEMAS 생맥주) changes only when the name names another kind.

Stored rows change (the category is what SQL filters by: roles, search, the engine's candidates), so this
is a data-sync rule (`rules/bar_licence`, docs/57): when this file changes, every place is re-derived from
where it started — the first move writes a `place_revision` (action `reclassify`, before = the category it
had) and later runs start from that, so a word taken out of a list moves its places back. The 술자리 tags it
writes are `place_tag` rows with source `licence`, owned by this rule (added and removed to match). Moved
places whose price is a SEMAS estimate are re-priced as what they now are (bulk/reprice.py). No outside calls;
idempotent — a second run changes nothing.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.infra.db.session import Database

Log = Callable[[str], None]

LICENCE_PROVIDERS = ("lic_restaurant", "lic_cafe")
KIND_KEY = "업태구분명"  # 업태구분명
HOF = "호프/통닭"
SOJU = "정종/대포집/소주방"
LOUNGE = "감성주점"
LIVE = "라이브카페"
DRINK_KINDS = (HOF, SOJU, LOUNGE, LIVE)
DRINK_TAG = "술자리"
DRINK_TAG_WEIGHT = 0.6  # = exclude_tag_threshold: a family's meal never lands there, a friends' evening may
TAG_SOURCE = "licence"
REVISION_ACTION = "reclassify"
REVISION_NOTE = "rules/bar_licence"
BATCH = 2_000

# the kind of bar, most specific first (compact, upper-cased names)
# fmt: off
BAR_KIND_WORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("bar.izakaya", ("이자카야", "이자까야", "이자카나", "사케", "오뎅바", "야키토리", "로바타", "갓포",
                     "IZAKAYA")),
    ("bar.wine", ("와인", "WINE")),
    ("bar.cocktail", ("칵테일", "위스키", "하이볼", "몰트", "스피크이지", "스피키지", "COCKTAIL", "WHISKY",
                      "WHISKEY")),
    ("bar.makgeolli", ("막걸리", "전통주", "주막", "양조장")),
    ("bar.pocha", ("포차", "포장마차", "소주방", "대포집", "다찌", "선술집")),
    ("bar.pub", ("호프", "비어", "맥주", "펍", "생맥", "브루", "BEER", "PUB", "HOF", "BREW")),
)
# a name that says bar without saying which (with the words above)
BAR_WORDS = ("술집", "주점", "술상", "술한잔", "라이브카페", "7080", "BAR", "LOUNGE", "라운지")
# a name that says a meal: the place stays a restaurant even under a drinking licence
MEAL_WORDS: tuple[str, ...] = (
    "식당", "밥", "국수", "칼국수", "냉면", "김밥", "분식", "떡볶이", "순대", "국밥", "해장", "감자탕",
    "설렁탕", "곰탕", "갈비탕", "추어", "찌개", "전골", "족발", "보쌈", "고기", "갈비", "삼겹", "한우",
    "정육", "곱창", "막창", "대창", "양꼬치", "짬뽕", "짜장", "반점", "마라", "중화", "돈까스", "돈가스",
    "돈가츠", "카츠", "초밥", "스시", "참치", "라멘", "우동", "소바", "덮밥", "버거", "피자", "파스타",
    "샤브", "닭갈비", "찜닭", "오리구이", "오리백숙", "횟집", "횟", "수산", "회센터", "어시장", "광어",
    "장어", "쌈밥", "한정식", "백반", "뷔페", "도시락", "아구", "아귀", "생선", "쭈꾸미", "주꾸미", "낙지",
    "맘스터치", "타코", "만두", "베이커리", "제과", "숯불", "구이", "바베큐",
)
CHICKEN_WORDS = (
    "치킨", "통닭", "닭강정", "후라이드", "교촌", "BHC", "굽네", "처갓집", "페리카나", "멕시카나",
    "또래오래", "60계", "푸라닭", "BBQ", "KFC",
)
CAFE_WORDS = ("카페", "까페", "커피", "다방", "COFFEE", "CAFE", "에스프레소", "로스터", "티룸")
# restaurants whose kind already says a meal: moved only by a bar word in the name
STRONG_MEAL = (
    "food.chinese", "food.bbq", "food.noodle", "food.snack", "food.asian", "food.brunch", "dessert",
)
# fmt: on


def _compact(name: str) -> str:
    return re.sub(r"\s+", "", name).upper()


def _has(compact: str, words: Iterable[str]) -> bool:
    return any(w in compact for w in words)


def _in(code: str, prefix: str) -> bool:
    return code == prefix or code.startswith(prefix + ".")


def bar_kind_by_name(compact: str) -> str | None:
    for code, words in BAR_KIND_WORDS:
        if _has(compact, words):
            return code
    return None


def _says_bar(compact: str) -> bool:
    return bar_kind_by_name(compact) is not None or _has(compact, BAR_WORDS)


def _licence_kind(kind: str | None, origin: str) -> str:
    if _in(origin, "food.japanese"):
        return "bar.izakaya"  # a Japanese kitchen that pours ("세이고우", "생마차", "토리메로")
    if kind == HOF:
        return "bar.pub"
    if kind == SOJU:
        return "bar.pocha"
    return "bar"  # 감성주점 · 라이브카페 say bar, not which


@dataclass(frozen=True, slots=True)
class Decision:
    category: str
    drinks: bool = False  # tag 술자리 (a restaurant or café that pours)


def decide(origin: str, kind: str | None, name: str) -> Decision:
    """Where a place filed under `origin` belongs, given its licence kind (None: no licence row) and name."""
    compact = _compact(name)
    drinking = kind in DRINK_KINDS
    if _in(origin, "bar"):
        by_name = bar_kind_by_name(compact)
        if origin == "bar":
            return Decision(by_name or (_licence_kind(kind, origin) if drinking else "bar"))
        if origin == "bar.pub" and by_name and by_name != "bar.pub":
            return Decision(by_name)
        return Decision(origin)
    if not drinking:
        return Decision(origin)
    if _in(origin, "cafe"):
        by_name = bar_kind_by_name(compact)
        if by_name:  # "금성호프", "달빛커피호프" (a 커피호프 is a bar), "카페&펍"
            return Decision(by_name)
        if not _has(compact, BAR_WORDS):
            return Decision(origin)
        if _has(compact, CAFE_WORDS) and "라이브카페" not in compact:
            return Decision(origin, drinks=True)  # "커피바", "카페라운지": a café that pours
        return Decision(_licence_kind(kind, origin))
    if not (_in(origin, "food") or _in(origin, "dessert")):
        return Decision(origin)  # activity · stay · …: the licence is the kitchen inside, not the place
    by_name = bar_kind_by_name(compact)
    if kind == HOF and by_name != "bar.pub" and _has(compact, CHICKEN_WORDS):
        return Decision(origin, drinks=True)  # 치킨집 (a 치킨호프 names its 호프)
    if origin.startswith(STRONG_MEAL) or _has(compact, MEAL_WORDS):
        if _says_bar(compact) and not _has(compact, MEAL_WORDS):
            return Decision(by_name or _licence_kind(kind, origin))
        return Decision(origin, drinks=True)
    return Decision(by_name or _licence_kind(kind, origin))


@dataclass(slots=True)
class Report:
    seen: int = 0
    moved: int = 0  # category changed in this run (either way)
    tagged: int = 0  # 술자리 rows added
    untagged: int = 0  # 술자리 rows removed
    repriced: int = 0
    by_move: dict[str, int] = field(default_factory=dict)

    def line(self) -> str:
        top = ", ".join(f"{k}={v}" for k, v in sorted(self.by_move.items(), key=lambda kv: -kv[1])[:8])
        return (
            f"bars: seen={self.seen} moved={self.moved} drinks_tag+={self.tagged} -={self.untagged} "
            f"repriced={self.repriced}" + (f" [{top}]" if top else "")
        )


def _raw(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    try:
        data = json.loads(value or "{}")
    except (TypeError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


async def apply(db: Database, *, log: Log = print) -> Report:
    """Re-derive every place's bar category and 술자리 tag from its licence and name (data sync rule)."""
    from sqlalchemy import delete, insert, select, update

    from app.infra.db.models import Category, Place, PlaceRevision, PlaceSource, PlaceTag, Tag
    from app.infra.ingestion.bulk import reprice as reprice_mod
    from app.infra.ingestion.bulk import semas_store
    from app.infra.ingestion.bulk.common import load_json
    from app.infra.ingestion.bulk.price_prior import PricePrior

    report = Report()
    async with db.sessionmaker() as session:
        cats = {
            code: (cid, pm)
            for cid, code, pm in (
                await session.execute(select(Category.id, Category.code, Category.provider_mapping))
            ).all()
        }
        code_of = {cid: code for code, (cid, _) in cats.items()}
        tag_id = await session.scalar(select(Tag.id).where(Tag.name == DRINK_TAG))

        # 1. the drinking licence of each place (several licence rows: any drinking one wins)
        kinds: dict[int, str] = {}
        kind_col = PlaceSource.raw[KIND_KEY].as_string()
        stmt = (
            select(PlaceSource.place_id, kind_col)
            .where(PlaceSource.provider.in_(LICENCE_PROVIDERS), PlaceSource.place_id.is_not(None))
            .where(kind_col.in_(DRINK_KINDS))
        )
        for pid, kind in (await session.execute(stmt)).all():
            kinds.setdefault(pid, kind)

        # 2. where each place started (the first move remembered it)
        origins: dict[int, tuple[int, str]] = {}  # place → (revision id, origin code)
        revs = select(PlaceRevision.id, PlaceRevision.place_id, PlaceRevision.before).where(
            PlaceRevision.action == REVISION_ACTION, PlaceRevision.note == REVISION_NOTE
        )
        for rid, pid, before in (await session.execute(revs.order_by(PlaceRevision.id))).all():
            origin = _raw(before).get("category")
            if pid not in origins and isinstance(origin, str) and origin in cats:
                origins[pid] = (rid, origin)

        # 3. the places this rule speaks about: licensed to pour, already a bar, or moved before
        bar_ids = [cid for code, (cid, _) in cats.items() if _in(code, "bar")]
        wanted = set(kinds) | set(origins)
        rows: list[tuple[int, str, int]] = []
        stmt_bars = select(Place.id, Place.name, Place.category_id).where(Place.category_id.in_(bar_ids))
        rows += [(pid, name, cid) for pid, name, cid in (await session.execute(stmt_bars)).all()]
        seen_ids = {r[0] for r in rows}
        rest = sorted(wanted - seen_ids)
        for start in range(0, len(rest), 5_000):
            chunk = rest[start : start + 5_000]
            stmt_rest = select(Place.id, Place.name, Place.category_id).where(Place.id.in_(chunk))
            rows += [(pid, name, cid) for pid, name, cid in (await session.execute(stmt_rest)).all()]

        existing_tags: dict[int, str] = {}  # place → source of its 술자리 row
        if tag_id is not None:
            stmt_tags = select(PlaceTag.place_id, PlaceTag.source).where(PlaceTag.tag_id == tag_id)
            existing_tags = {pid: src for pid, src in (await session.execute(stmt_tags)).all()}

        moves: list[dict[str, Any]] = []
        new_revs: list[dict[str, Any]] = []
        rev_updates: list[dict[str, Any]] = []
        want_tag: set[int] = set()
        for pid, name, cid in rows:
            report.seen += 1
            current = code_of.get(cid, "")
            rev = origins.get(pid)
            origin = rev[1] if rev else current
            d = decide(origin, kinds.get(pid), name or "")
            if d.drinks:
                want_tag.add(pid)
            if d.category != current and d.category in cats:
                moves.append({"id": pid, "category_id": cats[d.category][0]})
                key = f"{current}→{d.category}"
                report.by_move[key] = report.by_move.get(key, 0) + 1
                if rev is None:
                    new_revs.append(
                        {
                            "place_id": pid,
                            "action": REVISION_ACTION,
                            "note": REVISION_NOTE,
                            "before": {"category": current},
                            "after": {"category": d.category},
                        }
                    )
                else:
                    rev_updates.append({"id": rev[0], "after": {"category": d.category}})
        report.moved = len(moves)
        for start in range(0, len(moves), BATCH):
            await session.execute(update(Place), moves[start : start + BATCH])
            await session.commit()
        for start in range(0, len(new_revs), BATCH):
            await session.execute(insert(PlaceRevision), new_revs[start : start + BATCH])
            await session.commit()
        for start in range(0, len(rev_updates), BATCH):
            await session.execute(update(PlaceRevision), rev_updates[start : start + BATCH])
            await session.commit()

        # 4. the 술자리 rows this rule owns (a row another source wrote is left alone)
        if tag_id is not None:
            add = [
                {"place_id": pid, "tag_id": tag_id, "weight": DRINK_TAG_WEIGHT, "source": TAG_SOURCE}
                for pid in sorted(want_tag)
                if pid not in existing_tags
            ]
            drop = sorted(p for p, src in existing_tags.items() if src == TAG_SOURCE and p not in want_tag)
            for start in range(0, len(add), BATCH):
                await session.execute(insert(PlaceTag), add[start : start + BATCH])
                await session.commit()
            for start in range(0, len(drop), BATCH):
                await session.execute(
                    delete(PlaceTag).where(
                        PlaceTag.tag_id == tag_id,
                        PlaceTag.source == TAG_SOURCE,
                        PlaceTag.place_id.in_(drop[start : start + BATCH]),
                    )
                )
                await session.commit()
            report.tagged, report.untagged = len(add), len(drop)

        # 5. a moved place whose price is a SEMAS estimate is priced as what it now is (bulk/reprice.py)
        moved_ids = [m["id"] for m in moves]
        if moved_ids:
            categories = semas_store.code_to_category((code, pm) for code, (_, pm) in cats.items())
            prior = PricePrior.from_data(load_json("price_prior.json"), load_json("regions_kr.json"))
            new_code = {m["id"]: code_of[m["category_id"]] for m in moves}
            prices: list[dict[str, Any]] = []
            for start in range(0, len(moved_ids), 5_000):
                chunk = moved_ids[start : start + 5_000]
                stmt_p = (
                    select(Place.id, Place.name, Place.price_per_person, PlaceSource.raw)
                    .join(PlaceSource, (PlaceSource.place_id == Place.id) & (PlaceSource.provider == "semas"))
                    .where(Place.id.in_(chunk), Place.price_is_estimated.is_(True), Place.is_free.is_(False))
                )
                for pid, name, price, raw in (await session.execute(stmt_p)).all():
                    value = reprice_mod.new_price(prior, categories, new_code[pid], _raw(raw), name or "")
                    if value is not None and value != price:
                        prices.append({"id": pid, "price_per_person": value})
            for start in range(0, len(prices), BATCH):
                await session.execute(update(Place), prices[start : start + BATCH])
                await session.commit()
            report.repriced = len(prices)
    log(report.line())
    return report
