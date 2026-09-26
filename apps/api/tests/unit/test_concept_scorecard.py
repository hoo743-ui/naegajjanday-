"""Concept scorecard (docs/58): the per-course rules, the metric math and the ranking, on fake records."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.domain.models import CourseResult, PlaceCandidate, StopResult
from app.evaluation import concept as C
from app.evaluation.harness import load_spec
from tests.factories import SUNDAY_6PM, context, place

RULES = load_spec()["rules"]


def stop(
    role: str,
    name: str = "",
    *,
    position: int = 1,
    category: str = "food.korean",
    at: str = "12:00",
    leave_min: int = 13 * 60,
    price: int = 20000,
    leg: int = 5,
    kind: str | None = None,
    draw: bool = False,
    **tags: float,
) -> C.Stop:
    kinds = {"MEAL": "DINING", "CAFE": "CAFE", "DESSERT": "CAFE", "BAR": "NIGHT"}
    return C.Stop(
        position=position, role=role, name=name or role.lower(), category=category, at=at,
        leave_min=leave_min, price=price, leg=leg, kind=kind or kinds.get(role, "VIEW"), tags=dict(tags),
        draw=draw,
    )  # fmt: skip


def rec(
    purpose: str = "date",
    stops: list[C.Stop] | None = None,
    *,
    scene: str | None = None,
    start: str = "12:00",
    region: str = "seoul-hongdae",
    group: str = "hotspot",
    budget: int = 60000,
    error: str | None = None,
    flags: list[str] | None = None,
    draw_eligible: bool = False,
    with_concept: bool = True,
) -> C.Record:
    case = C.Case(region, purpose, 2, budget, start, scene=scene, group=group)
    stops = stops or []
    price = sum(s.price for s in stops)
    found = list(flags or [])
    if with_concept and not error:
        found += C.concept_flags(case, stops, price)
    return C.Record(case, error=error, price=price, stops=stops, flags=found, draw_eligible=draw_eligible)


def codes(r: C.Record) -> set[str]:
    return set(r.codes)


# ── the concept's rules ─────────────────────────────────────────────────────────────────────


def test_date_scene_rules() -> None:
    r = rec("date", [stop("MEAL", "고깃집", 단체석=0.9), stop("CAFE", "무인카페", position=2, 무인매장=1.0)])
    assert {"DATE_GROUP_SPOT", "DATE_UNMANNED", "WEAK_ENDING"} <= codes(r)
    assert "CAFE_CAFE" not in codes(r)  # a meal then a café is not a repetition


def test_anniversary_wants_one_table_to_carry_the_day() -> None:
    small = [stop("MEAL", price=20000), stop("ACTIVITY", position=2, price=40000, category="activity.x")]
    assert "ANNIV_NO_SPLURGE" in codes(rec("date", small, scene="anniversary"))
    big = [stop("MEAL", price=60000), stop("CAFE", position=2, price=15000)]
    assert "ANNIV_NO_SPLURGE" not in codes(rec("date", big, scene="anniversary"))
    assert "ANNIV_NO_SPLURGE" not in codes(rec("date", small, scene="steady"))


def test_family_scene_rules_follow_the_scene() -> None:
    drink = [stop("MEAL", "호프", 술자리=1.0), stop("ATTRACTION", position=2, leg=25, leave_min=21 * 60 + 30)]
    kids = codes(rec("family", drink, scene="kids"))
    assert {"FAMILY_DRINK", "LONG_LEG_KIDS", "KIDS_LATE"} <= kids
    adults = codes(rec("family", drink, scene="adults"))
    assert not adults & {"FAMILY_DRINK", "LONG_LEG_ADULTS", "KIDS_LATE"}  # 어른끼리 may have a drink
    noisy = [stop("ACTIVITY", "노래방", category="activity.karaoke")]
    assert "PARENTS_NOISY" in codes(rec("family", noisy, scene="parents"))
    # no scene = 아이와 (docs/48 §9)
    assert "FAMILY_DRINK" in codes(rec("family", drink))


def test_night_of_a_date_is_a_drink_first() -> None:
    walk_only = [stop("ATTRACTION", "강변", category="attraction.park")]
    assert "NIGHT_NO_DRINK" in codes(rec("date", walk_only, start="21:30"))
    assert "NIGHT_NO_DRINK" not in codes(rec("date", walk_only, start="18:30"))
    assert "NIGHT_NO_DRINK" not in codes(rec("solo", walk_only, start="21:30"))
    with_bar = [stop("BAR", "와인바"), *walk_only]
    assert "NIGHT_NO_DRINK" not in codes(rec("date", with_bar, start="21:30"))


def test_cafe_then_dessert_counts_as_cafe_cafe() -> None:
    r = rec("friends", [stop("MEAL"), stop("CAFE", position=2), stop("DESSERT", position=3)])
    assert "CAFE_CAFE" in codes(r)


# ── metric math ─────────────────────────────────────────────────────────────────────────────


def result(metric_id: str, records: list[C.Record]) -> C.Result:
    return C.evaluate(C.METRIC_BY_ID[metric_id], records)


def test_chain_rate_counts_paid_stops_of_its_purpose_only() -> None:
    records = [
        rec("travel", [stop("MEAL", 체인점=1.0), stop("CAFE", position=2), stop("ATTRACTION", position=3)]),
        rec("travel", [stop("MEAL"), stop("BAR", position=2, 체인점=1.0)]),
        rec("date", [stop("MEAL", 체인점=1.0)]),  # another purpose
        rec("travel", error="NO_CANDIDATES"),  # no course: counted by no_course_rate, not here
    ]
    r = result("chain_rate_travel", records)
    assert r.value == pytest.approx(2 / 4)  # 2 chains of 4 paid stops; the sight is not a paid stop
    assert r.n == 2 and r.units == 4
    assert not r.passed and len(r.examples) == 2


def test_draw_rate_only_counts_hotspot_courses_that_can_have_a_draw() -> None:
    records = [
        rec("date", [stop("MEAL", draw=True)], draw_eligible=True),
        rec("date", [stop("MEAL")], draw_eligible=True, region="busan-seomyeon"),
        rec("date", [stop("MEAL")], draw_eligible=False),  # nothing to carry here
        rec("date", [stop("MEAL")], draw_eligible=True, group="date_scene"),
    ]
    r = result("draw_rate", records)
    assert r.value == pytest.approx(0.5) and r.n == 2
    assert r.examples and "busan-seomyeon" in r.examples[0]


def test_no_course_rate_and_solo_night_bar() -> None:
    records = [
        rec("solo", [stop("BAR")], start="21:30", group="solo_night"),
        rec("solo", [stop("ATTRACTION")], start="21:30", group="solo_night"),
        rec("solo", start="21:30", error="BUDGET_TOO_LOW", group="solo_night"),
        rec("solo", [stop("ATTRACTION")], start="15:00"),  # a day, not a night
    ]
    assert result("no_course_rate", records).value == pytest.approx(0.25)
    bar = result("solo_night_bar_rate", records)
    assert bar.value == pytest.approx(0.5) and bar.n == 2 and not bar.passed


def test_low_budget_use_skips_the_night() -> None:
    records = [
        rec("date", [stop("MEAL")], flags=["LOW_BUDGET_USE:30%"]),
        rec(
            "date", [stop("BAR")], start="21:30", flags=["LOW_BUDGET_USE:20%"]
        ),  # night leftover is explained
        rec("date", [stop("MEAL")]),
    ]
    r = result("low_budget_use_rate", records)
    assert r.value == pytest.approx(0.5) and r.n == 2


def test_mean_stops_counts_day_courses() -> None:
    stops3 = [stop("MEAL"), stop("CAFE", position=2), stop("ATTRACTION", position=3)]
    records = [rec("date", stops3), rec("date", stops3[:1]), rec("date", stops3[:1], start="22:00")]
    r = result("mean_stops_day", records)
    assert r.value == pytest.approx(2.0) and r.n == 2 and not r.passed
    assert len(r.examples) == 1  # the one-stop day, not the three-stop one


def test_few_stops_leaves_out_an_evening_with_the_kids() -> None:
    two = [stop("MEAL"), stop("DESSERT", position=2)]
    records = [
        rec("family", two, scene="kids", start="18:30", flags=["FEW_STOPS:2곳"]),  # ends by 20:30 on purpose
        rec("family", two, start="18:30", flags=["FEW_STOPS:2곳"]),  # no scene = 아이와
        rec("family", two, scene="parents", start="18:30", flags=["FEW_STOPS:2곳"]),
        rec("family", two, scene="kids", start="12:00", flags=["FEW_STOPS:2곳"]),
    ]
    r = result("few_stops_rate", records)
    assert r.n == 2 and r.value == pytest.approx(1.0)


def test_empty_metric_is_not_ranked_as_failing() -> None:
    r = result("family_scene_flag_rate", [rec("date", [stop("MEAL")])])
    assert r.value is None and r.n == 0 and r.gap is None and not r.examples


# ── ranking ─────────────────────────────────────────────────────────────────────────────────


def fake(metric_id: str, value: float | None, passed: bool, gap: float | None) -> C.Result:
    m = C.METRIC_BY_ID[metric_id]
    return C.Result(metric_id, value, 10, 10, m.target, m.direction, passed, gap, 0.02)


def test_rank_puts_the_furthest_failing_metric_first() -> None:
    ranked = C.rank(
        [
            fake("cafe_cafe_rate", 0.01, True, -0.08),
            fake("draw_rate", 0.40, False, 1.2),
            fake("family_scene_flag_rate", None, False, None),
            fake("chain_rate_travel", 0.15, False, 0.4),
            fake("clean_rate", 0.49, True, -0.01),
        ]
    )
    assert [r.id for r in ranked] == [
        "draw_rate", "chain_rate_travel", "clean_rate", "cafe_cafe_rate", "family_scene_flag_rate",
    ]  # fmt: skip


def test_gap_is_normalized_by_scale_and_weight() -> None:
    # draw_rate 0.45 vs ≥0.70 → 25 points short = 1.0; over_budget 0.05 vs ≤0 → 5 points × weight 1.5 / 0.25
    draw = C.evaluate(
        C.METRIC_BY_ID["draw_rate"],
        [rec("date", [stop("MEAL", draw=i < 9)], draw_eligible=True) for i in range(20)],
    )
    assert draw.value == pytest.approx(0.45) and draw.gap == pytest.approx(1.0)
    over = C.evaluate(
        C.METRIC_BY_ID["over_budget_rate"],
        [rec("date", [stop("MEAL")], flags=["OVER_BUDGET:110%"] if i == 0 else []) for i in range(20)],
    )
    assert over.gap == pytest.approx(0.05 * 1.5 / 0.25)


def test_noise_band_has_a_floor_and_shrinks_with_the_sample() -> None:
    m = C.METRIC_BY_ID["chain_rate_travel"]
    assert C.noise_band(m, 0.0, 1000) == 0.02
    assert C.noise_band(m, 0.3, 20) > C.noise_band(m, 0.3, 200) >= 0.02


# ── comparing runs ──────────────────────────────────────────────────────────────────────────


def prev(**values: float) -> dict[str, object]:
    return {"metrics": {k: {"value": v, "noise": 0.02} for k, v in values.items()}}


def test_compare_marks_moves_beyond_the_noise_band() -> None:
    now = [
        fake("chain_rate_travel", 0.10, False, 0.2),  # was 0.20: lower is better → better
        fake("draw_rate", 0.59, False, 0.4),  # was 0.60: inside noise → same
        fake("cafe_cafe_rate", 0.10, False, 0.3),  # was 0.02 → worse
        fake("clean_rate", 0.5, True, 0.0),  # not in the previous run → new
    ]
    d = C.compare(now, prev(chain_rate_travel=0.2, draw_rate=0.6, cafe_cafe_rate=0.02))
    assert {k: v.status for k, v in d.items()} == {
        "chain_rate_travel": "better", "draw_rate": "same", "cafe_cafe_rate": "worse", "clean_rate": "new",
    }  # fmt: skip
    assert d["chain_rate_travel"].change == pytest.approx(-0.1)
    ok, why = C.verdict(now, d, "chain_rate_travel")
    assert not ok and "cafe_cafe_rate" in why
    ok, why = C.verdict(
        now[:2], C.compare(now[:2], prev(chain_rate_travel=0.2, draw_rate=0.6)), "chain_rate_travel"
    )
    assert ok and why.startswith("SHIP")
    ok, _ = C.verdict(now, d, "draw_rate")  # moved the wrong way (even if inside noise): not an improvement
    assert not ok


# ── sample · history · report ───────────────────────────────────────────────────────────────


def test_quick_sample_size_and_groups() -> None:
    spots = [f"r{i}" for i in range(55)]
    quick = C.build_sample("quick", spots)
    assert 90 <= len(quick) <= 140
    groups = {"hotspot", "solo_night", "date_scene", "family_scene", "night", "regular"}
    assert {c.group for c in quick} == groups
    # 처음 · 자주: every hotspot request has its regular twin, planned after it
    hot = [c.key for c in quick if c.group == "hotspot"]
    regular = [c for c in quick if c.group == "regular"]
    assert [c.first_key for c in regular] == hot and all(c.regular for c in regular)
    assert max(i for i, c in enumerate(quick) if c.group == "hotspot") < quick.index(regular[0])
    assert all(c.night for c in quick if c.group == "solo_night")
    full = C.build_sample("full", spots)
    assert len(full) > 2 * len(quick)
    assert len({c.key for c in full}) == len(full)  # every case distinct
    with pytest.raises(ValueError):
        C.build_sample("huge", spots)


def test_sample_day_is_a_saturday_at_least_two_days_ahead() -> None:
    for offset in range(7):
        today = date(2026, 9, 21) + timedelta(days=offset)
        day = C.sample_day(today)
        assert day.weekday() == 5 and 2 <= (day - today).days <= 8


def test_history_saves_latest_and_named(tmp_path: Path) -> None:
    records = [rec("date", [stop("MEAL", 체인점=1.0)])]
    results = C.evaluate_all(records)
    payload = C.build_payload(
        sample="quick", day=date(2026, 10, 3), records=records, results=results, runtime_s=12.3, note="t"
    )
    paths = C.save_run(payload, "baseline", tmp_path)
    assert [p.name for p in paths][1:] == ["latest.json", "baseline.json"]
    assert C.load_previous(None, tmp_path)["metrics"]["chain_rate_date"]["value"] == 1.0  # type: ignore[index]
    assert C.load_previous("baseline", tmp_path) is not None
    assert C.load_previous("nope", tmp_path) is None

    deltas = C.compare(results, payload)
    table = C.render(results, deltas)
    assert "chain_rate_date" in table and "✗" in table and "고칠 곳" in table
    line = C.log_line(payload, results, deltas)
    assert line.startswith("| ") and "quick" in line and "chain_rate_date" in line
    log = C.append_log(line, tmp_path / "log.md")
    C.append_log(line, log)
    text = log.read_text(encoding="utf-8")
    assert text.startswith("# 58") and text.count(line) == 2


def test_record_from_marks_draws_and_chains() -> None:
    """The bridge from the engine's objects to a record: a curated draw word on a food sign, a curated sight."""
    at = SUNDAY_6PM.replace(hour=12)
    sight = place("ATTRACTION", "attraction.landmark", None, name="전동성당")
    meal = place("MEAL", "food.korean", 12000, name="한국관 비빔밥", tags={"체인점": 1.0})

    def s(position: int, p: PlaceCandidate) -> StopResult:
        return StopResult(
            position=position, role=p.course_role, place=p, arrive_at=at, leave_at=at + timedelta(minutes=60),
            est_price=24000, travel_min_from_prev=5, distance_m_from_prev=300, score=0.7, score_breakdown={},
            congestion=None, slot_budget=24000.0,
        )  # fmt: skip

    course = CourseResult(
        label="추천", template_id=1, stops=[s(1, meal), s(2, sight)], total_price=24000, total_travel_min=5,
        total_distance_m=300, duration_min=120, score=0.7, objective=0.7, optimizer="none",
    )  # fmt: skip
    ctx = context(60000, draw_words=frozenset({"비빔밥"}), draw_ids=frozenset({sight.id}))
    region = SimpleNamespace(name="전주 한옥마을")
    r = C.record_from(C.Case("jeonju-hanok", "travel", 2, 60000, "12:00"), region, ctx, course, RULES)
    assert r.draw_eligible and [x.draw for x in r.stops] == [True, True]
    assert r.stops[0].chain and r.stops[0].tags == {"체인점": 1.0}
    assert "WEAK_ENDING" not in r.codes  # ends on the sight


