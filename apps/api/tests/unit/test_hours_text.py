"""docs/55: TourAPI 자유 문장 영업시간 → 일주일 시간표. 모두 실제 detailIntro2 응답(2026-09-26)에서 가져온 문장이다.

규칙: 애매하면 저장하지 않는다(ambiguous). 틀린 '열림'은 밤에 닫힌 박물관으로 사람을 보내고, 빈 값은 업종 상식선을
그대로 쓸 뿐이다.
"""

from __future__ import annotations

import pytest

from app.infra.ingestion.hours_text import (
    ParsedHours,
    days_in,
    normalize,
    parse_item,
    parse_restdate,
    parse_usetime,
)

MON, TUE, WED, THU, FRI, SAT, SUN = range(7)


def week(p: ParsedHours) -> list[str]:
    """One string per day: "휴" or "HH:MM-HH:MM" (+ "/bHH:MM-HH:MM" for a break)."""
    assert p.ok, p.reason
    out = []
    for d in p.days:
        if d.is_closed:
            out.append("휴")
        else:
            brk = f"/b{d.break_start}-{d.break_end}" if d.break_start else ""
            out.append(f"{d.open_time}-{d.close_time}{brk}")
    return out


def same(value: str, *, closed: tuple[int, ...] = ()) -> list[str]:
    return ["휴" if d in closed else value for d in range(7)]


# ── normalising ───────────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("09:30∼23:00", "09:30~23:00"),
        ("10시~18시", "10:00~18:00"),
        ("오전 9시 ~ 오후 6시 30분", "09:00 ~ 18:30"),
        ("9:00~18:00", "09:00~18:00"),
        ("10:00-18:00", "10:00~18:00"),
        ("평일 10:00~20:00<br>주말 10:00~21:00", "평일 10:00~20:00\n주말 10:00~21:00"),
        ("09:00~18:00 &lt;입장마감 17:00&gt;", "09:00~18:00 <입장마감 17:00>"),
    ],
)
def test_normalize(raw: str, expected: str) -> None:
    assert normalize(raw) == expected


@pytest.mark.parametrize(
    ("text", "days"),
    [
        ("평일", {MON, TUE, WED, THU, FRI}),
        ("주말 및 공휴일", {SAT, SUN}),
        ("월요일~화요일 / 목요일~금요일 / 일요일", {MON, TUE, THU, FRI, SUN}),
        ("수,토", {WED, SAT}),
        ("일~금", {SUN, MON, TUE, WED, THU, FRI}),
        ("[1월~2월/11월~12월]", set()),  # months, not Mondays
        ("휴일 일반 일출", set()),  # 일 glued to another syllable is not Sunday
    ],
)
def test_days_in(text: str, days: set[int]) -> None:
    assert days_in(text) == days


# ── closed days ───────────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("text", "closed"),
    [
        ("매주 월요일 휴무", {MON}),
        ("연중무휴", set()),
        ("매주 일요일~월요일 / 1월 1일 / 설·추석 연휴", {SUN, MON}),
        ("매주 토요일, 일요일 / 공휴일", {SAT, SUN}),
        ("매주 주말 / 개교기념일(10월 15일) / 법정공휴일", {SAT, SUN}),
        # 경복궁: the conditional clause is an exception, not a rule
        (
            "매주 화요일 휴무, 정기휴일이 공휴일 및 대체공휴일과 겹칠 경우에는 개방하며, 그 다음 첫 번째 비공휴일이 휴궁일",
            {TUE},
        ),
        ("매주 월요일 (단, 월요일이 공휴일인 경우 그 다음날 휴관)", {MON}),
        ("매주 월요일<br>※ 단, 정기휴일이 공휴일 및 대체공휴일과 겹칠 경우에는 개방하며", {MON}),
        ("매월 첫째 주 월요일※ 공휴일인 경우 다음날 휴무", set()),  # monthly: not a weekday rule
        ("매월 둘째, 넷째 화요일", set()),
        ("1월 1일 / 설·추석 당일", set()),  # holidays only → open every weekday
        ("매주 월요일 / 1월 1일 / 설·추석 연휴 / 12월 25일", {MON}),
        ("매주 월요일 / 설·추석 연휴 / 근로자의 날 / 선거일 / 12월 29일~1월 2일", {MON}),
        ("화요일", {TUE}),
        ("연중무휴※ 실개천, 바닥분수는 매주 월요일 휴무", set()),  # a footnote about a fountain
    ],
)
def test_restdate(text: str, closed: set[int]) -> None:
    r = parse_restdate(text)
    assert r.ambiguous is None
    assert r.known
    assert set(r.days) == closed


