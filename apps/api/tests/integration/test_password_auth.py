from __future__ import annotations

import asyncio
import uuid

import httpx
import pytest
from typer.testing import CliRunner

from app.core import security
from app.core.deps import Container
from app.repositories.user_repo import SqlUserRepository

PASSWORD = "throwaway-pw-1"  # test-only value


def _new_id() -> str:
    return f"t{uuid.uuid4().hex[:12]}"


def _has_hangul(text: str) -> bool:
    return any("가" <= ch <= "힣" for ch in text)


async def _signup(client: httpx.AsyncClient, login_id: str, **extra: object) -> httpx.Response:
    return await client.post("/v1/auth/signup", json={"login_id": login_id, "password": PASSWORD, **extra})


class TestSignup:
    async def test_signup_signs_in_at_once(self, client: httpx.AsyncClient, container: Container) -> None:
        login_id = _new_id()
        resp = await _signup(client, f"  {login_id.upper()} ")
        assert resp.status_code == 201
        body = resp.json()
        assert body["token_type"] == "Bearer" and body["access_token"] and body["expires_in"] > 0
        cookie = resp.headers["set-cookie"]
        assert cookie.startswith("rt=") and "HttpOnly" in cookie and "Path=/v1/auth" in cookie
        assert "SameSite=lax" in cookie

        me = await client.get("/v1/me", headers={"Authorization": f"Bearer {body['access_token']}"})
        assert me.status_code == 200
        profile = me.json()
        assert profile["login_id"] == login_id and profile["nickname"] == login_id  # stored lowercase
        assert (profile["role"], profile["status"], profile["email"]) == ("user", "active", None)

        # the refresh cookie works like the OAuth one
        rt = resp.cookies["rt"]
        client.cookies.clear()
        assert (await client.post("/v1/auth/refresh", cookies={"rt": rt})).status_code == 200

        async with container.db.sessionmaker() as session:
            user = await SqlUserRepository(session).get_by_login_id(login_id)
        assert user is not None and user.password_hash and user.password_hash.startswith("scrypt$")
        assert PASSWORD not in user.password_hash

    async def test_nickname_is_kept(self, client: httpx.AsyncClient) -> None:
        resp = await _signup(client, _new_id(), nickname="알뜰이")
        headers = {"Authorization": f"Bearer {resp.json()['access_token']}"}
        assert (await client.get("/v1/me", headers=headers)).json()["nickname"] == "알뜰이"

    async def test_duplicate_id_is_409(self, client: httpx.AsyncClient) -> None:
        login_id = _new_id()
        assert (await _signup(client, login_id)).status_code == 201
        again = await _signup(client, login_id.upper())  # case-insensitive
        assert again.status_code == 409
        assert again.headers["content-type"].startswith("application/problem+json")
        assert again.json()["code"] == "LOGIN_ID_TAKEN"
        assert again.json()["detail"] == "이미 쓰고 있는 아이디예요."

    @pytest.mark.parametrize(
        ("login_id", "password", "field"),
        [
            ("abc", PASSWORD, "login_id"),
            ("bad id!", PASSWORD, "login_id"),
            ("goodid1", "short1", "password"),
            ("goodid1", "onlyletters", "password"),
            ("goodid1", "1234567890", "password"),
        ],
    )
    async def test_bad_input_is_422_in_korean(
        self, client: httpx.AsyncClient, login_id: str, password: str, field: str
    ) -> None:
        resp = await client.post("/v1/auth/signup", json={"login_id": login_id, "password": password})
        assert resp.status_code == 422
        body = resp.json()
        assert body["code"] == "VALIDATION_ERROR"
        error = next(e for e in body["errors"] if e["field"] == field)
        assert _has_hangul(error["message"])  # our message, not pydantic's English one
        assert "rt=" not in resp.headers.get("set-cookie", "")


