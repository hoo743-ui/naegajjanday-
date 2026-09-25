"""Neighbourhood signature: what a place is known for, read off shop signs.

Fixtures use made-up syllables on purpose — the project forbids real region or place names in Python
(`test_no_region_or_place_names_are_hardcoded_in_python`), and the logic must not depend on them.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import replace

from app.domain.models import PlaceCandidate, RequestContext
from app.domain.signature import (
    Signature,
    SignatureRules,
    Specialty,
    count_grams,
    focus_pools,
    mark_local,
    pick_specialties,
    place_words,
    rank_sights,
    without,
)
from tests.factories import context, place

RULES = SignatureRules(
    gram_lengths=(2, 3, 4),
    specialty_roles=frozenset({"MEAL"}),
    sight_roles=frozenset({"ATTRACTION"}),
    min_local=3,
    min_outside=5,
    min_lift=3.0,
    max_specialties=3,
    drop_suffixes=("점",),
    admin_suffixes=("시",),
    short_word_min_count=3,
    tag="local",
)
TOWN = "라마"  # the town's own name
DISH = "가나다"  # a three-syllable dish sold under that word across the country
STREET = "바사아"  # a three-syllable street name that exists only here


def _national(dish_elsewhere: int, street_elsewhere: int) -> tuple[Counter[str], int]:
    names = [f"x{i}{DISH}" for i in range(dish_elsewhere)] + [
        f"y{i}{STREET}" for i in range(street_elsewhere)
    ]
    names += [f"z{i}" for i in range(2000)]
    return count_grams(names, RULES.gram_lengths), len(names)


def test_a_word_dense_here_and_still_used_elsewhere_is_the_specialty() -> None:
    local_names = [
        f"{TOWN}{DISH}",
        f"a{DISH}",
        f"b{DISH}",
        f"c{DISH}",
        f"d{STREET}",
        f"e{STREET}",
        f"f{STREET}",
    ]
    own = place_words([f"{TOWN}시"], RULES.admin_suffixes)
    local = count_grams((without(n, own) for n in local_names), RULES.gram_lengths)
    national, shops = _national(dish_elsewhere=40, street_elsewhere=0)
    national.update(local)

    found = pick_specialties(local, len(local_names), national, shops + len(local_names), set(), RULES)

    words = [s.word for s in found]
    assert DISH in words  # "<town><dish>" counted as the dish: the town's name was taken out first
    assert STREET not in words  # as dense, but nobody outside uses it: a place, not a thing
    assert all(DISH not in w or w == DISH for w in words)  # no slices of the dish alongside it


def test_toponyms_and_branch_suffixes_never_qualify() -> None:
    local = Counter({DISH: 6, STREET: 6, f"{DISH[:2]}점": 6})
    national = Counter({DISH: 60, STREET: 60, f"{DISH[:2]}점": 60})
    found = pick_specialties(local, 50, national, 50_000, {STREET}, RULES)
    assert [s.word for s in found] == [DISH]


def test_a_slice_of_a_longer_word_is_dropped() -> None:
    piece = DISH[:2]
    local = Counter({DISH: 10, piece: 10})  # the slice never occurs without the third syllable
    national = Counter({DISH: 100, piece: 100})
    found = pick_specialties(local, 100, national, 100_000, set(), RULES)
    assert [s.word for s in found] == [DISH]


def test_sights_are_ranked_by_how_many_shops_borrow_their_name() -> None:
    sights = [(1, f"{TOWN} quiet hill", False), (2, f"{TOWN} {STREET}", True), (3, f"{STREET}", True)]
    shops = [f"k{STREET}", f"m{STREET}", f"n{TOWN}"]
    ranked = rank_sights(sights, shops, RULES, region_words={TOWN})
    assert ranked[0].place_id == 2  # matched by its own word, not by the town's name
    assert ranked[0].mentions == 2
    assert 3 not in [s.place_id for s in ranked]  # the same sight under a shorter name is listed once


def _cand(pid: int, name: str, role: str) -> PlaceCandidate:
    return place(role, id=pid, name=name)


def _ctx(**kw: object) -> RequestContext:
    return context(**kw)


def test_mark_local_flags_specialty_shops_and_landmark_sights() -> None:
    meal, other, sight = (
        _cand(1, f"q{DISH}", "MEAL"),
        _cand(2, "plain", "MEAL"),
        _cand(9, "hill", "ATTRACTION"),
    )
    mark_local([meal, other, sight], _ctx(local_words=(DISH,), landmark_ids=frozenset({9})), RULES)
    assert (meal.local_score, meal.local_word, meal.tags.get("local")) == (1.0, DISH, 1.0)
    assert other.local_score == 0 and "local" not in other.tags
    assert sight.local_score == 1.0


def test_focus_gives_the_first_slot_that_can_serve_it_to_the_specialty_alone() -> None:
    pools = {1: [_cand(1, f"q{DISH}", "MEAL"), _cand(2, "plain", "MEAL")], 2: [_cand(3, f"r{DISH}", "MEAL")]}
    ctx = _ctx(focus_request=DISH)
    out = focus_pools(pools, ctx, RULES)
    assert [c.id for c in out[1]] == [1]
    assert [c.id for c in out[2]] == [3]  # later slots are left alone
    assert ctx.focus == DISH
    assert focus_pools(pools, _ctx(), RULES) == pools  # nothing stands out: nothing changes


def test_a_pick_that_does_not_fit_is_never_swapped_silently() -> None:
    other = DISH[::-1]
    pools = {1: [_cand(1, f"q{other}", "MEAL"), _cand(2, f"r{other}", "MEAL")]}  # the pick was priced out
    pricey = place("MEAL", price=22_500, id=7, name=f"s{DISH}")
    ctx = _ctx(focus_request=DISH, auto_focus_words=(DISH, other))
    out = focus_pools(pools, ctx, RULES, unfiltered=[pricey])
    assert [c.id for c in out[1]] == [1, 2]  # the next specialty still gets its stop
    assert (ctx.focus, ctx.focus_from_price) == (other, 22_500)  # and the engine can say what the pick costs


def test_a_strong_specialty_claims_a_stop_unasked_only_when_enough_shops_can_serve_it() -> None:
    two = {1: [_cand(1, f"q{DISH}", "MEAL"), _cand(2, f"r{DISH}", "MEAL"), _cand(3, "plain", "MEAL")]}
    ctx = _ctx(auto_focus_words=(DISH,))
    assert [c.id for c in focus_pools(two, ctx, RULES)[1]] == [1, 2]
    assert ctx.focus == DISH  # recorded, so the page can say what the course was built around

    one = {1: [_cand(4, f"q{DISH}", "MEAL"), _cand(5, "plain", "MEAL")]}
    ctx = _ctx(auto_focus_words=(DISH,))
    assert focus_pools(one, ctx, RULES) == one  # a single shop is not a choice
    assert ctx.focus is None


def test_signature_payload_round_trip() -> None:
    local = Counter({DISH: 6})
    found = pick_specialties(local, 50, Counter({DISH: 60}), 50_000, set(), RULES)
    signature = Signature(specialties=found, sights=rank_sights([(1, "abc hill", True)], [], RULES), shops=50)
    assert Signature.from_payload(signature.to_payload()) == signature
    assert Signature.from_payload(None) == Signature()


def test_what_people_come_for_pulls_harder_than_what_the_signs_say() -> None:
    rules = replace(RULES, local_pull=0.05, draw_pull=0.12)
    draw, sign, sight, famous = (
        _cand(1, "원조닭갈비", "MEAL"),
        _cand(2, f"q{DISH}", "MEAL"),
        _cand(8, "hill", "ATTRACTION"),
        _cand(9, "lake", "ATTRACTION"),
    )
    ctx = _ctx(
        local_words=("닭갈비", DISH),
        landmark_ids=frozenset({8, 9}),
        draw_words=frozenset({"닭갈비"}),
        draw_ids=frozenset({9}),
    )
    mark_local([draw, sign, sight, famous], ctx, rules)
    assert (draw.local_pull, sign.local_pull, sight.local_pull, famous.local_pull) == (0.12, 0.05, 0.05, 0.12)


def test_a_curated_draw_is_always_strong_and_noise_words_are_dropped() -> None:
    signature = Signature(
        specialties=(Specialty("닭갈비", 3, 0.0, curated=True), Specialty("에프엔비", 90, 40.0)),
    )
    assert [s.word for s in signature.strong(1_000.0).specialties] == ["닭갈비"]
    assert [s.word for s in signature.without_words({"에프엔비"}).specialties] == ["닭갈비"]
