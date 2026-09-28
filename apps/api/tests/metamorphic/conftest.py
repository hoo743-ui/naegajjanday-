"""일관성(메타모픽) 테스트의 DB (docs/65 §3).

- `fixture` — 늘 돈다(CI 포함). data/seed 를 진짜 적재 파이프라인으로 넣은 임시 SQLite 파일 +
  tests/metamorphic/data 의 작은 허구 샘플(가게 · 멀티플렉스). tests/conftest.py 의 `app` DB 와 따로 둔다 —
  가게를 더하면 "가게 없는 씨앗 DB" 를 전제로 한 다른 테스트가 달라지므로.
- `national` — `METAMORPHIC_NATIONAL=1` 일 때만. apps/api/.env 의 DATABASE_URL(로컬 전국 DB)을
  **읽기 전용**(sqlite `mode=ro`)으로 연다. 쓰기는 SQLite 가 거절한다 — 코스 서비스도 `dry_run` 만 쓴다.
"""

from __future__ import annotations

import os
import re
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio

from app.core.config import API_ROOT, Settings
from app.infra.db.session import Database
from app.infra.ingestion.config_loader import load_config
from app.services.ingestion_runner import ingest
from tests.metamorphic.harness import Planner

SEED_DIR = API_ROOT / "data" / "seed"
EXTRA_DIR = Path(__file__).parent / "data"
NATIONAL_ENV = "METAMORPHIC_NATIONAL"


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers", f"national: 로컬 전국 DB 표본(읽기 전용) — {NATIONAL_ENV}=1 일 때만 돈다 (docs/65 §3)"
    )


def _settings(database_url: str, tmp: Path) -> Settings:
    return Settings(
        _env_file=None,
        app_env="test",
        log_level="WARNING",
        database_url=database_url,
        redis_url=None,
        es_url=None,
        llm_provider="none",
        analytics_provider="none",
        jwt_secret="test-secret-test-secret-test-secret-1234",
        upload_dir=tmp,
        osrm_foot_url="",  # no network: walking legs keep the engine estimate
        naver_map_client_id=None,
        naver_map_client_secret=None,
    )


@pytest_asyncio.fixture(scope="session")
async def fixture_planner(tmp_path_factory: pytest.TempPathFactory) -> AsyncIterator[Planner]:
    db_file = tmp_path_factory.mktemp("metamorphic") / "fixture.db"
    settings = _settings(f"sqlite+aiosqlite:///{db_file.as_posix()}", tmp_path_factory.mktemp("uploads"))
    db = Database(settings)
    try:
        await db.create_all()
        async with db.sessionmaker() as session:
            await load_config(session, SEED_DIR)
            await session.commit()
        for path in [*sorted((SEED_DIR / "places").glob("*.json")), *sorted(EXTRA_DIR.glob("*.json"))]:
            _, report = await ingest(db, settings, provider_name="file", region_slug=None, path=path)
            assert report.failed == 0, report.errors
        yield Planner(db, settings, world="fixture")
    finally:
        await db.dispose()


MOVEMENT_DIR = Path(__file__).parent / "data_movement"
# M3 의 B: 홍대 중심에서 서쪽으로 1.8km 의 허구 동네 (tests/metamorphic/data_movement/seoul-mm-west.json)
MOVEMENT_WEST = {
    "slug": "seoul-mm-west",
    "name": "서쪽샘플",
    "level": 3,
    "parent": "seoul-mapo",
    "center_lat": 37.5572,
    "center_lng": 126.90408,
    "radius_m": 1200,
    "area_code": "1:13",
    "status": "active",
    "search_keywords": [],
}


@pytest_asyncio.fixture(scope="session")
async def movement_planner(tmp_path_factory: pytest.TempPathFactory) -> AsyncIterator[Planner]:
    """이동 모드(I8 · I9 · I10) 의 DB: `fixture` 와 같고, 거기에 홍대 둘레 0.9~2.4km 의 가게들과 서쪽 1.8km 의
    허구 동네 하나(M3 의 B)를 더한 것. 따로 두는 까닭: 둘레 가게가 I1~I7 의 코스를 바꾸지 않게."""
    from app.infra.ingestion.config_loader import upsert_regions

    db_file = tmp_path_factory.mktemp("metamorphic-movement") / "movement.db"
    settings = _settings(f"sqlite+aiosqlite:///{db_file.as_posix()}", tmp_path_factory.mktemp("uploads-m"))
    db = Database(settings)
    try:
        await db.create_all()
        async with db.sessionmaker() as session:
            await load_config(session, SEED_DIR)
            await upsert_regions(session, [MOVEMENT_WEST])
            await session.commit()
        paths = [
            *sorted((SEED_DIR / "places").glob("*.json")),
            *sorted(EXTRA_DIR.glob("*.json")),
            *sorted(MOVEMENT_DIR.glob("*.json")),
        ]
        for path in paths:
            _, report = await ingest(db, settings, provider_name="file", region_slug=None, path=path)
            assert report.failed == 0, report.errors
        yield Planner(db, settings, world="movement")
    finally:
        await db.dispose()


def _national_url() -> str | None:
    """The local national DB from apps/api/.env, as a read-only SQLite URI — or None."""
    env = API_ROOT / ".env"
    if not env.exists():
        return None
    found = re.search(r"^DATABASE_URL=sqlite\+aiosqlite:///(.+)$", env.read_text(encoding="utf-8"), re.M)
    if not found:
        return None
    path = Path(found.group(1).strip())
    if not path.is_file():
        return None
    # `mode=ro`: SQLite itself refuses every write on this connection
    return f"sqlite+aiosqlite:///file:{path.as_posix()}?mode=ro&uri=true"


@pytest_asyncio.fixture(scope="session")
async def national_planner(tmp_path_factory: pytest.TempPathFactory) -> AsyncIterator[Planner]:
    if os.environ.get(NATIONAL_ENV) != "1":
        pytest.skip(f"전국 DB 표본은 {NATIONAL_ENV}=1 일 때만 (docs/65 §3)")
    url = _national_url()
    if url is None:
        pytest.skip("apps/api/.env 의 DATABASE_URL 에 로컬 전국 SQLite DB 가 없다")
    settings = _settings(url, tmp_path_factory.mktemp("uploads-national"))
    db = Database(settings)
    try:
        yield Planner(db, settings, world="national")
    finally:
        await db.dispose()
