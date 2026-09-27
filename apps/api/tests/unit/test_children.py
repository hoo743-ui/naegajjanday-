"""아이 수 (docs/64 R18, 창업자 "4 아이 인원 받자") — the pass criteria ①–④ in code.

① no `children` → the assumption as before (가족 · 아이와 = 어른 둘, 나머지 아이)
② children = k → admission = (인원 − k) × 어른 + k × 아이
③ children > 0 → no bar, no 술자리 anywhere, the kids evening end
④ children ≥ 인원 → refused (422 at the API: tests/integration/test_children.py)
"""

from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from app.domain.models import GeoPoint
from app.domain.recommendation.children import (
    ALL_ROLES,
    DRINK_TAG,
    apply_children,
    child_scene,
    vetoed_for,
    with_children,
)
from app.domain.recommendation.style import extra_roles, extra_unavailable, resolve_scene, styled_never
from app.domain.recommendation.ticketed import parse, ticketed_venues
from app.schemas.course import CourseGenerateRequest
from tests.factories import context, place

GATE = GeoPoint(37.43556, 127.02384)
LAND = parse(
    {
        "party": {"child_scenes": {"family": ["kids"]}, "adults_of_family": 2},
        "venues": [
            {
                "key": "land",
                "name": "테스트랜드",
                "place_ids": [5],
                "gate": [GATE.lat, GATE.lng],
                "admission": {"adult": 52000, "child": 43000, "as_of": "2026-09", "basis": "공식"},
            }
        ],
    }
)
AT = context().start_at.replace(month=10, day=3, hour=11)


def _land():  # type: ignore[no-untyped-def]
    return LAND.mark(place("ACTIVITY", "activity", 12000, id=5, lat=GATE.lat, lng=GATE.lng))


# ── ① absent: exactly the assumption as before ──────────────────────────────────────────────


@pytest.mark.parametrize("party", range(1, 8))
@pytest.mark.parametrize(
    ("purpose", "scene"), [("family", "kids"), ("family", "parents"), ("family", "adults"), ("date", None)]
)
def test_absent_children_is_the_old_assumption(purpose: str, scene: str | None, party: int) -> None:
    old = (
        (min(2, max(1, party - 1)), party - min(2, max(1, party - 1)))
        if (purpose, scene) == ("family", "kids")
        else (party, 0)
    )
    assert LAND.party_of(purpose, scene, party) == old
    assert LAND.party_of(purpose, scene, party, None) == old


def test_absent_children_keeps_the_old_price_and_line() -> None:
    land = _land()
    LAND.price([land], context(budget_total=400000, party_size=3, purpose_code="family", scene="kids", start_at=AT))
    assert LAND.party_price(land, 3) == 2 * 52000 + 43000 == 147000
    assert land.ticket_split is None
    assert LAND.line(land) == "입장권 어른 52,000 · 어린이 43,000원(공식 2026-09)"  # as before R18


def test_absent_children_leaves_the_context_alone() -> None:
    ctx = context(purpose_code="family", scene="kids")
    before = (dict(ctx.never_tags_by_role), ctx.soft_end_min, ctx.children)
    apply_children(ctx, None)
    assert (dict(ctx.never_tags_by_role), ctx.soft_end_min, ctx.children) == before
    assert vetoed_for(None) == frozenset() and not with_children(None)


# ── ② the admission is the asked split ───────────────────────────────────────────────────────


@pytest.mark.parametrize(("party", "k"), [(3, 0), (3, 1), (3, 2), (4, 3), (5, 2), (1, 0)])
def test_asked_children_pay_the_child_price(party: int, k: int) -> None:
    land = _land()
    ctx = context(
        budget_total=900000, party_size=party, purpose_code="family", scene="kids", start_at=AT, children=k
    )
    LAND.price([land], ctx)
    assert LAND.party_price(land, party) == (party - k) * 52000 + k * 43000
    assert land.ticket_split == (party - k, k)
    assert land.price * party >= LAND.party_price(land, party)  # per person rounds up, never under


def test_asked_children_hold_whatever_the_purpose() -> None:
    # the head count said wins over the scene's assumption both ways
    assert LAND.party_of("date", None, 3, 1) == (2, 1)
    assert LAND.party_of("family", "kids", 4, 0) == (4, 0)
    assert LAND.party_of("family", "kids", 4, 3) == (1, 3)


