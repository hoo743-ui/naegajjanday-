"""The web promises: unsaved courses vanish after 24 h, a deleted account is purged after 30 days."""

from __future__ import annotations

import asyncio
import uuid
from datetime import timedelta
from typing import Any
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from typer.testing import CliRunner

from app.core import security
from app.core.deps import Container
from app.infra.db.base import utcnow
from app.infra.db.models import (
    Course,
    CourseStop,
    OAuthAccount,
    RecommendationLog,
    RefreshToken,
    User,
    UserPreference,
)
from app.repositories.user_repo import SqlUserRepository
from app.services import retention_service as retention
from app.services.auth_service import AuthService
from tests.conftest import GENERATE_BODY


async def _generate_body(
    client: httpx.AsyncClient, headers: dict[str, str] | None = None, **overrides: object
) -> dict[str, Any]:
    resp = await client.post("/v1/courses/generate", json={**GENERATE_BODY, **overrides}, headers=headers)
    assert resp.status_code == 200, resp.text
    body: dict[str, Any] = resp.json()
    return body


async def _generate(
    client: httpx.AsyncClient, headers: dict[str, str] | None = None, **overrides: object
) -> list[dict[str, Any]]:
    courses: list[dict[str, Any]] = (await _generate_body(client, headers, **overrides))["courses"]
    return courses


async def _age(container: Container, public_ids: list[str], hours: int) -> None:
    async with container.db.sessionmaker() as session:
        await session.execute(
            update(Course)
            .where(Course.public_id.in_(public_ids))
            .values(created_at=utcnow() - timedelta(hours=hours))
        )
        await session.commit()


async def _stop_count(container: Container, public_id: str) -> int:
    async with container.db.sessionmaker() as session:
        stmt = (
            select(func.count(CourseStop.id))
            .join(Course, Course.id == CourseStop.course_id)
            .where(Course.public_id == public_id)
        )
        return int(await session.scalar(stmt) or 0)


async def _new_user(container: Container) -> tuple[User, dict[str, str]]:
    async with container.db.sessionmaker() as session:
        users = SqlUserRepository(session)
        user = await users.upsert_oauth_user(
            "kakao", uuid.uuid4().hex, f"{uuid.uuid4().hex}@example.com", "bye"
        )
        await users.ensure_preference(user.id)
        await AuthService(container.settings, session, container.cache).issue(user, str(uuid.uuid4()))
        await session.commit()
    token, _ = security.create_access_token(container.settings, user_public_id=user.public_id, role="user")
    return user, {"Authorization": f"Bearer {token}"}


