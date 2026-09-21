from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sqlalchemy import delete, func, select

from app.core.config import API_ROOT
from app.core.deps import Container
from app.infra.db.models import Category, Place, PlaceSource, PlaceStats
from app.infra.ingestion.bulk.common import in_korea, load_json
from app.infra.ingestion.bulk.price_prior import PricePrior
from app.infra.ingestion.bulk.venues import build_place, load_spec, load_stadiums, pick_existing, similarity
from app.infra.ingestion.dedupe import ExistingPlace
from app.infra.tagging import get_tag_rules

SPEC: dict[str, Any] = {
    "provider": "kbo_stadium",
    "category": "activity.stadium",
    "schedule_url": "https://example.test/schedule",
    "_attribution": "© OpenStreetMap contributors",
    "description_template": "{clubs} 홈구장. 경기가 있는 날만 의미가 있어요 · 오늘 경기 확인: {schedule_url}",
    "game_day_notice": "경기가 있는 날만 의미가 있어요 · 오늘 경기 확인",
    "merge": {"radius_m": 200, "min_similarity": 0.8, "roles": ["ACTIVITY", "ATTRACTION", "CULTURE"]},
}
ENTRY: dict[str, Any] = {
    "id": "test-dome",
    "name": "테스트 스카이돔",
    "aliases": ["테스트돔 야구장"],
    "clubs": ["가나 팀", "다라 팀"],
    "sido": "서울특별시",
    "sigungu": "마포구",
    "road_address": "테스트로 1",
    "lat": 37.5572,
    "lng": 126.9245,
    "coord_source": "manual",
}


class TestDataFile:
    def test_every_club_has_a_stadium_with_usable_facts(self) -> None:
        spec = load_spec()
        stadiums = spec["stadiums"]
        assert len({s["id"] for s in stadiums}) == len(stadiums)
        assert sum(len(s["clubs"]) for s in stadiums) == 10
        assert spec["schedule_url"] == "https://www.koreabaseball.com/schedule/schedule.aspx"
        assert spec["_attribution"] == "© OpenStreetMap contributors"
        for s in stadiums:
            assert (
                in_korea(s["lat"], s["lng"]) and s["road_address"] and s["coord_source"] in {"osm", "manual"}
            )

    def test_category_price_and_tag_are_wired_in_data(self) -> None:
        cats = json.loads((API_ROOT / "data" / "seed" / "categories.json").read_text("utf-8"))["categories"]
        cat = next(c for c in cats if c["code"] == "activity.stadium")
        assert (cat["course_role"], cat["default_stay_min"], cat["parent"]) == ("ACTIVITY", 180, "activity")
        prior = PricePrior.from_data(load_json("price_prior.json"), load_json("regions_kr.json"))
        assert prior.base("activity.stadium") != prior.base("activity")
        tags = get_tag_rules().derive(
            category_code="activity.stadium",
            name="아무 구장",
            course_role="ACTIVITY",
            has_measured_price=False,
        )
        assert tags["야구장"] == 1.0 and "야구장" in get_tag_rules().visible(tags)


class TestBuildPlace:
    def test_place_carries_what_the_ui_needs_and_never_claims_a_game(self) -> None:
        prior = PricePrior.from_data(load_json("price_prior.json"), load_json("regions_kr.json"))
        p = build_place(ENTRY, SPEC, prior)
        assert (p.provider, p.external_id, p.category_code) == (
            "kbo_stadium",
            "test-dome",
            "activity.stadium",
        )
        assert p.description == (
            "가나 팀 · 다라 팀 홈구장. 경기가 있는 날만 의미가 있어요 · 오늘 경기 확인: https://example.test/schedule"
        )
        assert p.price_per_person == prior.estimate("activity.stadium", "서울특별시") and p.price_is_estimated
        assert p.raw["schedule_url"] == "https://example.test/schedule" and p.raw["game_day_only"] is True
        assert p.hours == [] and p.merge_into_place_id is None

    def test_without_a_prior_there_is_no_price(self) -> None:
        p = build_place(ENTRY, SPEC, None)
        assert p.price_per_person is None and p.price_is_estimated is False