@pytest.mark.parametrize(
    "text",
    [
        "점포별로 상이함",
        "※ 점포 별로 상이함",
        "공연 별로 상이함",
        "매주 토요일, 일요일 / 대관행사 시",
        "전시기간 외 휴관※ 전시기간에는 연중무휴이므로 자세한 사항은 홈페이지 참조 및 전화 문의 요망",
        "신세계백화점 휴점일 / 신정 / 명절",
        "[수성못 유원지] 연중무휴 [음악분수] 매주 월요일 ※ 운영 기간 홈페이지 참조",
    ],
)
def test_restdate_we_do_not_understand(text: str) -> None:
    assert parse_restdate(text).ambiguous


def test_no_restdate_is_unknown_not_open_every_day() -> None:
    r = parse_restdate("")
    assert not r.known and r.ambiguous is None


# ── hours ────────────────────────────────────────────────────────────────────────────────────────


def test_simple_range_with_last_entry_and_monday() -> None:
    p = parse_usetime("09:00~18:00 (입장마감 17:00)", "매주 월요일 휴무")
    # last entry 17:00 → the engine may still send someone at 17:00 (30-minute rule) but not later
    assert week(p) == same("09:00-17:30", closed=(MON,))
    assert p.closed_from == "restdate"


def test_last_entry_later_than_close_minus_30_keeps_close() -> None:
    p = parse_usetime("10:00~18:00 (매표마감 17:30)", "매주 월요일 / 1월 1일 / 설·추석 당일")  # 리움미술관
    assert week(p) == same("10:00-18:00", closed=(MON,))


def test_gyeongbokgung_three_seasons_take_the_narrowest_day() -> None:
    p = parse_usetime(
        "[1월~2월/11월~12월]09:00~17:00 (입장마감 16:00)[3월~5월/9월~10월]09:00~18:00 (입장마감 17:00)"
        "[6월~8월] 09:00~18:30 (입장마감 17:30)",
        "매주 화요일 휴무, 정기휴일이 공휴일 및 대체공휴일과 겹칠 경우에는 개방하며, 그 다음 첫 번째 비공휴일이 휴궁일",
    )
    assert week(p) == same("09:00-16:30", closed=(TUE,))
    assert "narrowest season" in p.notes


def test_changdeokgung_dash_last_entry_on_its_own_line() -> None:
    p = parse_usetime(
        "[2월~5월/9월~10월]- 09:00~18:00- 입장 마감 17:00[6월~8월]- 09:00~18:30- 입장 마감 17:30"
        "[11월~1월]- 09:00~17:30- 입장 마감 16:30",
        "매주 월요일 (단, 공휴일이 월요일인 경우 그 다음날 휴무)",
    )
    assert week(p) == same("09:00-17:00", closed=(MON,))


def test_summer_winter() -> None:
    p = parse_usetime("하절기 09:00~19:00 / 동절기 09:00~18:00", "연중무휴")
    assert week(p) == same("09:00-18:00")
    assert p.closed_from == "none"


def test_season_with_a_base_range_and_relative_last_entry() -> None:
    p = parse_usetime(  # 어진박물관
        "- 09:00~19:00- 하절기(6월~8월) 연장운영 09:00~20:00- 동절기(11월~2월) 단축운영 09:00~18:00"
        "- 입장 마감 : 관람 종료 1시간 전",
        "1월 1일",
    )
    assert week(p) == same("09:00-17:30")


def test_one_season_only_is_not_the_whole_year() -> None:
    p = parse_usetime("매년 6월~9월 09:00~18:00  ※ 자세한 사항은 홈페이지 참조", "연중무휴")  # 해운대해수욕장
    assert not p.ok


def test_always_open() -> None:
    p = parse_usetime("상시 개방", "연중무휴")
    assert week(p) == same("00:00-00:00")
    p = parse_usetime("상시개방", "")
    assert week(p) == same("00:00-00:00")  # every day, whatever the category's default closed day


