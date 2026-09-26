"""Opening hours from the free text 한국관광공사 TourAPI writes (docs/55).

`detailIntro2` answers with sentences, not a structure: "09:00~18:00 (입장마감 17:00)", "매주 월요일 휴무",
"[1월~2월/11월~12월]09:00~17:00 [3월~5월]09:00~18:00", "연중무휴", "일출~일몰", "상시개방" … This module
turns them into seven days of (open, close) or says it cannot.

The rule is **conservative**: a wrong "open" sends someone to a locked museum at night, a missing value only
means the category's usual hours stay in use (data/hours/default_hours.json). So:

- text we do not fully understand → `ambiguous`, nothing is stored (the raw text is kept by the caller);
- several seasons → the narrowest day (latest opening, earliest closing), so it is right all year;
- "입장마감 16:00" → closing becomes last entry + 30 min, because the engine asks "is it open for at
  least 30 minutes after I arrive" — that makes 16:00 the last arrival it allows;
- closed days: weekly ones only. Holidays (설 · 추석 · 1월 1일) and monthly ones (매월 첫째 월요일) are not
  a weekday rule and are left out; a conditional clause ("공휴일인 경우 다음 날") is dropped.
- no word about closed days → the caller's default for the category (a museum keeps its Monday).
"""

from __future__ import annotations

import html
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field

ALL_DAYS: frozenset[int] = frozenset(range(7))
WEEKDAYS: frozenset[int] = frozenset(range(5))
WEEKEND: frozenset[int] = frozenset({5, 6})
DAY_CHARS = "월화수목금토일"
LAST_ENTRY_GRACE_MIN = 30

# ── normalising ───────────────────────────────────────────────────────────────────────────────────

_TILDES = str.maketrans(
    {"～": "~", "∼": "~", "〜": "~", "：": ":", "（": "(", "）": ")", "·": ",", "ㆍ": ","}
)
# HTML tags only: "<입장마감 17:00>" written in angle brackets is text
_TAG = re.compile(r"<\s*br\s*/?\s*>|</?\s*[a-z][a-z0-9]*(?:\s[^<>]{0,60})?\s*/?>", re.I)
_SPACES = re.compile(r"[ \t ]+")
_AMPM = re.compile(
    r"(오전|오후|낮|밤|저녁|새벽)\s*(\d{1,2})\s*(?::\s*(\d{2})|시(?:\s*(\d{1,2})\s*분|\s*반)?)"
)
_KO_TIME = re.compile(r"(?<![\d:])(\d{1,2})\s*시(?:\s*(\d{1,2})\s*분|\s*(반))?(?![간작])")
_DOT_TIME = re.compile(r"(?<![\d.])([01]?\d|2[0-4])\.([0-5]\d)(?![\d.])")
_HHMM = re.compile(r"(?<![\d:])([01]?\d|2[0-4])\s*:\s*([0-5]\d)(?![\d:])")
_DASH_RANGE = re.compile(r"(\d{1,2}:\d{2})\s*[-–—]\s*(\d{1,2}:\d{2})")


def normalize(text: str | None) -> str:
    """HTML entities and tags out, one kind of tilde, and every clock time as HH:MM."""
    if not text:
        return ""
    t = html.unescape(html.unescape(text))
    t = _TAG.sub("\n", t).translate(_TILDES)
    t = t.replace("\r", "\n")

    def ampm(m: re.Match[str]) -> str:
        h = int(m.group(2))
        minute = int(m.group(3) or m.group(4) or (30 if "반" in m.group(0) else 0))
        if m.group(1) in {"오후", "저녁", "밤"} and h < 12:
            h += 12
        return f"{h:02d}:{minute:02d}"

    t = _AMPM.sub(ampm, t)
    t = _KO_TIME.sub(lambda m: f"{int(m.group(1)):02d}:{int(m.group(2) or (30 if m.group(3) else 0)):02d}", t)
    t = _DOT_TIME.sub(lambda m: f"{int(m.group(1)):02d}:{m.group(2)}", t)
    t = _HHMM.sub(lambda m: f"{int(m.group(1)):02d}:{m.group(2)}", t)
    t = _DASH_RANGE.sub(r"\1~\2", t)
    t = _SPACES.sub(" ", t)
    return "\n".join(line.strip() for line in t.split("\n") if line.strip())


