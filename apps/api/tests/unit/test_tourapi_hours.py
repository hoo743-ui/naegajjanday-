"""docs/55: 영업시간 적재기 — 우선순위 · 이어받기 · 한도 · 공연장 · 내보내기/불러오기 (네트워크 없이, 버리는 SQLite)."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime, time
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import delete, select

from app.core.config import API_ROOT, Settings
from app.infra import api_usage
from app.infra.db.models import ApiUsage, Category, OpeningHour, Place, PlaceSource, Region
from app.infra.db.session import Database
from app.infra.ingestion.bulk import tourapi_hours as hours
from app.infra.ingestion.config_loader import load_config

HOTSPOT = (37.5740, 126.9900)  # seoul-ikseon-jongno
FAR = (35.1000, 129.0300)

INTROS = {
    "1": {
        "contenttypeid": "14",
        "usetimeculture": "10:00~18:00 (입장마감 17:30)",
        "restdateculture": "매주 월요일",
    },
    "2": {
        "contenttypeid": "12",
        "usetime": "[3월~10월] 09:00~18:00 (입장마감 17:00)[11월~2월] 09:00~17:30 (입장마감 16:30)",
        "restdate": "매주 화요일 (단, 화요일이 공휴일인 경우 개방)",
    },
    "3": {
        "contenttypeid": "14",
        "usetimeculture": "09:00~18:00",
        "restdateculture": "매주 월요일",
    },  # theatre
    "4": {"contenttypeid": "12", "usetime": "점포별 상이", "restdate": "점포별 상이"},
    "5": {"contenttypeid": "12", "usetime": "상시 개방", "restdate": "연중무휴"},
}


@pytest_asyncio.fixture
async def db(tmp_path: Path) -> AsyncIterator[Database]:
    settings = Settings(
        _env_file=None,  # type: ignore[call-arg]
        app_env="test",
        database_url=f"sqlite+aiosqlite:///{(tmp_path / 'hours.db').as_posix()}",
    )
    database = Database(settings)
    await database.create_all()
    async with database.sessionmaker() as session:
        await load_config(session, API_ROOT / "data" / "seed")
        region = Region(
            slug="seoul-ikseon-jongno",
            name="익선동 · 종로",
            level=3,
            center_lat=HOTSPOT[0],
            center_lng=HOTSPOT[1],
            radius_m=1200,
            status="active",
        )
        session.add(region)
        await session.flush()
        cats = {c.code: c.id for c in (await session.scalars(select(Category))).all()}
        rows = [  # content id, name, category, where, popularity order
            ("1", "종로 박물관", "culture.museum", HOTSPOT),
            ("2", "종로 궁궐", "attraction.landmark", HOTSPOT),
            ("3", "종로 소극장", "culture.cinema", HOTSPOT),
            ("4", "종로 시장", "attraction.market", HOTSPOT),
            ("5", "먼 공원", "attraction.park", FAR),
        ]
        for cid, name, code, (lat, lng) in rows:
            place = Place(
                region_id=region.id, category_id=cats[code], name=name, lat=lat, lng=lng, status="approved"
            )
            session.add(place)
            await session.flush()
            session.add(
                PlaceSource(
                    place_id=place.id,
                    provider="tourapi",
                    external_id=cid,
                    raw={"contenttypeid": INTROS[cid]["contenttypeid"]},
                    fetched_at=datetime.now(UTC),
                    content_hash="x",
                )
            )
        await session.commit()
    try:
        yield database
    finally:
        await database.dispose()


def fake_tourapi(
    calls: list[str], remaining: list[int], *, exhausted_after: int | None = None
) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        cid = request.url.params["contentId"]
        calls.append(cid)
        if exhausted_after is not None and len(calls) > exhausted_after:
            return httpx.Response(200, text="<returnReasonCode>22</returnReasonCode>")
        remaining[0] -= 1
        item = {"contentid": cid, **INTROS[cid]}
        body = {"response": {"header": {"resultCode": "0000"}, "body": {"items": {"item": [item]}}}}
        return httpx.Response(200, json=body, headers={"x-ratelimit-remaining": str(remaining[0])})

    return httpx.MockTransport(handler)


async def week_of(db: Database, name: str) -> list[str]:
    async with db.sessionmaker() as session:
        pid = await session.scalar(select(Place.id).where(Place.name == name))
        rows = (await session.scalars(select(OpeningHour).where(OpeningHour.place_id == pid))).all()
    return [
        "휴" if h.is_closed else f"{h.open_time:%H:%M}-{h.close_time:%H:%M}"
        for h in sorted(rows, key=lambda h: h.dow)
    ]


async def test_queue_order_hotspot_culture_first(db: Database) -> None:
    async with db.sessionmaker() as session:
        queue = await hours.targets(session)
    assert [t.content_id for t in queue][:2] == ["1", "3"]  # hotspot CULTURE
    assert queue[-1].content_id == "5"  # outside every hotspot → last
    assert all(t.hotspot for t in queue[:-1])


async def test_run_resumes_stores_hours_and_keeps_raw_text(db: Database) -> None:
    calls: list[str] = []
    remaining = [900]
    quiet = lambda _m: None  # noqa: E731
    first = await hours.run(db, "key", limit=2, log=quiet, transport=fake_tourapi(calls, remaining))
    assert calls == ["1", "3"] and first.fetched == 2
    assert first.parsed == 1 and first.ambiguous == 1  # the theatre's box-office hours are not stored
    assert await week_of(db, "종로 박물관") == ["휴", *["10:00-18:00"] * 6]
    assert await week_of(db, "종로 소극장") == []

    second = await hours.run(db, "key", limit=10, log=quiet, transport=fake_tourapi(calls, remaining))
    assert calls[2:] == ["2", "4", "5"]  # continues where it stopped, nothing twice
    assert (second.parsed, second.ambiguous) == (2, 1)
    assert await week_of(db, "종로 궁궐") == ["09:00-17:00", "휴", *["09:00-17:00"] * 5]
    assert await week_of(db, "먼 공원") == ["00:00-00:00"] * 7
    assert await week_of(db, "종로 시장") == []

    async with db.sessionmaker() as session:
        raw = await session.scalar(select(PlaceSource.raw).where(PlaceSource.external_id == "4"))
    assert raw is not None
    assert raw["intro"]["status"] == "ambiguous"
    assert raw["intro"]["fields"]["usetime"] == "점포별 상이"  # the text is kept
    assert raw["contenttypeid"] == "12"  # the list operation's fields survive

    third = await hours.run(db, "key", limit=10, log=quiet, transport=fake_tourapi(calls, remaining))
    assert third.queued == 0 and len(calls) == 5


async def test_quota_hook_limits_the_run(db: Database) -> None:
    async with db.sessionmaker() as session:
        session.add(ApiUsage(provider="tourapi", day=api_usage.today(), calls=897, errors=0))
        await session.commit()
    calls: list[str] = []
    report = await hours.run(
        db, "key", limit=900, reserve=100, log=lambda _m: None, transport=fake_tourapi(calls, [900])
    )
    assert len(calls) == report.calls == 3  # 1000 - 897 - 100

    async with db.sessionmaker() as session:
        row = await session.get(ApiUsage, ("tourapi", api_usage.today()))
        assert row is not None
        row.calls = 950
        await session.commit()
    nothing = await hours.run(db, "key", limit=900, log=lambda _m: None, transport=fake_tourapi(calls, [900]))
    assert nothing.calls == 0 and nothing.stopped == "no quota left today"


async def test_stops_when_tourapi_says_the_quota_is_gone(db: Database) -> None:
    calls: list[str] = []
    report = await hours.run(
        db, "key", limit=10, log=lambda _m: None, transport=fake_tourapi(calls, [900], exhausted_after=1)
    )
    assert report.fetched == 1 and report.stopped and "quota" in report.stopped


async def test_stops_at_the_reserve_the_header_reports(db: Database) -> None:
    calls: list[str] = []
    report = await hours.run(
        db, "key", limit=10, reserve=100, log=lambda _m: None, transport=fake_tourapi(calls, [102])
    )
    assert len(calls) == 2 and report.stopped


async def test_existing_hours_from_elsewhere_are_kept(db: Database) -> None:
    async with db.sessionmaker() as session:
        pid = await session.scalar(select(Place.id).where(Place.name == "종로 박물관"))
        session.add_all(
            OpeningHour(place_id=pid, dow=d, open_time=time(9), close_time=time(21)) for d in range(7)
        )
        await session.commit()
    report = await hours.run(db, "key", limit=1, log=lambda _m: None, transport=fake_tourapi([], [900]))
    assert report.kept_existing == 1
    assert await week_of(db, "종로 박물관") == ["09:00-21:00"] * 7


async def test_export_and_load_elsewhere_without_calls(db: Database, tmp_path: Path) -> None:
    await hours.run(db, "key", limit=10, log=lambda _m: None, transport=fake_tourapi([], [900]))
    out = tmp_path / "hours.json"
    assert await hours.export(db, out, log=lambda _m: None) == 5
    data = json.loads(out.read_text("utf-8"))
    assert {r["contentid"] for r in data["intros"]} == set(INTROS)

    # a second machine: same places, nothing fetched yet
    async with db.sessionmaker() as session:
        for src in (await session.scalars(select(PlaceSource))).all():
            src.raw = {"contenttypeid": src.raw["contenttypeid"]}
        await session.execute(delete(OpeningHour))
        await session.commit()
    report = await hours.load_file(db, out, log=lambda _m: None)
    assert (report.parsed, report.ambiguous) == (3, 2)
    assert await week_of(db, "종로 박물관") == ["휴", *["10:00-18:00"] * 6]
    again = await hours.load_file(db, out, log=lambda _m: None)
    assert again.queued == 0  # not newer than what is stored


async def test_reapply_after_a_parser_change_costs_nothing(db: Database) -> None:
    await hours.run(db, "key", limit=10, log=lambda _m: None, transport=fake_tourapi([], [900]))
    report = await hours.reapply(db, log=lambda _m: None)
    assert report.calls == 0 and report.parsed == 3
    assert await week_of(db, "종로 궁궐") == ["09:00-17:00", "휴", *["09:00-17:00"] * 5]


async def test_no_key() -> None:
    with pytest.raises(hours.HoursIngestError):
        await hours.run(Database(Settings(_env_file=None, app_env="test")), None)  # type: ignore[call-arg]