def test_24h_close_wraps_to_midnight() -> None:
    p = parse_usetime("07:00~24:00", "연중무휴")  # 송상현광장
    assert week(p) == same("07:00-00:00")


def test_sunrise_to_sunset_is_ambiguous() -> None:
    assert parse_usetime("일출~일몰", "").reason == "sunrise / sunset"


@pytest.mark.parametrize(
    ("usetime", "restdate"),
    [
        ("점포별로 상이함", "점포별로 상이함"),
        ("08:00~21:00<br>※ 점포별 상이함", "※ 점포별 상이함"),
        ("홈페이지 참조", "홈페이지 참조"),
        ("10:00~17:00 (예약제 운영)", "화요일"),
        ("사전 예약 후 내부 관람가능", "연중무휴"),
        # 국립중앙박물관: indoor and garden hours side by side
        (
            "[실내 전시실]- 월요일~화요일 / 목요일~금요일 / 일요일 09:30~17:30 (입장 마감 17:00)"
            "- 수요일 / 토요일 09:30~21:00 (입장 마감 20:30)[야외 정원(용산)]- 07:00~22:00",
            "[휴관일]1월 1일 / 설날․추석 당일",
        ),
        ("- 정문 09:00~22:00 (입장 마감 21:30)<br>\n- 후문·천마총 09:00~21:30", "연중무휴"),  # 대릉원
        ("[공원]상시 개방[전망타워]09:00~22:00 (입장 마감 21:50)", "연중무휴"),
        ("상시 10:00~18:00(입장마감 17:00)", "연중무휴"),
        ("[일반 개장] - 09:00~18:00 [야간 개장]  - 수요일~일요일 18:00~21:00", "연중무휴"),
        ("09:00~20:45※ 12월~2월에는 18:00부터 대온실 내부 비개방함", "매주 월요일"),  # a stray time
        ("- 1층 06:00~21:00<br>- 2층 09:00~21:00<br>- 3층 09:00~23:00", "매월 둘째, 넷째 화요일"),
        ("- 월요일~금요일 17:00 / 20:00- 토요일 14:00 / 17:00 / 20:00", "연중무휴"),  # show times
        ("- 평일 10:00~18:00- 토요일 10:00~13:00", "법정공휴일 / 노동절(5월 1일)"),  # Sunday?
        ("[관람시간] 09:30~17:30 [시설이용] 09:00~18:00", "매주 월요일"),
    ],
)
def test_ambiguous_stores_nothing(usetime: str, restdate: str) -> None:
    p = parse_usetime(usetime, restdate)
    assert p.status == "ambiguous", week(p)
    assert p.days == ()


def test_empty_usetime() -> None:
    assert parse_usetime("", "연중무휴").status == "empty"


def test_weekday_and_weekend() -> None:
    p = parse_usetime("- 평일 10:00~18:00- 주말 10:00~17:00", "매주 월요일 / 설·추석 연휴")  # 백산기념관
    assert week(p) == ["휴", *["10:00-18:00"] * 4, "10:00-17:00", "10:00-17:00"]


def test_bracketed_day_groups() -> None:
    p = parse_usetime(  # 디뮤지엄
        "[화요일~목요일, 일요일]<br>\n- 11:00~18:00 <br>\n- 입장 마감 17:00<br>\n[금요일~토요일]<br>\n"
        "- 11:00~19:00 <br>\n- 입장 마감 18:00",
        "매주 월요일",
    )
    assert week(p) == [
        "휴",
        "11:00-17:30",
        "11:00-17:30",
        "11:00-17:30",
        "11:00-18:30",
        "11:00-18:30",
        "11:00-17:30",
    ]


def test_seoul_sky_sunday_to_thursday() -> None:
    p = parse_usetime(
        "[일요일~목요일]10:30~22:00 (입장 마감 21:00)[금요일~토요일]10:30~23:00 (입장 마감 22:00)", "연중무휴"
    )
    assert week(p) == [*["10:30-21:30"] * 4, "10:30-22:30", "10:30-22:30", "10:30-21:30"]


def test_a_narrower_day_label_refines_a_broader_one() -> None:
    p = parse_usetime(  # 아르코미술관: Wednesday is late
        "화요일~일요일 11:00~19:00 (입장 마감 18:30)수요일 11:00~21:00 (입장 마감 20:30)",
        "매주 월요일 / 1월 1일 / 설·추석 당일",
    )
    assert week(p) == [
        "휴",
        "11:00-19:00",
        "11:00-21:00",
        "11:00-19:00",
        "11:00-19:00",
        "11:00-19:00",
        "11:00-19:00",
    ]


