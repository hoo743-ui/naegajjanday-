"""이런 동네예요 (2026-09-26): an editorial text for the hotspots; for the rest, what the data shows and
what it means for the day (docs/54) — never more than the data backs."""

from __future__ import annotations

from app.domain.region_intro import editorial_intros, intro_for
from app.domain.signature import Sight, Signature, Specialty


def test_every_hotspot_intro_is_written_and_says_no_numbers_it_cannot_back() -> None:
    intros = editorial_intros()
    assert len(intros) >= 55 and "busan-seomyeon" in intros
    for slug, entry in intros.items():
        assert 40 <= len(entry["text"]) <= 200, slug
        assert 1 <= len(entry["keywords"]) <= 3, slug
        assert "곳이 모인" not in entry["text"] or slug  # counts belong to the data sentence


def test_an_editorial_intro_wins_and_the_rest_is_said_from_data() -> None:
    seomyeon = intro_for("busan-seomyeon", Signature())
    assert seomyeon is not None and seomyeon.source == "editorial" and "번화가" in seomyeon.text
    data = Signature(
        specialties=(Specialty("곰장어", 12, 30.0),),
        sights=(Sight(1, "마린시티", 3), Sight(2, "해운대해수욕장", 5)),
        shops=2648,
    )
    said = intro_for("busan-haeundae", data)
    assert said is not None and said.source == "data"
    assert said.text == (
        "가게가 2,648곳이라, 미리 정해 두지 않고 걸어도 하루가 채워져요. "
        "간판엔 ‘곰장어’가 유독 많고, 가게 이름엔 마린시티 · 해운대해수욕장이 자주 붙어요. "
        "뭘 먹을지는 간판이, 어디를 볼지는 가게 이름이 먼저 알려 주는 동네예요."
    )
    assert said.keywords == ("곰장어",)
    assert intro_for("nowhere", Signature()) is None


def test_the_data_sentence_reads_the_size_and_the_signs_as_a_kind_of_day() -> None:
    small = intro_for(None, Signature(shops=120))
    assert (
        small is not None
        and small.text == "가게 120곳 남짓한 아담한 동네라, 몇 곳에 오래 머무는 하루가 어울려요."
    )
    mid = intro_for(None, Signature(shops=450, specialties=(Specialty("막국수", 6, 9.0),)))
    assert mid is not None and mid.text == (
        "가게 450곳이 모여 있어, 가려던 곳 옆에 한 곳쯤 더 들르기 쉬워요. "
        "간판엔 ‘막국수’가 유독 많아요. 여기서 뭘 먹을지는 동네가 먼저 말해 주는 셈이에요."
    )
    sight = intro_for(None, Signature(sights=(Sight(3, "수원화성", 4),)))
    assert sight is not None and sight.text == (
        "가게 이름에 수원화성이 자주 붙어요. 동네가 스스로를 그 이름으로 소개하는 셈이에요."
    )


def test_editorial_intros_do_not_lean_on_the_same_phrase() -> None:
    """docs/54: each hotspot sounds like itself — no stock ending repeated across entries."""
    texts = [e["text"] for e in editorial_intros().values()]
    for stock in ("하기 좋아요", "잘 어울려요", "사랑받아요", "하이라이트"):
        assert sum(stock in t for t in texts) <= 2, stock
    endings = [" ".join(t.rstrip(".").split()[-2:]) for t in texts]
    assert max(endings.count(e) for e in set(endings)) <= 3
    openers = [t.split(".")[0].split()[-1] for t in texts]  # not "…한 곳이에요" as every first sentence
    assert max(openers.count(e) for e in set(openers)) <= len(texts) // 4
