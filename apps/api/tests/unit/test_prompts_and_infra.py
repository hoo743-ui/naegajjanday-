from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from app.core import security
from app.core.config import Settings
from app.core.rate_limit import MemoryRateLimiter
from app.core.sse import HEARTBEAT, sse, with_heartbeat
from app.infra.ingestion import dedupe
from app.infra.ingestion.base import NormalizedMenu
from app.infra.ingestion.price import price_per_person, price_tier
from app.infra.llm.base import LLMNotConfiguredError, LLMRequest
from app.infra.llm.factory import build_llm
from app.infra.search.client import SearchQuery, build_query, build_search
from app.prompts.loader import PromptLoader, PromptNotFoundError


class TestPromptLoader:
    def test_loads_latest_version_and_renders(self) -> None:
        prompt = PromptLoader().get("course_narrative")
        assert prompt.ref == "course_narrative@v1"
        rendered = prompt.render(facts={"total_price": 36000, "stops": []})
        assert "36000" in rendered.user and "짠이" in rendered.system
        assert rendered.output_schema and rendered.output_schema["required"] == ["summary", "stops", "tip"]

    def test_all_shipped_prompts_parse(self) -> None:
        loader = PromptLoader()
        ids = [
            "course_narrative",
            "course_narrative_stream",
            "review_sentiment",
            "chat_system",
            "tag_extraction",
        ]
        assert {loader.get(i).tier for i in ids} == {"smart", "fast"}
        assert loader.get("review_sentiment").tier == "fast"  # batch sentiment runs on the cheap model

    def test_version_pinning(self, tmp_path: Path) -> None:
        (tmp_path / "greet.v1.yaml").write_text(
            "id: greet\nversion: 1\nuser: 'v1 {{ name }}'\n", encoding="utf-8"
        )
        (tmp_path / "greet.v2.yaml").write_text(
            "id: greet\nversion: 2\nuser: 'v2 {{ name }}'\n", encoding="utf-8"
        )
        assert PromptLoader(tmp_path).get("greet").render(name="짠이").user == "v2 짠이"
        assert PromptLoader(tmp_path, pins={"greet": 1}).get("greet").render(name="짠이").user == "v1 짠이"
        assert PromptLoader(tmp_path).get("greet", version=1).version == 1
        assert PromptLoader(tmp_path).versions("greet") == [1, 2]

    def test_missing_prompt_variable_and_mismatch(self, tmp_path: Path) -> None:
        with pytest.raises(PromptNotFoundError):
            PromptLoader(tmp_path).get("nope")
        (tmp_path / "a.v1.yaml").write_text("id: a\nversion: 1\nuser: '{{ missing }}'\n", encoding="utf-8")
        with pytest.raises(Exception, match="missing"):
            PromptLoader(tmp_path).get("a").render()
        (tmp_path / "b.v1.yaml").write_text("id: other\nversion: 1\n", encoding="utf-8")
        with pytest.raises(ValueError, match="do not match"):
            PromptLoader(tmp_path).get("b")


class TestLLMFallback:
    async def test_null_provider_without_key(self) -> None:
        llm = build_llm(Settings(_env_file=None, llm_provider="anthropic", anthropic_api_key=None))
        assert llm.name == "none" and not llm.available
        with pytest.raises(LLMNotConfiguredError):
            await llm.complete(LLMRequest(messages=[]))

    def test_anthropic_selected_with_key(self) -> None:
        llm = build_llm(Settings(_env_file=None, llm_provider="anthropic", anthropic_api_key="sk-test"))
        assert llm.name == "anthropic" and llm.available
        assert llm.model_for("fast") == "claude-haiku-4-5"
        assert llm.model_for("smart") == "claude-opus-5"