def test_the_card_shows_the_real_split() -> None:
    land = _land()
    LAND.price([land], context(budget_total=400000, party_size=3, purpose_code="family", start_at=AT, children=2))
    assert LAND.line(land) == "입장권 어른 1 · 어린이 2 = 138,000원(공식 2026-09)"
    none = _land()
    LAND.price([none], context(budget_total=400000, party_size=3, purpose_code="family", start_at=AT, children=0))
    assert LAND.line(none) == "입장권 어른 3 = 156,000원(공식 2026-09)"
    assert len(LAND.line(land) or "") <= 40  # one card subtitle


def test_a_saved_course_restores_the_asked_split() -> None:
    land = _land()
    request = {"purposes": ["family"], "scene": "kids", "children": 2}
    LAND.restore(land, 138000, 3, request, date(2026, 10, 3))
    assert land.ticket_children == 2 and land.ticket_split == (1, 2)
    assert LAND.party_price(land, 3) == 138000
    assert LAND.line(land) == "입장권 어른 1 · 어린이 2 = 138,000원(공식 2026-09)"
    old = _land()  # a course saved before R18: the assumption, the old line
    LAND.restore(old, 147000, 3, {"purposes": ["family"], "scene": "kids"}, date(2026, 10, 3))
    assert old.ticket_children == 1 and old.ticket_split is None


def test_the_shipped_seoulland_for_one_adult_and_two_children() -> None:
    venue = ticketed_venues().by_key("seoulland")
    assert venue is not None and venue.name == "서울랜드"
    admission = venue.admission_on(date(2026, 10, 3))
    assert admission.for_party(1, 2) == 1 * 52000 + 2 * 43000


# ── ③ a day with children: no bar, no 술자리, home by the kids hour ─────────────────────────


@pytest.mark.parametrize("scene", ["kids", "parents", "adults"])
def test_children_keep_the_drink_out_of_every_stop(scene: str) -> None:
    ctx = context(purpose_code="family", scene=scene)
    key, rules = resolve_scene("family", scene)
    for tag, roles in styled_never(rules).items():
        ctx.never_tags_by_role[tag] = ctx.never_tags_by_role.get(tag, frozenset()) | roles
    for tag in rules.get("allow_tags") or ():  # 어른끼리: the 술자리 allowance
        ctx.never_tags_by_role.pop(tag, None)
    apply_children(ctx, 1)
    assert ctx.children == 1
    assert ctx.never_tags_by_role[DRINK_TAG] >= ALL_ROLES
    assert vetoed_for(1) == frozenset({"BAR"})
    end_by = str(child_scene()["end_by"])
    assert ctx.soft_end_min == int(end_by[:2]) * 60 + int(end_by[3:])


def test_children_on_another_purpose_still_end_early_and_start_in_the_evening() -> None:
    ctx = context(purpose_code="friends")
    apply_children(ctx, 2)
    assert ctx.soft_end_min == 20 * 60 + 30 and ctx.never_tags_by_role[DRINK_TAG] >= ALL_ROLES
    assert child_scene().get("earlier_start") == "17:30"  # the service moves a night start to it


def test_a_drink_asked_for_with_children_says_why() -> None:
    bar = extra_roles()["BAR"]
    warning = extra_unavailable("BAR", bar, vetoed=True, children=True)
    assert warning["detail"] == "아이와 함께라서 술 한잔은 넣지 않았어요." and warning["meta"]["vetoed"]
    assert extra_unavailable("BAR", bar, vetoed=True)["detail"] == bar["vetoed"]


def test_zero_children_is_no_day_with_children() -> None:
    ctx = context(purpose_code="friends")
    apply_children(ctx, 0)
    assert ctx.children == 0 and DRINK_TAG not in ctx.never_tags_by_role and ctx.soft_end_min is None
    assert vetoed_for(0) == frozenset()


# ── ④ at least one adult ──────────────────────────────────────────────────────────────────────

BODY = {"region": "x", "purpose": "family", "party_size": 3, "budget_total": 100000}


@pytest.mark.parametrize("k", [3, 4, 19])
def test_children_must_leave_an_adult(k: int) -> None:
    with pytest.raises(ValidationError) as err:
        CourseGenerateRequest.model_validate({**BODY, "children": k})
    [e] = err.value.errors()
    assert e["loc"] == ("children",) and "어른이 한 명은 있어야 해요" in e["msg"]


def test_children_under_the_party_size_are_accepted() -> None:
    assert CourseGenerateRequest.model_validate({**BODY, "children": 2}).children == 2
    assert CourseGenerateRequest.model_validate({**BODY, "children": 0}).children == 0
    assert CourseGenerateRequest.model_validate(BODY).children is None
    with pytest.raises(ValidationError):
        CourseGenerateRequest.model_validate({**BODY, "children": -1})
