from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

import pytest

from app.domain.showtimes import HOLIDAY, fits_window, parse_guidance, parse_runtime_min, shows_on

KST = timezone(timedelta(hours=9))
TYPICAL = "화요일 ~ 금요일(20:00), 토요일(15:00,19:00), 일요일(14:00), HOL(14:00)"
# 2026-09-21 is a Monday
MON, TUE, WED, FRI, SAT, SUN = (date(2026, 9, d) for d in (21, 22, 23, 25, 26, 27))
RUN_FROM, RUN_TO = date(2026, 9, 1), date(2026, 10, 31)


class TestParseGuidance:
    def test_range_expands_to_every_day_in_between(self) -> None:
        schedule = parse_guidance("화요일 ~ 금요일(20:00)")
        assert schedule == {1: [time(20)], 2: [time(20)], 3: [time(20)], 4: [time(20)]}

    def test_list_of_times_in_one_group(self) -> None:
        assert parse_guidance("토요일(15:00,19:00)") == {5: [time(15), time(19)]}

    def test_multiple_comma_separated_groups(self) -> None:
        schedule = parse_guidance(TYPICAL)
        assert schedule[1] == [time(20)] and schedule[5] == [time(15), time(19)]
        assert schedule[6] == [time(14)] and 0 not in schedule

    def test_holiday_marker_is_its_own_key_not_sunday(self) -> None:
        assert parse_guidance("HOL(14:00)") == {HOLIDAY: [time(14)]}
        assert parse_guidance("공휴일(13:00)") == {HOLIDAY: [time(13)]}

    def test_holiday_shares_a_group_with_weekdays(self) -> None:
        schedule = parse_guidance("토요일 ~ 일요일, HOL(14:00, 18:00)")
        assert set(schedule) == {5, 6, HOLIDAY} and schedule[HOLIDAY] == [time(14), time(18)]

    def test_wrapping_range(self) -> None:
        assert set(parse_guidance("금요일 ~ 월요일(19:30)")) == {4, 5, 6, 0}

    def test_several_single_days_before_one_bracket(self) -> None:
        assert parse_guidance("월요일, 수요일(19:30)") == {0: [time(19, 30)], 2: [time(19, 30)]}

    def test_short_weekday_words(self) -> None:
        assert set(parse_guidance("화~목(20:00), 토(15:00)")) == {1, 2, 3, 5}

    def test_every_day(self) -> None:
        assert set(parse_guidance("매일(11:00,14:00)")) == set(range(7))

    def test_same_day_in_two_groups_is_merged_sorted_and_unique(self) -> None:
        schedule = parse_guidance("수요일(20:00), 수요일(16:00,20:00)")
        assert schedule == {2: [time(16), time(20)]}

    def test_no_space_and_full_width_colon(self) -> None:
        assert parse_guidance("목요일~금요일(19：30)") == {3: [time(19, 30)], 4: [time(19, 30)]}

    @pytest.mark.parametrize(
        "junk",
        [
            "",
            None,
            "문의 요망",
            "토요일",
            "토요일(오후 세 시)",
            "(20:00)",
            "토요일(25:00)",
            "토요일(19:75)",
            "(((",
        ],
    )
    def test_junk_is_no_show_and_never_raises(self, junk: str | None) -> None:
        assert parse_guidance(junk) == {}

    def test_junk_group_does_not_spoil_a_good_one(self) -> None:
        assert parse_guidance("상세 일정 참조(예매처), 일요일(15:00)") == {6: [time(15)]}


class TestShowsOn:
    def test_weekday_lookup(self) -> None:
        assert shows_on(TYPICAL, TUE, RUN_FROM, RUN_TO) == [time(20)]
        assert shows_on(TYPICAL, SAT, RUN_FROM, RUN_TO) == [time(15), time(19)]

    def test_dark_day(self) -> None:
        assert shows_on(TYPICAL, MON, RUN_FROM, RUN_TO) == []

    def test_outside_the_run(self) -> None:
        assert shows_on(TYPICAL, SAT, date(2026, 10, 1), RUN_TO) == []
        assert shows_on(TYPICAL, SAT, RUN_FROM, date(2026, 9, 20)) == []

    def test_period_bounds_are_inclusive_and_optional(self) -> None:
        assert shows_on(TYPICAL, SAT, SAT, SAT) == [time(15), time(19)]
        assert shows_on(TYPICAL, SAT, None, None) == [time(15), time(19)]

    def test_holiday_times_only_when_the_caller_says_so(self) -> None:
        assert shows_on(TYPICAL, WED, RUN_FROM, RUN_TO) == [time(20)]
        assert shows_on(TYPICAL, WED, RUN_FROM, RUN_TO, is_holiday=True) == [time(14)]
        assert shows_on("수요일(20:00)", WED, RUN_FROM, RUN_TO, is_holiday=True) == [time(20)]


class TestFitsWindow:
    START = datetime(2026, 9, 26, 14, 0, tzinfo=KST)  # Saturday

    def test_show_inside_window(self) -> None:
        end = self.START + timedelta(hours=4)
        assert fits_window([time(15), time(19)], self.START, end, 100) == [time(15)]

    def test_may_end_up_to_30_min_after_the_window(self) -> None:
        end = self.START + timedelta(hours=3)  # 17:00 → latest end 17:30
        assert fits_window([time(15)], self.START, end, 150) == [time(15)]  # ends 17:30
        assert fits_window([time(15)], self.START, end, 151) == []

    def test_show_before_the_window_or_at_its_end_does_not_fit(self) -> None:
        end = self.START + timedelta(hours=1)
        assert fits_window([time(13, 30), time(15)], self.START, end, 60) == []

    def test_start_exactly_at_window_start_fits(self) -> None:
        assert fits_window([time(14)], self.START, self.START + timedelta(hours=2), 120) == [time(14)]

    def test_unknown_runtime_checks_only_the_start(self) -> None:
        end = self.START + timedelta(hours=2)
        assert fits_window([time(15, 30), time(19)], self.START, end, None) == [time(15, 30)]

    def test_empty_or_inverted_window(self) -> None:
        assert fits_window([time(15)], self.START, self.START, 60) == []
        assert fits_window([], self.START, self.START + timedelta(hours=3), 60) == []


@pytest.mark.parametrize(
    ("text", "minutes"),
    [
        ("1시간 30분", 90),
        ("2시간", 120),
        ("90분", 90),
        ("1시간30분", 90),
        ("", None),
        (None, None),
        ("미정", None),
    ],
)
def test_parse_runtime(text: str | None, minutes: int | None) -> None:
    assert parse_runtime_min(text) == minutes