class TestIngestionHelpers:
    def test_price_from_menu_median_ignores_sides(self) -> None:
        menus = [
            NormalizedMenu("잔치국수", 7000, True),
            NormalizedMenu("비빔국수", 8000),
            NormalizedMenu("수육", 15000),
            NormalizedMenu("사이다", 2000),
        ]
        assert price_per_person(menus) == 8000
        assert price_per_person([]) is None
        assert [price_tier(p, False) for p in (8000, 15000, 30000, 60000)] == [1, 2, 3, 4]
        assert price_tier(None, True) == 1

    def test_dedupe_by_name_and_distance(self) -> None:
        existing = [dedupe.ExistingPlace(1, "코인 로스터리", 37.5572, 126.9245, "02-123-4567")]
        same = dedupe.find_match("코인로스터리 홍대점", 37.55722, 126.92452, None, existing)
        assert same is not None and same.place_id == 1 and same.confidence >= dedupe.MATCH_THRESHOLD
        assert dedupe.find_match("코인 로스터리", 37.5590, 126.9245, None, existing) is None  # 200 m away
        assert dedupe.find_match("전혀 다른 식당", 37.5572, 126.9245, None, existing) is None


class TestSearchQuery:
    def test_disabled_without_url(self) -> None:
        assert build_search(Settings(_env_file=None, es_url=None)) is None

    def test_query_dsl(self) -> None:
        body = build_query(SearchQuery(q="국수", region_slug="seoul-hongdae", roles=("MEAL",), max_price=10000,
                                       lat=37.55, lng=126.92, radius_m=800, sort="distance"))  # fmt: skip
        filters = body["query"]["bool"]["filter"]
        assert {"term": {"status": "approved"}} in filters
        assert {"terms": {"course_role": ["MEAL"]}} in filters
        assert any("geo_distance" in f for f in filters)
        assert "_geo_distance" in body["sort"][0]


class TestSecurity:
    def test_access_token_roundtrip_and_tamper(self) -> None:
        settings = Settings(_env_file=None)
        token, claims = security.create_access_token(settings, user_public_id="u-1", role="admin")
        decoded = security.decode_access_token(settings, token)
        assert (decoded.sub, decoded.role, decoded.jti) == ("u-1", "admin", claims.jti)
        with pytest.raises(security.TokenError):
            security.decode_access_token(Settings(_env_file=None, jwt_secret="x" * 40), token)

    def test_pkce_s256_and_authorize_url(self) -> None:
        verifier, challenge = security.new_pkce_pair()
        assert 43 <= len(verifier) <= 128 and "=" not in challenge
        settings = Settings(_env_file=None, kakao_client_id="cid", kakao_client_secret="sec")
        url = security.build_authorize_url(settings, "kakao", state="st", code_challenge=challenge)
        assert url.startswith("https://kauth.kakao.com/oauth/authorize?")
        assert "code_challenge_method=S256" in url and "state=st" in url
        assert security.hash_token("a") != security.hash_token("b") and len(security.hash_token("a")) == 64

    def test_userinfo_parsers(self) -> None:
        kakao = {"id": 1, "kakao_account": {"email": "a@b.c", "profile": {"nickname": "짠이"}}}
        assert security.parse_userinfo("kakao", kakao) == ("1", "a@b.c", "짠이")
        naver = {"response": {"id": "n1", "email": "n@b.c", "nickname": "nn"}}
        assert security.parse_userinfo("naver", naver) == ("n1", "n@b.c", "nn")
        google = {"sub": "g1", "email": "g@b.c", "email_verified": False, "name": "G"}
        assert security.parse_userinfo("google", google) == ("g1", None, "G")


class TestRateLimiterAndSse:
    async def test_sliding_window(self) -> None:
        limiter = MemoryRateLimiter()
        results = [await limiter.hit("generate_anon", "ip:1", 3, 3600) for _ in range(4)]
        assert [r.allowed for r in results] == [True, True, True, False]
        assert results[2].remaining == 0 and results[3].reset_s > 0
        assert (await limiter.hit("generate_anon", "ip:2", 3, 3600)).allowed  # per identity

    async def test_heartbeat_fills_silence(self) -> None:
        async def slow() -> AsyncIterator[str]:
            yield sse("token", {"text": "a"})
            await asyncio.sleep(0.12)
            yield sse("done", {})

        chunks = [c async for c in with_heartbeat(slow(), interval_s=0.05)]
        assert chunks[0].startswith("event: token") and chunks[-1].startswith("event: done")
        assert HEARTBEAT in chunks and HEARTBEAT.startswith(":")