class TestPickExisting:
    def _pick(self, *cands: ExistingPlace) -> ExistingPlace | None:
        return pick_existing(ENTRY, cands, radius_m=200, min_similarity=0.8)

    def test_same_name_nearby_is_the_same_place(self) -> None:
        cand = ExistingPlace(1, "테스트스카이돔", 37.5580, 126.9250)
        assert self._pick(cand) == cand

    def test_alias_counts(self) -> None:
        cand = ExistingPlace(2, "테스트돔야구장", 37.5575, 126.9245)
        assert self._pick(cand) == cand

    def test_a_shop_named_after_the_stadium_is_not_the_stadium(self) -> None:
        assert self._pick(ExistingPlace(3, "으뜸탁구장테스트스카이돔점", 37.5573, 126.9246)) is None
        assert similarity("으뜸탁구장테스트스카이돔점", "테스트 스카이돔") < 0.8

    def test_same_name_far_away_is_somewhere_else(self) -> None:
        assert self._pick(ExistingPlace(4, "테스트 스카이돔", 37.5600, 126.9245)) is None  # ≈ 310 m

    def test_best_name_wins(self) -> None:
        exact = ExistingPlace(5, "테스트 스카이돔", 37.5573, 126.9245)
        close = ExistingPlace(6, "테스트 스카이돔 2", 37.5572, 126.9245)
        assert self._pick(close, exact) == exact


def _write_spec(tmp_path: Path, entries: list[dict[str, Any]]) -> Path:
    path = tmp_path / "stadiums.json"
    path.write_text(
        json.dumps({**SPEC, "provider": "test_stadium", "stadiums": entries}, ensure_ascii=False), "utf-8"
    )
    return path


async def test_loader_inserts_once_then_merges_into_an_existing_place(
    container: Container, tmp_path: Path
) -> None:
    logs: list[str] = []
    fresh = {**ENTRY, "id": "fresh", "name": "테스트 새구장", "aliases": [], "lat": 37.6001, "lng": 126.8501}
    path = _write_spec(tmp_path, [fresh])
    first = await load_stadiums(container.db, path=path, log=logs.append)
    again = await load_stadiums(container.db, path=path, log=logs.append)
    assert (first.created, first.merged) == (1, 0) and (again.created, again.unchanged) == (0, 1)

    async with container.db.sessionmaker() as s:
        row = (
            await s.execute(
                select(Place, Category.code)
                .join(Category, Category.id == Place.category_id)
                .join(PlaceSource, PlaceSource.place_id == Place.id)
                .where(PlaceSource.provider == "test_stadium", PlaceSource.external_id == "fresh")
            )
        ).one()
        place, code = row
        assert code == "activity.stadium" and place.status == "approved" and place.price_is_estimated
        assert "오늘 경기 확인" in (place.description or "")
        # pretend the nationwide data already had this stadium under another category
        other = await s.scalar(select(Category.id).where(Category.code == "attraction.park"))
        place.category_id = other
        place.description = None
        await s.execute(
            PlaceSource.__table__.update()
            .where(PlaceSource.provider == "test_stadium")
            .values(provider="someone_else")
        )
        await s.commit()
        place_id = place.id

    twin = {**fresh, "id": "twin", "name": "테스트새구장"}
    merged = await load_stadiums(container.db, path=_write_spec(tmp_path, [twin]), log=logs.append)
    assert (merged.created, merged.merged) == (0, 1) and any(line.startswith("merge") for line in logs)
    async with container.db.sessionmaker() as s:
        code, description = (
            await s.execute(
                select(Category.code, Place.description)
                .join(Place, Place.category_id == Category.id)
                .where(Place.id == place_id)
            )
        ).one()
        assert code == "activity.stadium" and "오늘 경기 확인" in description  # promoted, not duplicated
        count = await s.scalar(
            select(func.count()).select_from(Place).where(Place.name.like("테스트%새구장"))
        )
        assert count == 1
        # leave the shared test DB as we found it
        await s.execute(delete(PlaceSource).where(PlaceSource.place_id == place_id))
        await s.execute(delete(PlaceStats).where(PlaceStats.place_id == place_id))
        await s.execute(delete(Place).where(Place.id == place_id))
        await s.commit()