class TestUnsavedCoursePurge:
    async def test_only_old_unsaved_courses_are_removed(
        self, client: httpx.AsyncClient, container: Container, user_headers: dict[str, str]
    ) -> None:
        old = await _generate(client, budget_total=41000)
        kept, dropped = old[0]["id"], [c["id"] for c in old[1:]]
        assert dropped, "the request asks for alternatives"
        assert (await client.post(f"/v1/courses/{kept}/save", headers=user_headers)).status_code == 200
        fresh = (await _generate(client, budget_total=42000, alternatives=0))[0]["id"]
        await _age(container, [kept, *dropped], hours=25)

        preview = await retention.purge_unsaved_courses(container.db, container.settings, dry_run=True)
        assert preview.dry_run and preview.matched >= len(dropped) and preview.deleted == 0
        for course_id in [kept, fresh, *dropped]:  # --dry-run deletes nothing
            assert (await client.get(f"/v1/courses/{course_id}")).status_code == 200

        report = await retention.purge_unsaved_courses(container.db, container.settings)
        assert report.deleted == report.matched == preview.matched
        for course_id in dropped:
            assert (await client.get(f"/v1/courses/{course_id}")).status_code == 404
            assert await _stop_count(container, course_id) == 0
        assert (await client.get(f"/v1/courses/{fresh}")).status_code == 200  # younger than the TTL
        detail = await client.get(f"/v1/courses/{kept}")  # saved: survives, siblings shrink to itself
        assert detail.status_code == 200 and await _stop_count(container, kept) > 0
        assert [s["id"] for s in detail.json()["siblings"]] == [kept]
        again = await retention.purge_unsaved_courses(container.db, container.settings)
        assert (again.matched, again.deleted) == (0, 0)

    async def test_ttl_is_a_setting(
        self, client: httpx.AsyncClient, container: Container, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        course = (await _generate(client, budget_total=43000, alternatives=0))[0]["id"]
        await _age(container, [course], hours=25)
        monkeypatch.setattr(container.settings, "unsaved_course_ttl_hours", 48)
        assert (await retention.purge_unsaved_courses(container.db, container.settings)).deleted == 0
        assert (await client.get(f"/v1/courses/{course}")).status_code == 200
        monkeypatch.setattr(container.settings, "unsaved_course_ttl_hours", 24)
        assert (await retention.purge_unsaved_courses(container.db, container.settings)).deleted == 1

    async def test_cli_dry_run_deletes_nothing_then_purges(
        self, client: httpx.AsyncClient, container: Container, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app import cli

        course = (await _generate(client, budget_total=44000, alternatives=0))[0]["id"]
        await _age(container, [course], hours=30)
        monkeypatch.setattr(cli, "get_settings", lambda: container.settings)
        runner = CliRunner()
        # the command owns its event loop (`asyncio.run`) → run it off the test loop's thread
        dry = await asyncio.to_thread(runner.invoke, cli.cli, ["purge-courses", "--dry-run"])
        assert dry.exit_code == 0 and "would delete courses=1" in dry.output
        assert (await client.get(f"/v1/courses/{course}")).status_code == 200
        real = await asyncio.to_thread(runner.invoke, cli.cli, ["purge-courses"])
        assert real.exit_code == 0 and "deleted courses=1" in real.output
        assert (await client.get(f"/v1/courses/{course}")).status_code == 404
        accounts = await asyncio.to_thread(runner.invoke, cli.cli, ["purge-accounts", "--dry-run"])
        assert accounts.exit_code == 0 and "would delete accounts=" in accounts.output


class TestAccountPurge:
    async def test_soft_delete_now_hard_purge_after_the_grace_period(
        self, client: httpx.AsyncClient, container: Container
    ) -> None:
        user, headers = await _new_user(container)
        origin = {"lat": 37.5563, "lng": 126.9236}
        generated = await _generate_body(
            client, headers, budget_total=45000, alternatives=0, region=None, origin=origin
        )
        course = generated["courses"][0]
        assert (await client.post(f"/v1/courses/{course['id']}/save", headers=headers)).status_code == 200

        gone = await client.delete("/v1/me", headers=headers)
        assert gone.status_code == 200 and gone.json()["status"] == "deleting"
        assert (await client.get("/v1/me", headers=headers)).status_code == 401  # blocked at once

        early = await retention.purge_deleted_accounts(container.db, container.settings)
        assert early.accounts == 0  # still inside the 30 days: a new login can cancel it
        later = utcnow() + timedelta(days=container.settings.account_purge_grace_days, hours=1)
        preview = await retention.purge_deleted_accounts(
            container.db, container.settings, dry_run=True, now=later
        )
        assert preview.dry_run and preview.matched >= 1 and preview.courses >= 1
        async with container.db.sessionmaker() as session:
            assert await session.get(User, user.id) is not None  # --dry-run deletes nothing
        assert (await client.get(f"/v1/courses/{course['id']}")).status_code == 200

        report = await retention.purge_deleted_accounts(container.db, container.settings, now=later)
        assert report.accounts >= 1 and report.courses >= 1 and report.logs_anonymized >= 1
        async with container.db.sessionmaker() as session:
            assert await session.get(User, user.id) is None
            for model in (OAuthAccount, RefreshToken, UserPreference, Course):
                left = await session.scalar(select(func.count()).where(model.user_id == user.id))
                assert left == 0, model.__name__
            log = await session.scalar(
                select(RecommendationLog).where(RecommendationLog.request_id == generated["request_id"])
            )
            assert log is not None and log.user_id is None and "origin" not in log.request
            assert log.request["budget_total"] == 45000  # the anonymous aggregate survives
        assert (await client.get(f"/v1/courses/{course['id']}")).status_code == 404

    async def test_active_and_recently_deleted_accounts_survive(self, container: Container) -> None:
        active, _ = await _new_user(container)
        leaving, _ = await _new_user(container)
        async with container.db.sessionmaker() as session:
            row = await session.get(User, leaving.id)
            assert row is not None
            row.status, row.delete_requested_at = "deleting", utcnow() - timedelta(days=29)
            await session.commit()
        await retention.purge_deleted_accounts(container.db, container.settings)
        async with container.db.sessionmaker() as session:
            assert await session.get(User, active.id) is not None
            assert await session.get(User, leaving.id) is not None

    async def test_login_after_the_grace_period_starts_from_scratch(
        self, container: Container, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(container.settings, "kakao_client_id", "id")
        monkeypatch.setattr(container.settings, "kakao_client_secret", "secret")
        provider_id, email = uuid.uuid4().hex, f"{uuid.uuid4().hex}@example.com"

        def provider(request: httpx.Request) -> httpx.Response:
            if request.method == "POST":
                return httpx.Response(200, json={"access_token": "provider-token"})
            return httpx.Response(200, json={"id": provider_id, "kakao_account": {"email": email}})

        async def login(session: AsyncSession) -> User:
            async with httpx.AsyncClient(transport=httpx.MockTransport(provider)) as http:
                service = AuthService(container.settings, session, container.cache, http)
                url = await service.login_url("kakao", None)
                state = parse_qs(urlsplit(url).query)["state"][0]
                await service.callback("kakao", "code", state)
            found = await SqlUserRepository(session).get_by_email(email)
            assert found is not None
            return found

        async with container.db.sessionmaker() as session:
            first = await login(session)
            await SqlUserRepository(session).ensure_preference(first.id)
            first.status, first.delete_requested_at = "deleting", utcnow() - timedelta(days=3)
            await session.commit()
            first_id = first.public_id
        async with container.db.sessionmaker() as session:
            back = await login(session)  # inside the grace period: the same account, deletion cancelled
            assert (back.public_id, back.status, back.delete_requested_at) == (first_id, "active", None)
            back.status, back.delete_requested_at = "deleting", utcnow() - timedelta(days=31)
            await session.commit()
        async with container.db.sessionmaker() as session:
            fresh = await login(session)  # too late: old data is purged, a brand-new account appears
            assert fresh.public_id != first_id and fresh.status == "active"
            assert await SqlUserRepository(session).get_preference(fresh.id) is None
            assert await SqlUserRepository(session).get_by_public_id(first_id) is None
