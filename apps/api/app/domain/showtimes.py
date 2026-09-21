"""Performance showtimes (pure, no I/O).

The official performance API describes showtimes as free text, e.g.
    "화요일 ~ 금요일(20:00), 토요일(15:00,19:00), 일요일(14:00), HOL(14:00)"
This module turns that into weekday → start times and answers the one question a day course has:
"is there a show that starts inside our meeting window — and ends before we have to leave?"

Unknown or broken text never raises: what cannot be read is simply not a show. We would rather miss a
performance than send somebody to a closed door.
"""

from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta

HOLIDAY = 7  # key next to the weekdays 0 (Mon) … 6 (Sun)
END_GRACE_MIN = 30  # a show may run this long past the end of the meeting window
_DAYS = "월화수목금토일"
_GROUP = re.compile(r"([^()]*)\(([^()]*)\)")
_FULL_DAY = re.compile(rf"([{_DAYS}])요일")
_SHORT_DAY = re.compile(rf"(?<![가-힣])([{_DAYS}])(?![가-힣])")
_RANGE = re.compile(rf"([{_DAYS}])(?:요일)?\s*[~\-–∼〜]\s*([{_DAYS}])(?:요일)?")
_TIME = re.compile(r"(?<!\d)(\d{1,2})\s*[:：]\s*(\d{2})(?!\d)")
_HOLIDAY_WORDS = ("HOL", "공휴일", "휴일")
_EVERY_DAY_WORDS = ("매일", "EVERYDAY")
_HOURS = re.compile(r"(\d+)\s*시간")
_MINUTES = re.compile(r"(\d+)\s*분")

Schedule = dict[int, list[time]]


def _times(text: str) -> list[time]:
    found = {time(int(h), int(m)) for h, m in _TIME.findall(text) if int(h) < 24 and int(m) < 60}
    return sorted(found)


def _days(text: str) -> set[int]:
    upper = text.upper()
    days: set[int] = set()
    if any(word in upper for word in _HOLIDAY_WORDS):
        days.add(HOLIDAY)
        for word in _HOLIDAY_WORDS:  # the "일" of "공휴일" is not a Sunday
            upper = upper.replace(word, " ")
    if any(word in upper for word in _EVERY_DAY_WORDS):
        days.update(range(7))
    for start, end in _RANGE.findall(upper):
        a, b = _DAYS.index(start), _DAYS.index(end)
        span = range(a, b + 1) if a <= b else [*range(a, 7), *range(0, b + 1)]  # "금 ~ 월" wraps
        days.update(span)
    singles = _FULL_DAY.findall(upper) or _SHORT_DAY.findall(upper)
    days.update(_DAYS.index(d) for d in singles)
    return days


def parse_guidance(guidance: str | None) -> Schedule:
    """weekday (0=Mon … 6=Sun, 7=public holiday) → sorted start times."""
    schedule: dict[int, set[time]] = {}
    for day_text, time_text in _GROUP.findall(guidance or ""):
        times = _times(time_text)
        if not times:
            continue
        for day in _days(day_text):
            schedule.setdefault(day, set()).update(times)
    return {day: sorted(times) for day, times in sorted(schedule.items())}


def shows_on(
    guidance: str | None,
    day: date,
    period_from: date | None,
    period_to: date | None,
    *,
    is_holiday: bool = False,
) -> list[time]:
    """Start times on `day`; nothing outside the run of the performance. Holiday times replace the
    weekday's only when the caller knows the day is a public holiday (this module has no calendar)."""
    if (period_from and day < period_from) or (period_to and day > period_to):
        return []
    schedule = parse_guidance(guidance)
    if is_holiday and HOLIDAY in schedule:
        return list(schedule[HOLIDAY])
    return list(schedule.get(day.weekday(), []))


def fits_window(
    shows: list[time], window_start: datetime, window_end: datetime, runtime_min: int | None
) -> list[time]:
    """Shows (on the window's first day) that start inside the window and end ≤ window end + 30 min.
    An unknown runtime cannot rule a show out, so only the start is checked then."""
    if window_end <= window_start:
        return []
    latest_end = window_end + timedelta(minutes=END_GRACE_MIN)
    fitting: list[time] = []
    for show in shows:
        starts = datetime.combine(window_start.date(), show, tzinfo=window_start.tzinfo)
        if not window_start <= starts < window_end:
            continue
        if runtime_min is not None and starts + timedelta(minutes=runtime_min) > latest_end:
            continue
        fitting.append(show)
    return fitting


def parse_runtime_min(text: str | None) -> int | None:
    """ "1시간 30분" → 90, "90분" → 90, junk → None."""
    if not text:
        return None
    hours, minutes = _HOURS.search(text), _MINUTES.search(text)
    if not hours and not minutes:
        return None
    total = (int(hours.group(1)) * 60 if hours else 0) + (int(minutes.group(1)) if minutes else 0)
    return total if 0 < total <= 600 else None
