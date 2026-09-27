"""믿을 이유 한 줄 (docs/59 #15 · docs/61 우선 3): why this place can be trusted, from stored fields only.

docs/61 found the weakest link of a course is the single place — of 23 food and drink stops, 7 had a
photo, 1 a real price, 0 ratings. What we *do* hold is a handful of checkable facts; this module turns
them into one short line, most convincing first, and never says anything the data does not:

1. 공적 표식 — 백년가게 (중소벤처기업부) · 모범음식점 (지자체) · 착한가격업소 (행정안전부) · 관광공사 소개
2. 영업 연수 — the licence date (인허가일자): "1992년부터 34년째 영업"
3. 실제 메뉴 가격 — a menu row we hold (착한가격업소 조사): "칼국수 9,000원"
4. 동네 명물 — the draw it matches (data/regions/draws.json): "망원동 명물 칼국수"
5. 티맵 실측 — a measured top-30 destination of its district: "마포구 티맵 목적지 12위"
6. 사진 — the number of checked photos we show

Nothing is scored here and nothing is guessed: no "인기 많은", no ratings, no reviews. A place with none
of these gets no line at all (the card then leads with its Kakao place page instead). Every fact names the
stored field it was read from (`TrustFact.field`), and `grounded` re-checks a line against those fields —
the scorecard's trust_invented_rate is that check over every stop of the sample.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import Literal

from app.domain.models import PlaceCandidate

TrustKind = Literal["designated", "long_run", "menu_price", "draw", "visited", "photos"]

LINE_MAX = 40  # the card's one line, same as reason_short
MIN_YEARS = 5  # "2023년부터 3년째" says little; five years and up is a track record
VISIT_TOP_RANK = 30  # data/bulk/visit_hubs.json › top_rank — the same cut as the "티맵 인기 목적지" tag
# words that would be claims we cannot back (no reviews, no ratings, no popularity by guess)
BANNED_WORDS = ("인기", "맛집", "별점", "평점", "후기", "리뷰", "유명", "핫플", "추천")

# designation tags (place_tag, written by ingest-bulk marks / derived by tag_rules) and provider rows
# (place_source) → (label, who says so); strongest first
DESIGNATIONS: tuple[tuple[str, str, str], ...] = (
    # (tag or provider, card text, source)
    ("백년가게", "중기부 지정 백년가게", "중소벤처기업부 백년가게 지정"),
    ("모범음식점", "지자체 지정 모범음식점", "지방자치단체 모범음식점 지정"),
    ("goodprice", "착한가격업소", "행정안전부 · 지자체 착한가격업소 지정"),
    ("관광공사 소개", "관광공사 관광정보에 실린 곳", "한국관광공사 관광정보(TourAPI)"),
)
PROVIDER_ALIASES = {"centurystore": "백년가게", "model_restaurant": "모범음식점", "tourapi": "관광공사 소개"}
MENU_SOURCES = {"goodprice": "행정안전부 착한가격업소 조사 가격"}


@dataclass(frozen=True, slots=True)
class TrustFacts:
    """What the database holds about a place beyond the candidate row (read per course, load_trust_facts)."""

    providers: frozenset[str] = frozenset()  # place_source.provider rows attached to the place
    licence_on: date | None = None  # place_source(lic_*).raw › 인허가일자, the earliest
    visit_rank: int | None = None  # place_source(tmap_hub).raw › rank
    visit_area: str | None = None  # › district
    visit_month: str | None = None  # › month, "202608"
    menu_name: str | None = None  # menu_item: the signature row, else the cheapest
    menu_price: int | None = None
    menu_source: str | None = None
    photos: int = 0  # distinct showable photos (place.images + thumbnail_url)


@dataclass(frozen=True, slots=True)
class TrustFact:
    kind: TrustKind
    text: str
    source: str
    field: (
        str  # the stored field it reads — "place_tag:모범음식점", "place_source:lic_restaurant.인허가일자" …
    )


@dataclass(frozen=True, slots=True)
class TrustLine:
    text: str  # the card's line: the strongest fact, and a second when both fit in LINE_MAX
    kind: TrustKind
    source: str
    facts: tuple[TrustFact, ...] = field(default_factory=tuple)


def _designations(place: PlaceCandidate, facts: TrustFacts) -> list[TrustFact]:
    out = []
    for key, text, source in DESIGNATIONS:
        if place.tags.get(key):
            out.append(TrustFact("designated", text, source, f"place_tag:{key}"))
        elif (
            row := next((p for p in sorted(facts.providers) if PROVIDER_ALIASES.get(p, p) == key), None)
        ) is not None:
            out.append(TrustFact("designated", text, source, f"place_source:{row}"))
    return out


def trust_facts(
    place: PlaceCandidate,
    facts: TrustFacts | None,
    *,
    today: date,
    area: str | None = None,
    draw_word: str | None = None,
    draw_sight: bool = False,
) -> list[TrustFact]:
    """Every checkable fact about the place, most convincing first. `draw_word`: the neighbourhood draw its
    sign matches (only a draws.json word — a specialty guessed from sign statistics is not a fact about it);
    `draw_sight`: the place is one of the sights people come to the neighbourhood for (draws.json › see);
    `area`: the neighbourhood's name for that line."""
    if place.is_event:
        return []
    facts = facts or TrustFacts()
    out = _designations(place, facts)
    if facts.licence_on is not None and 1900 < facts.licence_on.year <= today.year:
        years = today.year - facts.licence_on.year
        if years >= MIN_YEARS:
            out.append(
                TrustFact(
                    "long_run",
                    f"{facts.licence_on.year}년부터 {years}년째 영업",
                    "지자체 인허가(영업 신고) 기록",
                    "place_source:lic.인허가일자",
                )
            )
    # a menu called "인기세트" would put a claim in our mouth
    menu_ok = facts.menu_name and not any(w in facts.menu_name for w in BANNED_WORDS)
    if menu_ok and facts.menu_price and facts.menu_price > 0:
        out.append(
            TrustFact(
                "menu_price",
                f"{facts.menu_name} {facts.menu_price:,}원",
                MENU_SOURCES.get(facts.menu_source or "", "조사된 메뉴판 가격"),
                "menu_item:price",
            )
        )
    if draw_word:
        out.append(
            TrustFact(
                "draw",
                f"{area} 명물 {draw_word}" if area else f"이 동네 명물 {draw_word}",
                "그 동네에 오는 이유 목록(내가짠데이 조사)",
                "draws.json:eat",
            )
        )
    elif draw_sight:
        out.append(
            TrustFact(
                "draw",
                f"{area} 대표 볼거리" if area else "이 동네 대표 볼거리",
                "그 동네에 오는 이유 목록(내가짠데이 조사)",
                "draws.json:see",
            )
        )
    if facts.visit_rank is not None and 1 <= facts.visit_rank <= VISIT_TOP_RANK and facts.visit_area:
        m = facts.visit_month or ""
        when = f" ({m[:4]}년 {int(m[4:6])}월)" if len(m) == 6 and m.isdigit() else ""
        area_short = facts.visit_area.split()[-1]
        out.append(
            TrustFact(
                "visited",
                f"{area_short} 티맵 목적지 {facts.visit_rank}위",
                f"티맵 내비게이션 목적지 실측{when}",
                "place_source:tmap_hub.rank",
            )
        )
    if facts.photos > 0:
        out.append(
            TrustFact("photos", f"확인된 사진 {facts.photos}장", "장소와 맞춰 본 사진", "place.images")
        )
    return out


