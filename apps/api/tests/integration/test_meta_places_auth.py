from __future__ import annotations

import uuid
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest

from app.core.deps import Container
from app.repositories.user_repo import SqlUserRepository
from app.services.auth_service import AuthService


class TestMeta:
    async def test_regions_come_from_the_database(self, client: httpx.AsyncClient) -> None:
        resp = await client.get("/v1/meta/regions")
        assert resp.status_code == 200 and resp.headers["x-ratelimit-limit"] == "300"
        items = {r["slug"]: r for r in resp.json()["items"]}
        hongdae = items["seoul-hongdae"]
        assert hongdae["name"] == "홍대입구" and hongdae["level"] == 3 and hongdae["radius_m"] == 1200
        assert hongdae["parent"] == {"slug": "seoul-mapo", "name": "마포구"}
        assert hongdae["center"] == {"lat": 37.5572, "lng": 126.9245} and hongdae["place_count"] == 38

    async def test_region_filters(self, client: httpx.AsyncClient) -> None:
        under_seoul = (await client.get("/v1/meta/regions", params={"parent": "seoul"})).json()["items"]
        slugs = {r["slug"] for r in under_seoul}
        assert {"seoul-mapo", "seoul-hongdae", "seoul-seongsu"} <= slugs and "busan-seomyeon" not in slugs
        found = (await client.get("/v1/meta/regions", params={"q": "홍대"})).json()["items"]
        assert [r["slug"] for r in found] == ["seoul-hongdae"]

    async def test_purposes_categories_tags_banners(self, client: httpx.AsyncClient) -> None:
        purposes = (await client.get("/v1/meta/purposes")).json()["items"]
        assert purposes[0]["code"] == "date" and len(purposes) == 5
        date = purposes[0]
        assert date["recommended_budget"] == {"min": 30000, "max": 120000}
        # 총액(2인 기준)을 1인당으로 — 웹이 총액을 1인당으로 읽어 기본 예산이 두 배가 되던 문제의 회귀 방지
        assert date["default_party_size"] == 2
        assert date["budget_per_person"] == {"min": 15000, "max": 60000, "typical": 30000}
        assert (
            set(date["time_bands"]) == {"lunch", "afternoon", "evening", "fullday"}
            and date["min_budget_per_person"] > 0
        )

        tree = (await client.get("/v1/meta/categories")).json()["items"]
        food = next(c for c in tree if c["code"] == "food")
        assert food["course_role"] == "MEAL" and "food.noodle" in [c["code"] for c in food["children"]]

        moods = (await client.get("/v1/meta/tags", params={"group": "mood"})).json()["items"]
        assert moods and {t["group"] for t in moods} == {"mood"} and "조용한" in [t["name"] for t in moods]
        assert (await client.get("/v1/meta/banners", params={"placement": "home"})).json() == {"items": []}