# ── 처음 · 자주: the paired sample (docs/59 #1) ─────────────────────────────────────────────────


def _regular(stops: list[C.Stop], *, pair_draw: bool | None, draw_eligible: bool = True) -> C.Record:
    case = C.Case("seoul-hongdae", "date", 2, 60000, "12:00", group="regular", familiarity="regular")
    return C.Record(case, stops=stops, draw_eligible=draw_eligible, pair_draw=pair_draw)


def test_paired_metrics_count_only_the_regular_half() -> None:
    first = [rec("date", [stop("MEAL", draw=True)], draw_eligible=True) for _ in range(4)]
    regular = [
        _regular([stop("MEAL", draw=True), stop("CAFE", position=2)], pair_draw=True),
        _regular([stop("MEAL"), stop("CAFE", position=2)], pair_draw=True),
        _regular([stop("MEAL"), stop("CAFE", position=2)], pair_draw=True),
        _regular([stop("MEAL"), stop("CAFE", position=2)], pair_draw=False),  # nothing to drop from
    ]
    regular[0].stops[1].shared = True
    for r in regular[1:]:
        for x in r.stops:
            x.novel = True
    results = {r.id: r for r in C.evaluate_all([*first, *regular])}
    # the first-visit numbers never see the regular half
    assert results["draw_rate"].value == 1.0 and results["draw_rate"].n == 4
    assert results["clean_rate"].n == 4
    # one regular course of the three whose pair had a draw still has one: 1/3 of the first's
    assert results["regular_draw_rate"].value == pytest.approx(1 / 3, abs=1e-4)
    assert results["regular_draw_rate"].passed
    assert results["regular_overlap_rate"].value == pytest.approx(1 / 8)
    assert results["regular_novelty_rate"].value == pytest.approx(6 / 8)
    assert regular[1].case.key.endswith("|자주") and regular[1].case.first_key == first[0].case.key