def trust_line(found: Sequence[TrustFact]) -> TrustLine | None:
    """One line: the strongest fact, plus the next when both fit (a photo count never rides along)."""
    if not found:
        return None
    first = found[0]
    text = first.text
    nxt = next((f for f in found[1:] if f.kind != first.kind and f.kind != "photos"), None)
    if nxt is not None and len(text) + 3 + len(nxt.text) <= LINE_MAX:
        text = f"{text} · {nxt.text}"
    if len(text) > LINE_MAX:
        text = text[: LINE_MAX - 1] + "…"
    return TrustLine(text=text, kind=first.kind, source=first.source, facts=tuple(found))


# ── the invented-fact check (docs/58 trust_invented_rate) ──────────────────────────────────────────────

_NUM = re.compile(r"\d[\d,]*")


def evidence_of(
    place: PlaceCandidate,
    facts: TrustFacts | None,
    *,
    draw_word: str | None = None,
    draw_sight: bool = False,
    area: str | None = None,
) -> dict[str, str]:
    """The stored values a trust line may read, as plain strings — kept on the scorecard's record."""
    facts = facts or TrustFacts()
    ev: dict[str, str] = {"region.name": area} if area else {}
    for tag, w in place.tags.items():
        if w:
            ev[f"place_tag:{tag}"] = tag
    for p in facts.providers:
        ev[f"place_source:{p}"] = PROVIDER_ALIASES.get(p, p)
    if facts.licence_on is not None:
        ev["place_source:lic.인허가일자"] = facts.licence_on.isoformat()
    if facts.menu_name and facts.menu_price:
        ev["menu_item:price"] = f"{facts.menu_name} {facts.menu_price}"
    if draw_word:
        ev["draws.json:eat"] = draw_word
    elif draw_sight:
        ev["draws.json:see"] = place.name
    if facts.visit_rank is not None:
        ev["place_source:tmap_hub.rank"] = f"{facts.visit_rank} {facts.visit_area or ''}"
    if facts.photos:
        ev["place.images"] = str(facts.photos)
    return ev