def _minutes(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def _hhmm(minutes: int) -> str:
    minutes %= 1440
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


# ── days of the week ──────────────────────────────────────────────────────────────────────────────

# a lone day letter: not glued to another syllable ("휴일", "일반", "일출", "금액") except its own 요일
_DAY = re.compile(
    r"(?<![가-힣\d])([월화수목금토일])(?:요일|욜)?(?![가-힣])|(?<![가-힣\d])([월화수목금토일])요일"
)
_DAY_RANGE = re.compile(
    r"(?<![가-힣\d])([월화수목금토일])(?:요일)?\s*~\s*([월화수목금토일])(?:요일)?(?![가-힣])"
)


def days_in(text: str) -> frozenset[int]:
    """Every weekday a phrase names: 평일 · 주말 · 매일 · 월~금 · 토,일 · 수요일 …"""
    found: set[int] = set()
    if "매일" in text or "연중" in text:
        found |= ALL_DAYS
    if "평일" in text or "주중" in text:
        found |= WEEKDAYS
    if "주말" in text:
        found |= WEEKEND
    rest = text
    for m in _DAY_RANGE.finditer(text):
        a, b = DAY_CHARS.index(m.group(1)), DAY_CHARS.index(m.group(2))
        span = range(a, b + 1) if a <= b else [*range(a, 7), *range(b + 1)]
        found |= set(span)
    rest = _DAY_RANGE.sub(" ", text)
    for m in _DAY.finditer(rest):
        found.add(DAY_CHARS.index(m.group(1) or m.group(2)))
    return frozenset(found)


# ── closed days (restdate) ────────────────────────────────────────────────────────────────────────

_NONE_WORDS = (
    "연중무휴",
    "연중 무휴",
    "무휴",
    "휴무없음",
    "휴무 없음",
    "휴관없음",
    "휴관 없음",
    "휴일없음",
    "휴일 없음",
    "쉬는날 없음",
    "쉬는 날 없음",
    "상시개방",
    "상시 개방",
    "연중개방",
    "연중 개방",
    "365일",
    "없음",
)
_HOLIDAY = re.compile(
    r"설날|설 ?연휴|설 ?당일|설,|설 |^설$|추석|명절|신정|구정|1월 ?1일|1/1|성탄|크리스마스|12월 ?25일|"
    r"공휴일|대체 ?휴일|연휴|당일|전날|다음 ?날|익일|선거일|근로자의 ?날|어린이날|노동절|부처님|국경일|"
    r"삼일절|3[.,]1절|광복절|기념일|지정|정하는|인정하는|\d{1,2}월 ?\d{1,2}일|우천|혹서기|혹한기|국정|탄강"
)
_MONTHLY = re.compile(r"매월|격주|첫 ?째|둘 ?째|셋 ?째|넷 ?째|다섯 ?째|마지막|번 ?째|[1-5] ?(?:째|주)")
# a footnote that says the days are not fixed makes the whole answer unreliable
_VARIES = re.compile(r"상이|다름|다릅|달라|변동|유동")
_FOOTNOTE = re.compile(r"※[^\n]*|\(\s*단\s*[,.]?[^()]*\)|(?:(?<=\s)|^)단\s*[,.][^\n]*")
_CONDITIONAL_PAREN = re.compile(r"\([^()]*(?:경우|겹치|제외|개관|개방|휴관|휴무)[^()]*\)")
_CONDITIONAL = re.compile(r"경우|겹치|인 때|일 때|이면|해당|제외|단,|단 |변동|사정|별도|문의|홈페이지|공지")
_SEASONAL = re.compile(r"\d{1,2} ?월|하절기|동절기|하계|동계|여름|겨울|성수기|비수기|기간")
_CLOSED_WORDS = re.compile(r"휴무|휴관|휴장|휴일|쉼|쉽니다|정기 ?휴|휴궁|휴원|닫|문 ?닫")
_CLOSED_DAY_NAMED = re.compile(r"(?<![가-힣\d])[월화수목금토]요일|주말|평일")
_CLAUSE_SPLIT = re.compile(r"[\n,;/]|(?<=[다요])\.|\)|\(|\[|\]|※|\*|- ")


@dataclass(frozen=True, slots=True)
class ClosedDays:
    """`days` = weekly closed days. `known` False = the text said nothing we can use (caller's default)."""

    days: frozenset[int] = frozenset()
    known: bool = False
    ambiguous: str | None = None
    notes: tuple[str, ...] = ()


def parse_restdate(text: str | None) -> ClosedDays:
    t = normalize(text)
    if not t:
        return ClosedDays()
    compact = t.replace(" ", "")
    if _VARIES.search(t):
        return ClosedDays(ambiguous=f"restdate varies: {compact[:40]}")
    # "(단, 월요일이 공휴일인 경우 그 다음날)", "※ 단, …": exceptions to a rule, not a rule
    t = _CONDITIONAL_PAREN.sub(" ", _FOOTNOTE.sub(" ", t))
    if not t.strip():
        return ClosedDays(notes=("footnote only",))
    closed: set[int] = set()
    notes: list[str] = []
    understood = False
    for raw in _CLAUSE_SPLIT.split(t):
        clause = raw.strip(" .:-~")
        if not clause:
            continue
        c = clause.replace(" ", "")
        if any(w.replace(" ", "") in c for w in _NONE_WORDS) and not _CLOSED_DAY_NAMED.search(clause):
            understood = True
            continue
        if _CONDITIONAL.search(clause):
            notes.append("conditional")
            understood = True
            continue
        days = days_in(clause)
        if _MONTHLY.search(clause) and not re.search(r"매주", clause):
            notes.append("monthly")
            understood = True
            continue
        if days and _SEASONAL.search(clause) and not re.search(r"매주", clause):
            closed |= days  # "동절기 월요일 휴무": closed on that day part of the year → closed (safe side)
            notes.append("seasonal")
            understood = True
            continue
        if days:
            if days == ALL_DAYS and not _CLOSED_WORDS.search(clause):
                continue  # "연중" / "매일" alone says nothing about a closed day
            closed |= days
            understood = True
            continue
        if _HOLIDAY.search(clause):
            notes.append("holidays")
            understood = True
            continue
        if re.fullmatch(r"(매년|매월)?(\d{1,2}월)+", c):
            continue  # "매년 3월, 6월, 9월, 12월 첫 번째 월요일" split at its commas
        if re.fullmatch(
            r"(매주|정기|휴무|휴관|휴장|휴실|휴궁|휴원|휴일|쉬는날|없음|운영|개방|기타|및|일|날|정기휴실|정기휴관)*",
            c,
        ):
            continue  # connective words / a "[휴관일]" label only
        return ClosedDays(ambiguous=f"restdate: {clause[:40]}")
    if not understood and not closed:
        return ClosedDays(ambiguous=f"restdate: {compact[:40]}")
    return ClosedDays(frozenset(closed), known=True, notes=tuple(dict.fromkeys(notes)))


# ── hours (usetime) ───────────────────────────────────────────────────────────────────────────────

_RANGE = re.compile(r"(\d{2}:\d{2})\s*(?:분)?\s*(?:부터)?\s*~\s*(?:익일|다음날|새벽)?\s*(\d{2}:\d{2})")
_ENTRY = r"(?:마지막 ?(?:입장|주문)|입장|매표|발권|입장권 ?판매|관람권 ?판매|티켓 ?판매|입실)"
_LAST_ENTRY = re.compile(
    rf"{_ENTRY}\s*(?:마감|종료|시간 ?마감)?\s*(?:시간)?\s*[:은는]?\s*(?:~\s*)?(\d{{2}}:\d{{2}})(?:\s*까지)?"
    rf"|(\d{{2}}:\d{{2}})\s*(?:까지)?\s*{_ENTRY}\s*(?:마감|가능|종료)?"
)
# "관람 종료 1시간 전 입장 마감", "※ 1시간 전 입장 마감", "종료 40분 전까지 입장"
_LAST_ENTRY_BEFORE = re.compile(
    rf"(\d{{1,3}})\s*(분|시간)\s*전\s*(?:까지)?\s*(?:에)?\s*{_ENTRY}"
    rf"|{_ENTRY}\s*(?:마감|시간)?\s*[:은는]?\s*(?:관람|운영)?\s*(?:종료|마감)\s*(\d{{1,3}})\s*(분|시간)\s*전"
)
# the leading part of the text after a range that still belongs to it: "(입장마감 17:00)", "- 입장 마감 17:00"
_RANGE_TAIL = re.compile(
    rf"\s*(?:\([^()]*\)|[-,/]?\s*{_ENTRY}\s*(?:마감|종료)?\s*[:은는]?\s*\d{{2}}:\d{{2}}(?:\s*까지)?)?"
)
_BREAK_LABEL = re.compile(r"(휴게|점심|준비|브레이크|정비|청소)\s*(시간)?\s*[:은는]?\s*$")
_BREAK_AFTER = re.compile(r"\s*(휴게|점심|준비|브레이크)")  # "( 12:00~13:00 점심시간 )"
_CLOCK = re.compile(r"\d{2}:\d{2}")
_BOILERPLATE = re.compile(
    r"※?\s*(?:자세한|상세한|기타 ?자세한)\s*(?:사항|내용|이용 ?시간|운영 ?시간)?\s*(?:은|는)?\s*"
    r"(?:홈페이지|전화|유선)?\s*(?:참조|문의|확인)\s*(?:및\s*(?:전화)?\s*문의)?\s*(?:요망|바람|바랍니다|하세요|필수)?"
)
_ALWAYS = re.compile(
    r"24 ?시간|상시|연중 ?개방|연중 ?무휴 ?개방|제한 ?없음|자유 ?관람|자유 ?이용|자유롭게|항시|언제든|"
    r"00:00 ?~ ?24:00"
)
# "always" comes in two kinds (backlog 9, docs/55). "상시 개방" / "24시간" / "자유 관람" say the gate
# never shuts — a park, a square, a bridge, a 한옥마을. "상시운영" / "상시 영업" / "연중 운영" is a shop
# saying it is a standing shop and not a pop-up (영카이브 성수점, 1층: "상시운영", sent to on a
# night date at 23:04); it says nothing about the hour its door closes.
_ALWAYS_OPEN_WORDS = re.compile(
    r"개방|24 ?시간|제한 ?없음|자유 ?관람|자유 ?이용|자유롭게|언제든|00:00 ?~ ?24:00"
)
_STANDING_SHOP = re.compile(r"(?:상시|항시|연중)\s*(?:운영|영업|오픈|open)", re.I)
# a place that has no door: its "상시 운영" can only mean the whole day
OPEN_SPACE_CATEGORIES = ("attraction.park", "attraction.street", "nightview.riverside")
_OPEN_SPACE_NAME = re.compile(
    r"공원|광장|거리|골목|마을|다리|대교|해변|해수욕장|해안|산책로|둘레길|숲|호수|강변|천변|성곽|유원지|관광특구|"
    r"(?:길|교|항|포구|천|성|터)(?:\s*\(|$)"
)
# inside a building (a museum, a shop, a café): the building has a door even when TourAPI writes
# "상시 개방" (김만덕기념관 — a museum, 09:00~18:00 in fact); only an explicit "24시간" is believed there
INDOOR_CATEGORIES = (
    "culture.museum",
    "culture.gallery",
    "culture.exhibition",
    "culture.bookstore",
    "food",
    "cafe",
    "dessert",
    "bar",
    "activity",
    "stay",
    "attraction.market",
)
_EXPLICIT_24H = re.compile(r"24 ?시간|00:00 ?~ ?24:00")


def is_open_space(place_name: str = "", category_code: str = "") -> bool:
    """A park, a street, a square, a bridge, a village — somewhere with no door to lock."""
    if category_code and category_code.startswith(OPEN_SPACE_CATEGORIES):
        return True
    return bool(place_name and _OPEN_SPACE_NAME.search(place_name.strip()))


def _is_indoor(category_code: str) -> bool:
    return bool(category_code) and any(
        category_code == c or category_code.startswith(c + ".") for c in INDOOR_CATEGORIES
    )


def always_open_doubt(text: str, *, place_name: str = "", category_code: str = "") -> str | None:
    """Why an "always" in the hours text must not be read as 24 h here, or None when it can be."""
    if _is_indoor(category_code) and not _EXPLICIT_24H.search(text):
        return f"indoor place ({category_code}) said always open"
    if (
        _STANDING_SHOP.search(text)
        and not _ALWAYS_OPEN_WORDS.search(text)
        and not is_open_space(place_name, category_code)
    ):
        return "standing shop: '상시운영' is not 24 h"
    return None


_SUN = re.compile(r"일출|일몰|해 ?뜰|해 ?질|해넘이|해돋이|해가")
_ASK = re.compile(r"문의|변동|상이|다름|다릅|달라|홈페이지|사전 ?예약|예약제|공지|확인|유동|협의|별도|회차")
_SEASON_LABEL = re.compile(
    r"\d{1,2} ?월|하절기|동절기|하계|동계|여름|겨울|봄|가을|춘추|성수기|비수기|춘하추동|절기"
)
_NIGHT = re.compile(r"야간|야경")
# words that label a range but do not change what it means
_FILLER = re.compile(
    r"운영 ?시간|이용 ?시간|관람 ?시간|개방 ?시간|영업 ?시간|개장 ?시간|운영|이용|관람|개방|영업|개장|"
    r"시간|매일|매주|매년|연중|평일|주말|주중|요일|법정|공휴일|휴일|및|기준|부터|까지|오전|오후|전시|전시실|"
    r"실내|본관|상설|일반|정상|정규|기본|시설|전체|연장|단축|기간|중|중에는|에는|는|은|:"
)


@dataclass(slots=True)
class _Range:
    open_min: int
    close_min: int
    before: str  # the label written in front of it
    last_entry: int | None = None
    after: str = ""  # the text right behind it ("12:00~13:00 점심시간")


@dataclass(frozen=True, slots=True)
class DayHours:
    dow: int
    open_time: str | None = None
    close_time: str | None = None
    is_closed: bool = False
    break_start: str | None = None
    break_end: str | None = None


@dataclass(frozen=True, slots=True)
class ParsedHours:
    """`status`: ok (seven days in `days`) · ambiguous (store nothing) · empty (no text at all)."""

    status: str
    days: tuple[DayHours, ...] = ()
    reason: str | None = None
    closed_from: str | None = None  # restdate | usetime | default | none
    notes: tuple[str, ...] = field(default_factory=tuple)

    @property
    def ok(self) -> bool:
        return self.status == "ok"


def _ambiguous(reason: str) -> ParsedHours:
    return ParsedHours("ambiguous", reason=reason)


_CLOSED_IN_USETIME = re.compile(
    r"(?:매주\s*)?([월화수목금토일 ,~요일및]+?)\s*(?:은|는)?\s*(?:정기\s*)?(?:휴관|휴무|휴장|휴궁|쉼|쉽니다)"
)


def _closed_in_usetime(t: str) -> tuple[frozenset[int], str]:
    """ "(월요일 휴관)" written inside the hours text → those days, and the text without that phrase."""
    days: set[int] = set()
    out = t
    for m in _CLOSED_IN_USETIME.finditer(t):
        found = days_in(m.group(1))
        if found and found != ALL_DAYS:
            days |= found
            out = out.replace(m.group(0), " ")
    return frozenset(days), out


def _last_entry(span: str) -> int | None:
    m = _LAST_ENTRY.search(span)
    return _minutes(m.group(1) or m.group(2)) if m else None


def _entry_offset(t: str) -> int | None:
    """Minutes before closing that entry stops, when the text says it once for every range."""
    m = _LAST_ENTRY_BEFORE.search(t)
    if not m:
        return None
    n, unit = (m.group(1), m.group(2)) if m.group(1) else (m.group(3), m.group(4))
    return int(n) * (60 if unit == "시간" else 1)


def _ranges(t: str) -> list[_Range]:
    found = list(_RANGE.finditer(t))
    out: list[_Range] = []
    label_from = 0
    for i, m in enumerate(found):
        o, c = _minutes(m.group(1)), _minutes(m.group(2))
        if c <= o:
            c += 1440  # past midnight
        nxt = found[i + 1].start() if i + 1 < len(found) else len(t)
        after = t[m.end() : nxt]
        # a note right after a range belongs to it ("(입장마감 17:00)"); what follows labels the next one
        m_tail = _RANGE_TAIL.match(after)
        tail = m_tail.group(0) if m_tail else ""
        before = t[label_from : m.start()]
        out.append(_Range(o, c, before, _last_entry(tail), after[:12]))
        label_from = m.end() + len(tail)
    return out


def _stray_clock(t: str) -> bool:
    """A clock time outside every range and last-entry note ("18:00부터 비개방", "마지막 주문 20:00")
    means the text says something about the hours we did not understand."""
    covered = [m.span() for m in _RANGE.finditer(t)] + [m.span() for m in _LAST_ENTRY.finditer(t)]
    return any(not any(a <= m.start() < b for a, b in covered) for m in _CLOCK.finditer(t))


def _is_entry_range(r: _Range) -> bool:
    return bool(re.search(rf"{_ENTRY}\s*(시간|가능)?\s*[:은는]?$", r.before.strip(" ([-")))


def _is_break_range(r: _Range) -> bool:
    return bool(_BREAK_LABEL.search(r.before.strip(" ([-")) or _BREAK_AFTER.match(r.after))


def _label_rest(label: str) -> str:
    """What is left of a label after days, seasons and filler words: a facility name, or nothing."""
    rest = _SEASON_LABEL.sub(" ", label)
    rest = _DAY_RANGE.sub(" ", rest)
    rest = _DAY.sub(" ", rest)
    rest = _FILLER.sub(" ", rest)
    rest = re.sub(r"[\d~,./()\[\]\-:·※*<>+&]", " ", rest)
    return " ".join(w for w in rest.split() if len(w) >= 2)


def parse_usetime(
    usetime: str | None,
    restdate: str | None,
    *,
    default_closed: Iterable[int] = (),
    place_name: str = "",
    category_code: str = "",
) -> ParsedHours:
    """Seven days of hours from TourAPI `usetime` + `restdate`, or `ambiguous` with the reason.
    `place_name` / `category_code` only decide what an "always" means (a park vs. a shop)."""
    t = normalize(usetime)
    rest = parse_restdate(restdate)
    if not t:
        return ParsedHours("empty", reason="no usetime")
    if rest.ambiguous:
        return _ambiguous(rest.ambiguous)
    t = _BOILERPLATE.sub(" ", t)  # "※ 자세한 사항은 전화문의 요망" sits under nearly every entry
    if _ASK.search(t):
        return _ambiguous("usetime says it varies / ask")
    if _SUN.search(t):
        return _ambiguous("sunrise / sunset")
    closed_u, t = _closed_in_usetime(t)
    offset = _entry_offset(t)
    ranges = _ranges(t)
    always = bool(_ALWAYS.search(t))
    if always and not ranges:
        doubt = always_open_doubt(t, place_name=place_name, category_code=category_code)
        if doubt:
            return _ambiguous(doubt)
    if always and any(r.close_min - r.open_min < 1440 for r in ranges):
        return _ambiguous("always open and a time range")
    if not ranges and not always:
        return _ambiguous("no time range")
    if _stray_clock(t):
        return _ambiguous("a time that is not a range")
    if _NIGHT.search(t) and len(ranges) > 1:
        return _ambiguous("night opening")

    notes: list[str] = []
    per_day: dict[int, tuple[int, int]] = {}
    breaks: list[_Range] = []
    if always:
        per_day = {d: (0, 1440) for d in ALL_DAYS}
        notes.append("always")
    else:
        breaks = [r for r in ranges if _is_break_range(r)]
        ranges = [r for r in ranges if not _is_break_range(r)]
        entry = [r for r in ranges if _is_entry_range(r)]
        main = [r for r in ranges if not _is_entry_range(r)]
        if not main:
            main, entry = entry, []
        if len(entry) > 1 or len(breaks) > 1:
            return _ambiguous("several entry or break ranges")
        labels = [
            (r, days_in(r.before), bool(_SEASON_LABEL.search(r.before)), _label_rest(r.before)) for r in main
        ]
        if any(rest_ for *_, rest_ in labels):
            return _ambiguous(f"label: {next(rest_ for *_, rest_ in labels if rest_)[:30]}")
        seasonal = any(s for _, _, s, _ in labels)
        by_days = [d for _, d, _, _ in labels if d and d != ALL_DAYS]
        if seasonal and by_days:
            return _ambiguous("seasons and weekdays together")
        if seasonal and len(main) == 1:
            return _ambiguous("one season only")  # "매년 6월~9월 09:00~18:00": the rest of the year?
        if len(main) > 1 and not seasonal and len(by_days) < len(main) - 1:
            return _ambiguous("several ranges without labels")

        def effective(r: _Range) -> tuple[int, int]:
            close = r.close_min
            last = r.last_entry
            if last is None and entry:
                last = entry[0].close_min
            if last is None and offset is not None:
                last = close - offset
            if last is not None:
                if last <= r.open_min:
                    last += 1440
                if r.open_min < last <= close:
                    close = min(close, last + LAST_ENTRY_GRACE_MIN)
            return r.open_min, close

        if seasonal or len(main) == 1:
            spans = [effective(r) for r in main]
            o, c = max(s[0] for s in spans), min(s[1] for s in spans)
            if c - o < 60:
                return _ambiguous("seasons do not overlap")
            per_day = {d: (o, c) for d in ALL_DAYS}
            if seasonal:
                notes.append("narrowest season")
        else:
            base = [r for r, d, _, _ in labels if not d or d == ALL_DAYS]
            if len(base) > 1:
                return _ambiguous("several unlabelled ranges")
            # the broader label first, so "수요일 11:00~21:00" can refine "화요일~일요일 11:00~19:00"
            named = sorted(((r, d) for r, d, _, _ in labels if d and d != ALL_DAYS), key=lambda x: -len(x[1]))
            set_by: dict[int, int] = {}
            for r, d in named:
                for day in d:
                    if day in set_by and set_by[day] <= len(d):
                        return _ambiguous("a day named twice")
                    per_day[day], set_by[day] = effective(r), len(d)
            if base:
                for day in ALL_DAYS - per_day.keys():
                    per_day[day] = effective(base[0])
            notes.append("by weekday")

    if closed_u:
        closed, closed_from = set(closed_u) | set(rest.days), "usetime"
    elif rest.known:
        closed, closed_from = set(rest.days), "restdate" if rest.days else "none"
    elif always:
        closed, closed_from = set(), "none"  # "상시개방" is every day
    else:
        closed, closed_from = set(default_closed), "default"
    missing = ALL_DAYS - per_day.keys() - closed
    if missing:
        return _ambiguous("days without hours: " + ",".join(DAY_CHARS[d] for d in sorted(missing)))
    if closed >= ALL_DAYS:
        return _ambiguous("closed every day")

    def row_for(d: int) -> DayHours:
        if d in closed:
            return DayHours(d, is_closed=True)
        o, c = per_day[d]
        brk = breaks[0] if breaks and o < breaks[0].open_min < breaks[0].close_min < c else None
        return DayHours(
            d,
            _hhmm(o),
            _hhmm(c if c - o < 1440 else 0),
            break_start=_hhmm(brk.open_min) if brk else None,
            break_end=_hhmm(brk.close_min) if brk else None,
        )

    if breaks:
        notes.append("break")
    return ParsedHours(
        "ok",
        tuple(row_for(d) for d in sorted(ALL_DAYS)),
        closed_from=closed_from,
        notes=tuple(notes + list(rest.notes)),
    )


# ── TourAPI field names per content type ─────────────────────────────────────────────────────────

FIELDS: dict[str, tuple[str, str]] = {
    "12": ("usetime", "restdate"),  # 관광지
    "14": ("usetimeculture", "restdateculture"),  # 문화시설
    "15": ("playtime", ""),  # 행사 (not loaded here)
    "28": ("usetimeleports", "restdateleports"),  # 레포츠
    "38": ("opentime", "restdateshopping"),  # 쇼핑
    "39": ("opentimefood", "restdatefood"),  # 음식점
}


def hours_fields(content_type: str, item: Mapping[str, object]) -> tuple[str, str]:
    use_key, rest_key = FIELDS.get(str(content_type), ("usetime", "restdate"))
    return str(item.get(use_key) or ""), str(item.get(rest_key) or "") if rest_key else ""


def parse_item(
    content_type: str,
    item: Mapping[str, object],
    *,
    default_closed: Sequence[int] = (),
    place_name: str = "",
    category_code: str = "",
) -> ParsedHours:
    usetime, restdate = hours_fields(content_type, item)
    return parse_usetime(
        usetime, restdate, default_closed=default_closed, place_name=place_name, category_code=category_code
    )