class TestPlaces:
    async def test_search_falls_back_to_sql(self, client: httpx.AsyncClient) -> None:
        resp = await client.get("/v1/places/search", params={"q": "국수", "region": "seoul-hongdae"})
        body = resp.json()
        assert resp.status_code == 200 and body["engine"] == "sql"
        assert "짠이네 국수" in [i["name"] for i in body["items"]]

    async def test_search_filters_and_distance_sort(self, client: httpx.AsyncClient) -> None:
        params = {
            "role": "CAFE",
            "max_price": 5000,
            "lat": 37.5572,
            "lng": 126.9245,
            "radius": 1500,
            "sort": "distance",
        }
        items = (await client.get("/v1/places/search", params=params)).json()["items"]
        assert items and all(i["role"] == "CAFE" and (i["price_per_person"] or 0) <= 5000 for i in items)
        dists = [i["distance_m"] for i in items]
        assert dists == sorted(dists) and dists[-1] <= 1500

    async def test_autocomplete_detail_nearby(self, client: httpx.AsyncClient) -> None:
        auto = (await client.get("/v1/places/autocomplete", params={"q": "짠이네"})).json()["items"]
        assert auto and auto[0]["name"].startswith("짠이네")
        detail = (await client.get(f"/v1/places/{auto[0]['id']}")).json()
        assert detail["menus"] and detail["opening_hours"] and detail["reviews"]["bayes_rating"]
        assert detail["price_per_person"] == 8000  # menu median, derived by the ingestion pipeline
        assert any(h["is_closed"] for h in detail["opening_hours"]) and len(detail["congestion_today"]) == 24
        near = (await client.get(f"/v1/places/{auto[0]['id']}/nearby", params={"role": "CAFE"})).json()[
            "items"
        ]
        assert near and all(i["role"] == "CAFE" for i in near)
        assert (await client.get("/v1/places/does-not-exist")).json()["code"] == "PLACE_NOT_FOUND"

    async def test_attractions_and_events(self, client: httpx.AsyncClient) -> None:
        resp = await client.get(
            "/v1/attractions", params={"region": "seoul-hongdae", "type": "park,festival"}
        )
        items = resp.json()["items"]
        assert {i["type"] for i in items} == {"park", "festival"}
        assert "경의선숲길" in [i["name"] for i in items] and any(i["kind"] == "event" for i in items)
        events = await client.get(
            "/v1/events", params={"region": "seoul-hongdae", "from": "2026-09-01", "to": "2026-09-30"}
        )
        assert len(events.json()["items"]) == 2
        # 페이지네이션: 웹은 limit·cursor 로 나눠 받는다 (무시하면 둘러보기가 전부를 한 번에 그린다)
        first = (await client.get("/v1/attractions", params={"region": "seoul-hongdae", "limit": 2})).json()
        assert len(first["items"]) == 2 and first["next_cursor"] == "2"
        rest = await client.get(
            "/v1/attractions", params={"region": "seoul-hongdae", "limit": 100, "cursor": "2"}
        )
        everything = (await client.get("/v1/attractions", params={"region": "seoul-hongdae"})).json()
        assert rest.json()["next_cursor"] is None and everything["next_cursor"] is None
        assert [i["id"] for i in first["items"] + rest.json()["items"]] == [
            i["id"] for i in everything["items"]
        ]
        bad = await client.get("/v1/attractions", params={"region": "seoul-hongdae", "type": "casino"})
        assert bad.status_code == 422

    async def test_attractions_search_by_name_or_address(self, client: httpx.AsyncClient) -> None:
        """둘러보기 검색창은 `q` 를 보낸다 — 무시하면 무엇을 쳐도 목록이 그대로다."""
        everything = (await client.get("/v1/attractions", params={"region": "seoul-hongdae"})).json()["items"]
        by_name = (
            await client.get("/v1/attractions", params={"region": "seoul-hongdae", "q": "경의선"})
        ).json()
        assert [i["name"] for i in by_name["items"]] == ["경의선숲길"]
        assert 0 < len(by_name["items"]) < len(everything)
        # 행사도 같은 목록에서 찾는다 (제목의 일부, 대소문자 무시)
        event = next(i for i in everything if i["kind"] == "event")
        found = await client.get("/v1/attractions", params={"q": event["name"][:4].upper()})
        assert event["id"] in [i["id"] for i in found.json()["items"]]
        # 주소로도 찾는다
        place = next(i for i in everything if i["kind"] == "place" and i["address"])
        by_addr = await client.get("/v1/attractions", params={"q": place["address"]})
        assert place["id"] in [i["id"] for i in by_addr.json()["items"]]
        # 자르기 전에 거른다: 검색 결과의 첫 쪽은 '검색된 것들'의 첫 쪽이다
        paged = (await client.get("/v1/attractions", params={"q": "경의선", "limit": 1})).json()
        assert [i["name"] for i in paged["items"]] == ["경의선숲길"] and paged["next_cursor"] is None
        # LIKE 와일드카드는 글자 그대로 취급한다
        assert (await client.get("/v1/attractions", params={"q": "%"})).json()["items"] == []
        assert (await client.get("/v1/attractions", params={"q": "없는곳없는곳"})).json()["items"] == []

    async def test_suggest_needs_login_and_lands_pending(
        self, client: httpx.AsyncClient, user_headers: dict[str, str]
    ) -> None:
        body = {
            "region": "seoul-hongdae",
            "name": "제보 테스트 식당",
            "category": "food.korean",
            "lat": 37.5575,
            "lng": 126.9250,
        }
        assert (await client.post("/v1/places/suggest", json=body)).status_code == 401
        resp = await client.post("/v1/places/suggest", json=body, headers=user_headers)
        assert resp.status_code == 201 and resp.json()["status"] == "pending"
        hidden = await client.get("/v1/places/search", params={"q": "제보 테스트"})
        assert hidden.json()["items"] == []  # pending places are never served