def grounded(line: TrustLine | None, evidence: Mapping[str, str], *, today: date) -> bool:
    """True when every fact of the line reads a field the place really has, every number it prints is in that
    field (or is the years since the licence year), and no claim word we cannot back appears."""
    if line is None:
        return True
    if any(w in line.text for w in BANNED_WORDS):
        return False
    for f in line.facts:
        if any(w in f.text for w in BANNED_WORDS):
            return False
        value = evidence.get(f.field)
        if value is None:
            return False
        stored = {n.replace(",", "") for n in _NUM.findall(value)}
        if f.kind == "long_run":
            year = int(value[:4])
            stored |= {str(year), str(today.year - year)}
        if f.kind == "draw":  # "익선동·종로3가 명물 빈대떡": the neighbourhood's own name may carry a number
            stored |= set(_NUM.findall(evidence.get("region.name", "")))
        for n in _NUM.findall(f.text):
            if n.replace(",", "") not in stored:
                return False
        if f.kind == "designated" and f.text not in {t for k, t, _s in DESIGNATIONS if k == value}:
            return False
        if f.field in ("draws.json:eat", "menu_item:price") and value.split()[0] not in f.text:
            return False
    # the card line is one fact, or two joined, in the facts' own words (cut with "…" when too long)
    made = {f.text for f in line.facts} | {f"{a.text} · {b.text}" for a in line.facts for b in line.facts}
    if line.text in made:
        return True
    return line.text.endswith("…") and any(m.startswith(line.text[:-1]) for m in made)


def for_place(
    place: PlaceCandidate, facts: TrustFacts | None, *, today: date, area: str | None
) -> tuple[TrustLine | None, dict[str, str]]:
    """The line a stop shows (API and scorecard alike) and the stored values it may read."""
    draw_word = place.local_word if place.local_draw else None
    draw_sight = place.local_draw and not place.local_word
    found = trust_facts(place, facts, today=today, area=area, draw_word=draw_word, draw_sight=draw_sight)
    evidence = evidence_of(place, facts, draw_word=draw_word, draw_sight=draw_sight, area=area)
    return trust_line(found), evidence