def test_a_regular_record_marks_what_is_new_and_what_it_shares() -> None:
    at = SUNDAY_6PM
    fresh = place(name="새가게", opened_on=date(2026, 3, 1))
    listed = place(name="관광식당", is_curated=True)

    def s(position: int, p: PlaceCandidate) -> StopResult:
        return StopResult(
            position=position, role=p.course_role, place=p, arrive_at=at, leave_at=at + timedelta(minutes=60),
            est_price=20000, travel_min_from_prev=5, distance_m_from_prev=300, score=0.7, score_breakdown={},
            congestion=None, slot_budget=20000.0,
        )  # fmt: skip

    course = CourseResult(
        label="추천", template_id=1, stops=[s(1, fresh), s(2, listed)], total_price=40000, total_travel_min=5,
        total_distance_m=300, duration_min=120, score=0.7, objective=0.7, optimizer="none",
    )  # fmt: skip
    pair = rec("date", [stop("MEAL", "관광 식당")])
    pair.stops[0].place_id = "another-record"
    case = C.Case("seoul-hongdae", "date", 2, 60000, "18:00", group="regular", familiarity="regular")
    ctx = context(60000, familiarity="regular")
    r = C.record_from(case, SimpleNamespace(name="홍대"), ctx, course, RULES, pair)
    assert [x.novel for x in r.stops] == [True, False]
    # the same sign under another record is still the place they have been to
    assert [x.shared for x in r.stops] == [False, True]
    assert r.pair_draw is False