def test_late_days_on_top_of_a_base_range_and_ticket_offset() -> None:
    p = parse_usetime(  # 국립현대미술관 서울관
        "10:00~18:00<br>\n수,토 10:00~21:00<br>\n※ 발권시간 : 관람종료 1시간 전까지 가능",
        "1월1일 / 설날 / 추석",
    )
    assert week(p) == [
        "10:00-17:30",
        "10:00-17:30",
        "10:00-20:30",
        "10:00-17:30",
        "10:00-17:30",
        "10:00-20:30",
        "10:00-17:30",
    ]


def test_every_day_named_differently() -> None:
    p = parse_usetime(  # 전주난장
        "- 월요일~금요일 10:00~19:00- 토요일 09:30~19:30- 일요일 09:30~19:00※ 1시간 전 입장 마감", "연중무휴"
    )
    assert week(p) == [*["10:00-18:30"] * 5, "09:30-19:00", "09:30-18:30"]


def test_break_in_parentheses() -> None:
    p = parse_usetime("09:00~17:00 (휴게시간 12:00~13:00)", "매주 토요일, 일요일 / 공휴일")  # 건국대 박물관
    assert week(p) == [*["09:00-17:00/b12:00-13:00"] * 5, "휴", "휴"]


def test_break_written_after_its_range() -> None:
    p = parse_usetime("매일 10:00-18:00 ( 12:00-13:00 점심시간 )", "연중무휴")  # 달빛갤러리
    assert week(p) == same("10:00-18:00/b12:00-13:00")


def test_break_on_its_own_line() -> None:
    p = parse_usetime("- 09:00~17:00<br>\n- 휴게시간 12:00~13:00", "연중무휴")  # 청주향교
    assert week(p) == same("09:00-17:00/b12:00-13:00")


def test_boilerplate_footnote_does_not_make_it_ambiguous() -> None:
    p = parse_usetime(
        "09:00~18:00<br>\n※ 자세한 사항은 전화문의 요망", "연중무휴<br>※ 자세한 사항은 전화문의 요망"
    )
    assert week(p) == same("09:00-18:00")


def test_closed_day_inside_the_hours_text() -> None:
    p = parse_usetime("09:00~18:00 (월요일 휴관)", "")
    assert week(p) == same("09:00-18:00", closed=(MON,))
    assert p.closed_from == "usetime"


def test_no_restdate_falls_back_to_the_category_default() -> None:
    p = parse_usetime("10:00~18:00", "", default_closed=[MON])
    assert week(p) == same("10:00-18:00", closed=(MON,))
    assert p.closed_from == "default"
    p = parse_usetime("10:00~18:00", "")
    assert week(p) == same("10:00-18:00")


def test_korean_clock_words() -> None:
    p = parse_usetime("오전 10시 ~ 오후 7시", "매주 화요일")
    assert week(p) == same("10:00-19:00", closed=(TUE,))


def test_past_midnight() -> None:
    p = parse_usetime("18:00~02:00", "연중무휴")
    assert week(p) == same("18:00-02:00")


def test_closed_every_day_is_nonsense() -> None:
    assert not parse_usetime("10:00~18:00", "매주 월요일~일요일").ok  # 글래드스톤 갤러리


# ── field names per content type ──────────────────────────────────────────────────────────────────


def test_parse_item_reads_the_right_fields() -> None:
    culture = {"usetimeculture": "10:00~18:00", "restdateculture": "매주 월요일", "usetime": "x"}
    assert week(parse_item("14", culture)) == same("10:00-18:00", closed=(MON,))
    shop = {"opentime": "10:30~22:00", "restdateshopping": "연중무휴"}
    assert week(parse_item("38", shop)) == same("10:30-22:00")
    leports = {"usetimeleports": "09:00~18:00", "restdateleports": "매주 화요일"}
    assert week(parse_item("28", leports)) == same("09:00-18:00", closed=(TUE,))
    assert week(parse_item("12", {"usetime": "상시 개방", "restdate": "연중무휴"})) == same("00:00-00:00")
