from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI

from app.core import security
from app.core.config import API_ROOT, Settings
from app.core.deps import Container
from app.infra.ingestion.config_loader import load_config
from app.main import create_app
from app.repositories.user_repo import SqlUserRepository
from app.services.ingestion_runner import ingest

SEED_DIR = API_ROOT / "data" / "seed"
GENERATE_BODY = {
    "region": "seoul-hongdae",
    "purpose": "date",
    "party_size": 2,
    "budget_total": 40000,
    "start_at": "2026-09-20T18:00:00+09:00",
    "transport": "walk",
    "alternatives": 2,
}


@pytest_asyncio.fixture(scope="session")
async def app(tmp_path_factory: pytest.TempPathFactory) -> AsyncIterator[FastAPI]:
    """SQLite file DB, no Redis / search / LLM — seeded from data/seed through the real pipeline."""
    db_file: Path = tmp_path_factory.mktemp("db") / "test.db"
    settings = Settings(
        _env_file=None,
        app_env="test",
        log_level="WARNING",
        database_url=f"sqlite+aiosqlite:///{db_file.as_posix()}",
        redis_url=None,
        es_url=None,
        llm_provider="none",
        analytics_provider="none",
        jwt_secret="test-secret-test-secret-test-secret-1234",
    )
    application = create_app(settings)
    async with application.router.lifespan_context(application):
        container: Container = application.state.container
        await container.db.create_all()
        async with container.db.sessionmaker() as session:
            await load_config(session, SEED_DIR)
            await session.commit()
        for path in sorted((SEED_DIR / "places").glob("*.json")):
            _, report = await ingest(
                container.db, settings, provider_name="file", region_slug=None, path=path
            )
            assert report.failed == 0, report.errors
        yield application


@pytest_asyncio.fixture
async def container(app: FastAPI) -> Container:
    c: Container = app.state.container
    return c


@pytest_asyncio.fixture(autouse=True)
async def _clean_state(request: pytest.FixtureRequest) -> AsyncIterator[None]:
    """Rate-limit counters and caches must not leak between tests."""
    yield
    if "app" in request.fixturenames:
        c: Container = request.getfixturevalue("app").state.container
        await c.rate_limiter.reset()
        await c.cache.delete_prefix("")


@pytest_asyncio.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c


async def _token(container: Container, email: str, role: str) -> dict[str, str]:
    async with container.db.sessionmaker() as session:
        users = SqlUserRepository(session)
        user = await users.get_by_email(email) or await users.create(email=email, nickname=role, role=role)
        await session.commit()
        token, _ = security.create_access_token(container.settings, user_public_id=user.public_id, role=role)
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def user_headers(container: Container) -> dict[str, str]:
    return await _token(container, "user@example.com", "user")


@pytest_asyncio.fixture
async def admin_headers(container: Container) -> dict[str, str]:
    return await _token(container, "admin@example.com", "admin")
