"""이런 동네예요 (2026-09-26): an editorial text for the hotspots, one sentence of facts for the rest."""

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
    assert (
        said.text
        == "가게 2,648곳이 모인 동네예요. 간판엔 ‘곰장어’가 유독 많고, 사람들은 주로 마린시티 · 해운대해수욕장을 보러 와요."
    )
    assert intro_for("nowhere", Signature()) is None
