from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

API_ROOT = Path(__file__).resolve().parents[2]

CsvList = Annotated[list[str], NoDecode]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- app ---
    app_env: Literal["local", "test", "staging", "production"] = "local"
    app_name: str = "naegajjanday-api"
    engine_version: str = "1.0.0"
    # docs/29: v1 = distance as a hard limit (kept for comparison), v2 = the whole day scored ("Best Day").
    # A request may name one (offline comparison, A/B); every course remembers the one it was made with.
    recommendation_algorithm: Literal["v1", "v2"] = "v2"
    log_level: str = "INFO"
    log_json: bool = True
    public_base_url: str = "http://localhost:8000"
    web_base_url: str = "http://localhost:3000"
    error_type_base: str = "https://api.naegajjanday.com/errors"
    timezone: str = "Asia/Seoul"
    seed_dir: Path = API_ROOT / "data" / "seed"

    # --- storage ---
    database_url: str = "sqlite+aiosqlite:///./dev.db"
    db_echo: bool = False
    redis_url: str | None = None
    es_url: str | None = None  # OpenSearch / Elasticsearch-compatible endpoint; unset → SQL fallback
    es_username: str | None = None
    es_password: str | None = None
    es_verify_certs: bool = True
    es_index_alias: str = "places"

    # --- security ---
    jwt_secret: str = "change-me-in-production-please-use-32+bytes"
    jwt_algorithm: str = "HS256"
    jwt_issuer: str = "naegajjanday"
    access_token_ttl_min: int = 15
    refresh_token_ttl_days: int = 14
    refresh_cookie_name: str = "rt"
    cookie_secure: bool = False
    cors_origins: CsvList = Field(
        default_factory=lambda: ["http://localhost:3000", "http://localhost:3100"]  # 3100 = preview:prod
    )
    webhook_secret: str | None = None

    # --- retention (what the web promises users; enforced by `purge-courses` / `purge-accounts`) ---
    unsaved_course_ttl_hours: int = Field(default=24, ge=1)  # never-saved courses are removed after this
    visit_retention_days: int = Field(default=365, ge=30)  # page views (docs/50) older than this are removed
    account_purge_grace_days: int = Field(default=30, ge=0)  # DELETE /v1/me → hard purge after this

    # --- OAuth2 (official endpoints are in core/security.py) ---
    kakao_client_id: str | None = None
    kakao_client_secret: str | None = None
    naver_client_id: str | None = None
    naver_client_secret: str | None = None
    google_client_id: str | None = None
    google_client_secret: str | None = None

    # --- rate limits: "count/window_seconds" (doc 03 §1) ---
    rate_limit_enabled: bool = True
    rl_generate_anon: str = "10/3600"
    rl_generate_user: str = "60/3600"
    rl_chat: str = "30/3600"
    rl_read: str = "300/60"
    rl_auth: str = "20/600"  # POST /auth/signup · /auth/login, per IP (password guessing)

    # --- LLM ---
    llm_provider: Literal["anthropic", "openai", "gemini", "none"] = "none"
    anthropic_api_key: str | None = None
    anthropic_model_smart: str = "claude-opus-5"
    anthropic_model_fast: str = "claude-haiku-4-5"
    anthropic_server_fallbacks: bool = True
    openai_api_key: str | None = None
    openai_model_smart: str = "gpt-4.1"
    openai_model_fast: str = "gpt-4.1-mini"
    gemini_api_key: str | None = None
    gemini_model_smart: str = "gemini-2.5-pro"
    gemini_model_fast: str = "gemini-2.5-flash"
    llm_timeout_s: float = 30.0
    narrative_inline_llm: bool = False

    # --- place providers (official Open APIs only) ---
    kakao_rest_api_key: str | None = None
    naver_search_client_id: str | None = None
    naver_search_client_secret: str | None = None
    google_places_api_key: str | None = None
    tourapi_service_key: str | None = None
    data_go_kr_service_key: str | None = None
    data_go_kr_category_hint: str = "attraction.park"  # canonical category.code for the dataset
    trusted_providers: CsvList = Field(default_factory=lambda: ["file", "admin", "tourapi"])
    # 공연예술통합전산망(KOPIS) Open API. Empty = the performances feature is off (no request is made).
    kopis_api_key: str = ""

    # --- routing providers ---
    travel_time_provider: Literal["haversine", "kakao", "tmap", "google"] = "haversine"
    kakao_mobility_api_key: str | None = None
    tmap_app_key: str | None = None
    google_routes_api_key: str | None = None

    # --- walking directions (path geometry shown on the map) ---
    # Any OSRM-compatible server with a foot profile. The default is the public FOSSGIS instance
    # (fair use, no key); production should point this at a self-hosted OSRM with the Korea extract.
    # Empty string disables it -> straight-line fallback.
    osrm_foot_url: str = "https://routing.openstreetmap.de/routed-foot"
    directions_timeout_s: float = 4.0

    # --- NAVER Maps (NAVER Cloud Platform · Maps) — Route Intelligence (docs/27) ---
    # Directions 5/15 are DRIVING only; walking uses the OSRM foot router above and transit stays an estimate
    # (no public NAVER transit API). Both values empty -> car legs keep the engine estimate. Server-side only:
    # the secret never reaches the browser.
    naver_map_client_id: str | None = None
    naver_map_client_secret: str | None = None
    naver_maps_base_url: str = "https://maps.apigw.ntruss.com"
    naver_timeout_s: float = 4.0
    route_cache_ttl_car_s: int = 600  # driving legs use live traffic -> short TTL
    route_cache_ttl_static_s: int = 86_400  # walking geometry / estimates do not change with traffic
    geocode_cache_ttl_s: int = 30 * 86_400
    transit_dir: Path = API_ROOT / "data" / "transit"
    media_dir: Path = API_ROOT / "data" / "media"  # curated open-licence category images
    upload_dir: Path | None = None  # operator-uploaded place photos; None = uploads.default_upload_dir()

    # --- analytics ---
    analytics_provider: Literal["none", "ga4", "posthog", "mixpanel"] = "none"
    ga4_measurement_id: str | None = None
    ga4_api_secret: str | None = None
    posthog_api_key: str | None = None
    posthog_host: str = "https://us.i.posthog.com"
    mixpanel_token: str | None = None

    # --- celery ---
    celery_broker_url: str | None = None
    celery_result_backend: str | None = None

    @field_validator("cors_origins", "trusted_providers", mode="before")
    @classmethod
    def _split_csv(cls, v: object) -> object:
        if isinstance(v, str):
            return [s.strip() for s in v.split(",") if s.strip()]
        return v

    @field_validator("database_url", mode="after")
    @classmethod
    def _async_driver(cls, v: str) -> str:
        # 관리형 Postgres(Render 등)는 `postgres://` · `postgresql://` 로 준다 → 비동기 드라이버를 붙인다.
        # 드라이버가 이미 적힌 URL(`postgresql+asyncpg://`, `sqlite+aiosqlite://`)은 그대로 둔다.
        for prefix in ("postgres://", "postgresql://"):
            if v.startswith(prefix):
                return "postgresql+asyncpg://" + v[len(prefix) :]
        return v

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    def parse_limit(self, spec: str) -> tuple[int, int]:
        count, window = spec.split("/")
        return int(count), int(window)


@lru_cache
def get_settings() -> Settings:
    return Settings()
