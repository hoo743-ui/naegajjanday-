"""사용 지표 definitions (docs/62): what counts as a used course, a first course accepted, a swap per category."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.core.config import API_ROOT
from app.services import event_catalog
from app.services.usage_metrics import Ev, Feedback, Gen, Inputs, compute, format_report

TZ = ZoneInfo("Asia/Seoul")
NOW = datetime(2026, 9, 26, 12, 0, tzinfo=UTC)  # a Saturday


def cid(n: int) -> str:
    return f"00000000-0000-4000-8000-{n:012d}"


class TestCatalog:
    def test_only_listed_short_scalar_props_survive(self) -> None:
        props = {
            "length": 23,
            "matched": 2,
            "options": "BAR,MOVIE",
            "text": "애플스토어 들렀다가 영화 보고 싶어",  # the one-line text is never a listed key
            "course_id": cid(1),
        }
        assert event_catalog.clean_props("course_option_text_parsed", props) == {
            "length": 23,
            "matched": 2,
            "options": "BAR,MOVIE",
        }
        long = {"label": "x" * 65, "shared": True}
        assert event_catalog.clean_props("course_viewed", long) == {"shared": True}
        nested = {"position": {"a": 1}, "strategy": ["x"], "from": "prev"}
        assert event_catalog.clean_props("directions_opened", nested) == {"from": "prev"}

    def test_every_web_event_is_accepted(self) -> None:
        """A name in the web catalog but not here would be thrown away by POST /v1/events."""
        events_ts = API_ROOT.parent / "web" / "src" / "lib" / "analytics" / "events.ts"
        if not events_ts.exists():
            pytest.skip("web app not checked out")
        body = events_ts.read_text(encoding="utf-8").split("export interface AnalyticsEvents {", 1)[1]
        body = body.split("\n}\n", 1)[0]
        names = set(re.findall(r"^  ([a-z_]+): ", body, re.M))
        assert len(names) > 40
        assert sorted(n for n in names if not event_catalog.is_known(n)) == []

    def test_stop_sheet_events_are_already_accepted(self) -> None:
        for name in (
            "stop_sheet_opened",
            "stop_fixed",
            "stop_alternative_viewed",
            "stop_swapped_from_sheet",
            "course_confirmed",
            "outbound_link",
        ):
            assert event_catalog.is_known(name)
        assert not event_catalog.is_known("password_typed")


class TestNorthStar:
    def test_used_within_seven_days_by_any_signal(self) -> None:
        t = NOW - timedelta(days=2)
        gens = [
            Gen(at=t, courses=(cid(1), cid(2))),  # alternative shared
            Gen(at=t, courses=(cid(3),)),  # saved (course status)
            Gen(at=t, courses=(cid(4),)),  # directions
            Gen(at=t, courses=(cid(5),)),  # only viewed
            Gen(at=NOW - timedelta(days=12), courses=(cid(6),)),  # shared 9 days later: too late
            Gen(at=t, courses=(cid(7),)),  # marked visited
        ]
        events = [
            Ev("share_clicked", cid(2), "d1", t + timedelta(minutes=3)),
            Ev("directions_opened", cid(4), "d2", t + timedelta(hours=1), {"position": 1}),
            Ev("course_viewed", cid(5), "d3", t),
            Ev("share_clicked", cid(6), "d4", NOW - timedelta(days=3)),
        ]
        feedback = [Feedback(cid(7), t + timedelta(days=1), True, None, 30000)]
        m = compute(
            Inputs(gens=gens, events=events, owned={cid(3)}, feedback=feedback), now=NOW, days=28, tz=TZ
        )

        this_week = m.north_star[-1]
        assert (this_week.generated, this_week.used, this_week.complete) == (5, 4, False)
        assert this_week.signals.model_dump() == {"saved": 1, "shared": 1, "outbound": 1, "confirmed": 1}
        last_week = m.north_star[-2]
        assert (last_week.generated, last_week.used) == (1, 0)
        assert len(m.north_star) == 8 and m.north_star[0].generated == 0 and m.north_star[0].rate is None
        assert (m.used.count, m.used.total) == (4, 6)
        assert (m.outbound.count, m.share_opened.total) == (1, 2)
        assert m.visited.count == 1 and m.collecting_since is not None
        assert any("쓰인 코스" in line for line in format_report(m))

    def test_first_course_accepted_excludes_rerolls_and_swaps(self) -> None:
        t = NOW - timedelta(days=1)
        gens = [
            Gen(at=t, courses=(cid(1),)),  # made, saved as it was
            Gen(at=t + timedelta(minutes=10), courses=(cid(2),)),  # came from "다시 짜기" on cid(1)'s browser
            Gen(at=t, courses=(cid(3),)),  # saved after a swap
        ]
        events = [
            Ev("course_generated", cid(1), "a", t),
            Ev("course_saved", cid(1), "a", t + timedelta(minutes=2)),
            Ev("reroll_clicked", cid(1), "a", t + timedelta(minutes=8)),
            Ev("course_generated", cid(2), "a", t + timedelta(minutes=10)),
            Ev("course_saved", cid(2), "a", t + timedelta(minutes=12)),
            Ev("stop_swapped", cid(3), "b", t, {"position": 2}),
            Ev("course_saved", cid(3), "b", t + timedelta(minutes=1)),
        ]
        m = compute(Inputs(gens=gens, events=events), now=NOW, days=28, tz=TZ)
        # cid(1) was rerolled after being saved → not "as it was"; cid(2) came from a reroll; cid(3) was swapped
        assert (m.first_course_accepted.count, m.first_course_accepted.total) == (0, 3)

        m2 = compute(Inputs(gens=gens[:1], events=events[:2]), now=NOW, days=28, tz=TZ)
        assert (m2.first_course_accepted.count, m2.first_course_accepted.total) == (1, 1)

    def test_swaps_per_category_share_open_and_options(self) -> None:
        t = NOW - timedelta(days=1)
        gens = [Gen(at=t, courses=(cid(1),), places={cid(1): ("p1", "p2", "p3")})]
        events = [
            Ev("course_viewed", cid(1), "a", t),
            Ev("stop_swapped", cid(1), "a", t, {"position": 2}),
            Ev("stop_swapped_from_sheet", cid(1), "a", t, {"position": 2}),
            Ev("share_clicked", cid(1), "a", t),
            Ev("course_option_toggled", cid(1), "a", t, {"option": "BAR", "on": True, "via": "chip"}),
            Ev("course_option_toggled", cid(1), "a", t, {"option": "BAR", "on": False, "via": "text"}),
            Ev("course_option_text_parsed", cid(1), "a", t, {"length": 12, "matched": 0}),
        ]
        data = Inputs(
            gens=gens,
            events=events,
            place_category={"p1": "food", "p2": "cafe", "p3": "food"},
            category_names={"food": "음식", "cafe": "카페"},
            course_openers={cid(1): {"a", "friend"}},
        )
        m = compute(data, now=NOW, days=28, tz=TZ)
        by = {c.category: (c.stops, c.swaps) for c in m.swap_by_category}
        assert by == {"food": (2, 0), "cafe": (1, 2)}
        assert (m.share_opened.count, m.share_opened.total) == (1, 1)
        assert [(o.option, o.on, o.off, o.chip, o.text) for o in m.options] == [("BAR", 1, 1, 1, 1)]
        assert (m.option_text.count, m.option_text.total) == (0, 1)

        alone = Inputs(gens=gens, events=events, course_openers={cid(1): {"a"}})
        assert compute(alone, now=NOW, days=28, tz=TZ).share_opened.count == 0
