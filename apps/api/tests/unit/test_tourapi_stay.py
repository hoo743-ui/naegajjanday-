"""Lodging mapping. Names are made-up syllables / English on purpose: no real place may be spelled out in
Python, and the mapping must not depend on one."""

from __future__ import annotations

import json
from pathlib import Path

from app.core.config import API_ROOT
from app.infra.ingestion.bulk import tourapi_stay as S
from app.infra.ingestion.bulk.common import BulkReport

RULES = S.load_rules()
PHOTO = "http://tong.visitkorea.or.kr/cms/resource/1/room.jpg"


def item(**over: object) -> dict[str, object]:
    base: dict[str, object] = {
        "contentid": "900001",
        "contenttypeid": "32",
        "title": "Gana Dara Inn",
        "lclsSystm3": "AC010100",
        "cat3": "",
        "mapx": "128.0001",
        "mapy": "36.0001",
        "addr1": "Mado Basa-gu Ajaro 1",
        "addr2": "",
        "tel": "000-000-0000",
        "firstimage": PHOTO,
        "firstimage2": "",
        "cpyrhtDivCd": "Type3",
    }
    return {**base, **over}


def test_classification_code_decides_the_category() -> None:
    expect = {
        "AC010100": "stay.hotel",
        "AC020100": "stay.resort",
        "AC020200": "stay.hotel",
        "AC030100": "stay.pension",
        "AC030200": "stay.hanok",
        "AC030300": "stay.pension",
        "AC030400": "stay.guesthouse",
        "AC040100": "stay.motel",
        "AC060100": "stay.guesthouse",
        "AC060200": "stay.guesthouse",
        "VE050200": "stay.resort",
    }
    for code, category in expect.items():
        assert S.category_for(item(lclsSystm3=code), "Gana", RULES) == category, code


def test_campsites_and_training_centres_are_not_lodging() -> None:
    for code in ("AC050100", "VE100200"):
        assert S.category_for(item(lclsSystm3=code), "Gana", RULES) is None
        place, reason = S.to_stay(item(lclsSystm3=code), RULES, {})
        assert place is None and reason == "unmapped_category"


def test_fallbacks_old_code_then_name_then_default() -> None:
    assert S.category_for(item(lclsSystm3="", cat3="B02011600"), "Gana", RULES) == "stay.hanok"
    assert S.category_for(item(lclsSystm3="", cat3=""), "Gana Hostel", RULES) == "stay.guesthouse"
    assert S.category_for(item(lclsSystm3="", cat3=""), "Gana", RULES) == "stay"
    # the new classification beats the old one and the name
    assert S.category_for(item(lclsSystm3="AC040100", cat3="B02010100"), "Gana Hotel", RULES) == "stay.motel"


def test_stay_has_photo_over_https_and_never_a_price() -> None:
    place, reason = S.to_stay(item(), RULES, {"Mado": "MD"})
    assert reason is None and place is not None
    assert place.provider == "tourapi" and place.external_id == "900001"
    assert place.category_code == "stay.hotel" and place.sido == "MD" and place.sigungu == "Basa-gu"
    assert place.thumbnail_url == PHOTO.replace("http://", "https://") and place.images == [
        place.thumbnail_url
    ]
    assert place.price_per_person is None and not place.price_is_estimated and not place.is_free
    bare, _ = S.to_stay(item(firstimage=""), RULES, {})
    assert bare is not None and bare.thumbnail_url is None and bare.images == []
    assert bare.content_hash != place.content_hash


def test_bad_rows_are_counted_not_raised() -> None:
    report = BulkReport()
    rows = [
        item(),
        item(contentid="2", mapx="0", mapy="0"),
        item(contentid="3", title=""),
        item(contentid="4", mapx="x"),
        item(contentid="5", lclsSystm3="AC050100"),
    ]
    places = list(S.iter_stays(rows, RULES, {}, report))
    assert [p.external_id for p in places] == ["900001"]
    assert report.read == 5 and report.mapped == 1 and report.skipped == 4
    assert dict(report.skip_reasons) == {"bad_coord": 2, "no_name": 1, "unmapped_category": 1}


def test_every_mapped_category_is_a_seeded_stay_category() -> None:
    seed = json.loads((API_ROOT / "data" / "seed" / "categories.json").read_text(encoding="utf-8"))
    roles = {c["code"]: c["course_role"] for c in seed["categories"]}
    used = {v for table in ("by_lcls", "by_cat3") for v in RULES[table].values() if v}
    used |= {row["category"] for row in RULES["by_name_contains"]} | {RULES["default_category"]}
    assert used and all(roles.get(code) == "STAY" for code in used)
    # lodging must never become a stop of a day course: no template slot may ask for the STAY role
    purposes = json.loads((API_ROOT / "data" / "seed" / "purposes.json").read_text(encoding="utf-8"))
    slot_roles = {s["course_role"] for p in purposes["purposes"] for t in p["templates"] for s in t["slots"]}
    assert "STAY" not in slot_roles


def test_download_uses_the_week_old_cache_without_a_call(tmp_path: Path) -> None:
    (tmp_path / "stay_1.json").write_text(json.dumps([item(), item(contentid="2")]), "utf-8")
    assert S.download("unused-key", tmp_path, "32") == 2  # a network call would fail with this key