class TestPasswordLogin:
    async def test_login_success(self, client: httpx.AsyncClient) -> None:
        login_id = _new_id()
        await _signup(client, login_id)
        client.cookies.clear()
        resp = await client.post("/v1/auth/login", json={"login_id": login_id.upper(), "password": PASSWORD})
        assert resp.status_code == 200 and resp.json()["token_type"] == "Bearer"
        assert "HttpOnly" in resp.headers["set-cookie"] and resp.cookies.get("rt")
        headers = {"Authorization": f"Bearer {resp.json()['access_token']}"}
        assert (await client.get("/v1/me", headers=headers)).json()["login_id"] == login_id

    async def test_wrong_password_and_unknown_id_look_the_same(self, client: httpx.AsyncClient) -> None:
        login_id = _new_id()
        await _signup(client, login_id)
        wrong = await client.post("/v1/auth/login", json={"login_id": login_id, "password": "nope-pw-2"})
        unknown = await client.post("/v1/auth/login", json={"login_id": _new_id(), "password": PASSWORD})
        for resp in (wrong, unknown):
            assert resp.status_code == 401
            assert resp.json()["code"] == "INVALID_CREDENTIALS"
            assert resp.json()["detail"] == "아이디 또는 비밀번호가 맞지 않아요."
        assert wrong.json()["title"] == unknown.json()["title"]

    async def test_account_without_password_cannot_password_login(
        self, client: httpx.AsyncClient, container: Container
    ) -> None:
        login_id = _new_id()
        async with container.db.sessionmaker() as session:
            await SqlUserRepository(session).create(email=None, nickname="o", login_id=login_id)
            await session.commit()
        resp = await client.post("/v1/auth/login", json={"login_id": login_id, "password": PASSWORD})
        assert (resp.status_code, resp.json()["code"]) == (401, "INVALID_CREDENTIALS")

    async def test_suspended_account_is_forbidden(
        self, client: httpx.AsyncClient, container: Container
    ) -> None:
        login_id = _new_id()
        await _signup(client, login_id)
        async with container.db.sessionmaker() as session:
            user = await SqlUserRepository(session).get_by_login_id(login_id)
            assert user is not None
            user.status = "suspended"
            await session.commit()
        resp = await client.post("/v1/auth/login", json={"login_id": login_id, "password": PASSWORD})
        assert (resp.status_code, resp.json()["code"]) == (403, "FORBIDDEN")

    async def test_auth_routes_have_their_own_tight_ip_limit(
        self, client: httpx.AsyncClient, container: Container, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(container.settings, "rl_auth", "2/600")
        body = {"login_id": _new_id(), "password": PASSWORD}
        # a stale bearer token neither answers 401-expired nor buys a separate budget
        stale = {"Authorization": "Bearer not-a-valid-jwt"}
        first = await client.post("/v1/auth/login", json=body, headers=stale)
        assert first.json()["code"] == "INVALID_CREDENTIALS"
        assert (await client.post("/v1/auth/login", json=body)).status_code == 401
        limited = await client.post("/v1/auth/signup", json=body)
        assert (limited.status_code, limited.json()["code"]) == (429, "RATE_LIMITED")


class TestCreateAdminLogin:
    async def test_create_then_update_by_login_id(
        self, client: httpx.AsyncClient, container: Container, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app import cli

        monkeypatch.setattr(cli, "get_settings", lambda: container.settings)
        runner = CliRunner()
        login_id = _new_id()
        args = ["create-admin", "--login-id", login_id]

        monkeypatch.delenv("ADMIN_PASSWORD", raising=False)
        missing = await asyncio.to_thread(runner.invoke, cli.cli, args)
        assert missing.exit_code == 1 and "ADMIN_PASSWORD" in missing.output

        monkeypatch.setenv("ADMIN_PASSWORD", "weakpw")
        weak = await asyncio.to_thread(runner.invoke, cli.cli, args)
        assert weak.exit_code == 1 and "weakpw" not in weak.output

        monkeypatch.setenv("ADMIN_PASSWORD", "throwaway-admin-1")
        created = await asyncio.to_thread(runner.invoke, cli.cli, args)
        assert created.exit_code == 0, created.output
        assert "(created)" in created.output and "throwaway-admin-1" not in created.output
        first = {"login_id": login_id, "password": "throwaway-admin-1"}
        assert (await client.post("/v1/auth/login", json=first)).status_code == 200

        monkeypatch.setenv("ADMIN_PASSWORD", "throwaway-admin-2")
        updated = await asyncio.to_thread(runner.invoke, cli.cli, [*args, "--role", "operator"])
        assert updated.exit_code == 0 and "(updated)" in updated.output
        assert (await client.post("/v1/auth/login", json=first)).status_code == 401
        second = {"login_id": login_id, "password": "throwaway-admin-2"}
        new = await client.post("/v1/auth/login", json=second)
        assert new.status_code == 200
        async with container.db.sessionmaker() as session:
            user = await SqlUserRepository(session).get_by_login_id(login_id)
        assert user is not None and user.role == "operator"
        assert security.decode_access_token(container.settings, new.json()["access_token"]).role == "operator"

    async def test_needs_exactly_one_target(self) -> None:
        from app import cli

        runner = CliRunner()
        both = await asyncio.to_thread(
            runner.invoke, cli.cli, ["create-admin", "--email", "a@example.com", "--login-id", "abcd"]
        )
        none = await asyncio.to_thread(runner.invoke, cli.cli, ["create-admin"])
        assert both.exit_code == 1 and none.exit_code == 1