class TestAuth:
    async def test_me_requires_a_valid_token(
        self, client: httpx.AsyncClient, user_headers: dict[str, str]
    ) -> None:
        assert (await client.get("/v1/me")).json()["code"] == "UNAUTHORIZED"
        assert (await client.get("/v1/me", headers={"Authorization": "Bearer garbage"})).status_code == 401
        me = await client.get("/v1/me", headers=user_headers)
        assert me.status_code == 200 and me.json()["role"] == "user"
        patched = await client.patch("/v1/me", headers=user_headers, json={"nickname": "알뜰이"})
        assert patched.json()["nickname"] == "알뜰이"

    async def test_preferences_roundtrip(
        self, client: httpx.AsyncClient, user_headers: dict[str, str]
    ) -> None:
        body = {
            "liked_tags": ["조용한"],
            "disliked_tags": ["웨이팅"],
            "category_weights": {},
            "default_transport": "transit",
        }
        assert (await client.put("/v1/me/preferences", headers=user_headers, json=body)).json() == body
        assert (await client.get("/v1/me/preferences", headers=user_headers)).json() == body

    async def test_oauth_login_not_configured_is_explicit(self, client: httpx.AsyncClient) -> None:
        resp = await client.get("/v1/auth/kakao/login")
        assert (resp.status_code, resp.json()["code"]) == (503, "OAUTH_NOT_CONFIGURED")
        assert (await client.get("/v1/auth/myspace/login")).status_code == 422

    async def test_providers_report_what_is_configured(
        self, client: httpx.AsyncClient, container: Container, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        resp = await client.get("/v1/auth/providers")
        assert resp.status_code == 200
        assert resp.json() == {
            "items": [{"provider": p, "enabled": False} for p in ("kakao", "naver", "google")]
        }
        monkeypatch.setattr(container.settings, "naver_client_id", "id")  # id alone is not enough
        monkeypatch.setattr(container.settings, "google_client_id", "id")
        monkeypatch.setattr(container.settings, "google_client_secret", "secret")
        items = (await client.get("/v1/auth/providers")).json()["items"]
        assert {i["provider"]: i["enabled"] for i in items} == {
            "kakao": False,
            "naver": False,
            "google": True,
        }

    async def test_oauth_failures_go_back_to_the_web_login_page(
        self, client: httpx.AsyncClient, container: Container, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        web = container.settings.web_base_url.rstrip("/")
        # a browser navigation (redirect_to given) never dead-ends on raw JSON at the API origin
        resp = await client.get("/v1/auth/kakao/login", params={"redirect_to": "/my"})
        assert resp.status_code == 303
        assert resp.headers["location"] == f"{web}/login?error=oauth_not_configured&next=%2Fmy"
        # an off-site target is not a redirect target → the explicit problem+json stays
        evil = await client.get("/v1/auth/kakao/login", params={"redirect_to": "https://evil.example"})
        assert evil.status_code == 503

        monkeypatch.setattr(container.settings, "kakao_client_id", "id")
        monkeypatch.setattr(container.settings, "kakao_client_secret", "secret")
        started = await client.get("/v1/auth/kakao/login", params={"redirect_to": "/my"})
        assert started.status_code == 307
        state = parse_qs(urlsplit(started.headers["location"]).query)["state"][0]
        cancelled = await client.get(
            "/v1/auth/kakao/callback", params={"error": "access_denied", "state": state}
        )
        assert cancelled.status_code == 303
        assert cancelled.headers["location"] == f"{web}/login?error=oauth_cancelled&next=%2Fmy"
        # the state is single-use, and without a known origin the answer is problem+json again
        replay = await client.get(
            "/v1/auth/kakao/callback", params={"error": "access_denied", "state": state}
        )
        assert (replay.status_code, replay.json()["code"]) == (400, "BAD_REQUEST")

    async def test_refresh_rotation_and_reuse_detection(
        self, client: httpx.AsyncClient, container: Container
    ) -> None:
        async with container.db.sessionmaker() as session:
            user = await SqlUserRepository(session).create(
                email=f"{uuid.uuid4().hex}@example.com", nickname="r"
            )
            tokens = await AuthService(container.settings, session, container.cache).issue(
                user, str(uuid.uuid4())
            )
            await session.commit()
        first = await client.post("/v1/auth/refresh", cookies={"rt": tokens.refresh_token})
        assert first.status_code == 200 and first.json()["token_type"] == "Bearer"
        rotated = first.cookies.get("rt")
        assert rotated and rotated != tokens.refresh_token
        assert "HttpOnly" in first.headers["set-cookie"] and "SameSite=lax" in first.headers["set-cookie"]
        access = {"Authorization": f"Bearer {first.json()['access_token']}"}
        assert (await client.get("/v1/me", headers=access)).status_code == 200

        # replaying the already-rotated token = theft signal → the whole family dies
        client.cookies.clear()
        replay = await client.post("/v1/auth/refresh", cookies={"rt": tokens.refresh_token})
        assert (replay.status_code, replay.json()["code"]) == (401, "TOKEN_REUSE_DETECTED")
        client.cookies.clear()
        assert (await client.post("/v1/auth/refresh", cookies={"rt": rotated})).status_code == 401
        client.cookies.clear()
        assert (await client.post("/v1/auth/refresh")).status_code == 401

    async def test_logout_denylists_the_access_token(
        self, client: httpx.AsyncClient, container: Container
    ) -> None:
        from app.core import security

        async with container.db.sessionmaker() as session:
            user = await SqlUserRepository(session).create(
                email=f"{uuid.uuid4().hex}@example.com", nickname="l"
            )
            await session.commit()
        token, _ = security.create_access_token(
            container.settings, user_public_id=user.public_id, role="user"
        )
        headers = {"Authorization": f"Bearer {token}"}
        assert (await client.get("/v1/me", headers=headers)).status_code == 200
        assert (await client.post("/v1/auth/logout", headers=headers)).status_code == 200
        assert (await client.get("/v1/me", headers=headers)).status_code == 401

    async def test_logout_is_idempotent_without_a_valid_access_token(
        self, client: httpx.AsyncClient, container: Container
    ) -> None:
        async with container.db.sessionmaker() as session:
            user = await SqlUserRepository(session).create(
                email=f"{uuid.uuid4().hex}@example.com", nickname="x"
            )
            tokens = await AuthService(container.settings, session, container.cache).issue(
                user, str(uuid.uuid4())
            )
            await session.commit()
        # expired / garbage / denylisted access token: the refresh cookie must still be revoked and cleared
        stale = {"Authorization": "Bearer not-a-valid-jwt"}
        out = await client.post("/v1/auth/logout", headers=stale, cookies={"rt": tokens.refresh_token})
        assert out.status_code == 200
        assert 'rt=""' in out.headers["set-cookie"] and "Path=/v1/auth" in out.headers["set-cookie"]
        client.cookies.clear()
        assert (
            await client.post("/v1/auth/refresh", cookies={"rt": tokens.refresh_token})
        ).status_code == 401
        client.cookies.clear()
        assert (await client.post("/v1/auth/logout")).status_code == 200  # nothing to do is still fine

    async def test_me_reports_the_linked_provider(
        self, client: httpx.AsyncClient, container: Container, user_headers: dict[str, str]
    ) -> None:
        from app.core import security

        assert (await client.get("/v1/me", headers=user_headers)).json()["provider"] is None
        async with container.db.sessionmaker() as session:
            user = await SqlUserRepository(session).upsert_oauth_user(
                "naver", uuid.uuid4().hex, f"{uuid.uuid4().hex}@example.com", None
            )
            await session.commit()
        token, _ = security.create_access_token(
            container.settings, user_public_id=user.public_id, role="user"
        )
        body = (await client.get("/v1/me", headers={"Authorization": f"Bearer {token}"})).json()
        assert body["provider"] == "naver"


class TestOps:
    async def test_health_ready_metrics_and_headers(self, client: httpx.AsyncClient) -> None:
        assert (await client.get("/healthz")).json() == {"ok": True}
        ready = await client.get("/readyz")
        assert ready.status_code == 200
        components = ready.json()["components"]
        assert components["database"] == {"status": "ok", "backend": "sqlite"}
        assert components["cache"]["backend"] == "memory" and components["search"]["status"] == "disabled"
        assert "njd_recommendations_total" in (await client.get("/metrics")).text
        assert (
            ready.headers["x-content-type-options"] == "nosniff"
            and ready.headers["x-frame-options"] == "DENY"
        )
        echoed = await client.get("/healthz", headers={"X-Request-ID": "trace-12345678"})
        assert echoed.headers["x-request-id"] == "trace-12345678"

    async def test_cors_allowlist(self, client: httpx.AsyncClient) -> None:
        preflight = {"Access-Control-Request-Method": "POST"}
        ok = await client.options(
            "/v1/courses/generate", headers={"Origin": "http://localhost:3000", **preflight}
        )
        assert ok.headers["access-control-allow-origin"] == "http://localhost:3000"
        evil = await client.options(
            "/v1/courses/generate", headers={"Origin": "https://evil.example", **preflight}
        )
        assert "access-control-allow-origin" not in evil.headers

    async def test_unknown_route_is_a_problem(self, client: httpx.AsyncClient) -> None:
        resp = await client.get("/v1/nope")
        assert resp.status_code == 404 and resp.headers["content-type"].startswith("application/problem+json")
        assert resp.json()["code"] == "NOT_FOUND"

    async def test_chat_without_llm_is_an_explicit_503(self, client: httpx.AsyncClient) -> None:
        resp = await client.post("/v1/chat/sessions")
        assert (resp.status_code, resp.json()["code"]) == (503, "LLM_UNAVAILABLE")
        # 웹은 이 플래그를 보고 챗봇 입구를 미리 접는다 — 503 과 같은 스위치여야 한다
        assert (await client.get("/v1/meta/features")).json()["chat"] is False

    async def test_openapi_is_served(self, client: httpx.AsyncClient) -> None:
        spec = (await client.get("/v1/openapi.json")).json()
        assert "/v1/courses/generate" in spec["paths"] and "/v1/admin/places" in spec["paths"]
