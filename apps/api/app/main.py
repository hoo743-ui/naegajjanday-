from __future__ import annotations

import asyncio
import contextlib
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.v1 import health
from app.api.v1.router import api_router
from app.core.cache import build_cache
from app.core.config import Settings, get_settings
from app.core.deps import Container
from app.core.errors import AppError, problem_body
from app.core.logging import configure_logging, get_logger, trace_id_var
from app.core.rate_limit import build_rate_limiter
from app.domain.routing.travel_time import (
    GoogleRoutesProvider,
    KakaoMobilityProvider,
    TmapProvider,
    TravelTimeProvider,
)
from app.infra import api_usage, uploads
from app.infra.analytics.factory import build_tracker
from app.infra.db.session import Database
from app.infra.llm.factory import build_llm
from app.infra.search.client import build_search
from app.prompts.loader import PromptLoader
from app.services import data_sync
from app.services import retention_service as retention

logger = get_logger(__name__)

PROBLEM_JSON = "application/problem+json"
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "geolocation=(self), camera=(), microphone=()",
    "Cross-Origin-Opener-Policy": "same-origin",
}
DOCS_PATHS = ("/v1/docs", "/v1/redoc", "/v1/openapi.json")
HTTP_TITLES = {404: ("NOT_FOUND", "찾을 수 없어요"), 405: ("METHOD_NOT_ALLOWED", "허용되지 않는 메서드예요")}


def build_travel_provider(settings: Settings) -> TravelTimeProvider | None:
    """None → haversine only. A missing key raises a clear error at startup."""
    name = settings.travel_time_provider
    if name == "kakao":
        return KakaoMobilityProvider(settings.kakao_mobility_api_key)
    if name == "tmap":
        return TmapProvider(settings.tmap_app_key)
    if name == "google":
        return GoogleRoutesProvider(settings.google_routes_api_key)
    return None


def build_container(settings: Settings) -> Container:
    return Container(
        settings=settings,
        db=Database(settings),
        cache=build_cache(settings.redis_url),
        rate_limiter=build_rate_limiter(settings.redis_url),
        llm=build_llm(settings),
        tracker=build_tracker(settings),
        prompts=PromptLoader(),
        search=build_search(settings),
        travel=build_travel_provider(settings),
    )


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level, settings.log_json)
    if settings.is_production and settings.jwt_secret.startswith("change-me"):
        raise RuntimeError("JWT_SECRET must be set in production")

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        container = build_container(settings)
        app.state.container = container
        api_usage.install(container.db)  # docs/47: count calls to external APIs with a quota
        logger.info(
            "app.start",
            env=settings.app_env,
            db=container.db.dialect,
            cache=container.cache.backend,
            search=container.search.backend if container.search else "sql-fallback",
            llm=container.llm.name,
        )
        # the privacy page promises page views are kept a year at most (docs/50): enforced at every start
        await retention.purge_old_visits(container.db, settings)
        await retention.clear_old_ips(container.db, settings)
        # docs/57: shipped data files (seed config, bulk deltas, anchors) the DB has not applied yet — in the
        # background, so the server answers its health check right away. Render's preDeploy has no disk.
        sync_task = (
            asyncio.create_task(data_sync.run_on_start(container.db, settings), name="data-sync")
            if data_sync.enabled_on_start(settings)
            else None
        )
        try:
            yield
        finally:
            if sync_task is not None and not sync_task.done():
                sync_task.cancel()  # an unfinished item is not recorded → applied again next start
                with contextlib.suppress(asyncio.CancelledError):
                    await sync_task
            await container.tracker.aclose()
            if container.search is not None:
                await container.search.aclose()
            await container.cache.aclose()
            await container.db.dispose()

    app = FastAPI(
        title="내가짠데이 API",
        version=settings.engine_version,
        description="AI 예산 기반 데이트·여행·식사 코스 최적화 API",
        lifespan=lifespan,
        docs_url="/v1/docs",
        redoc_url="/v1/redoc",
        openapi_url="/v1/openapi.json",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,  # explicit allowlist, never "*"
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "X-Request-ID", "X-Course-Key"],
        expose_headers=[
            "X-Request-ID",
            "X-RateLimit-Limit",
            "X-RateLimit-Remaining",
            "X-RateLimit-Reset",
            "Retry-After",
        ],
        max_age=600,
    )

    @app.middleware("http")
    async def request_context(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        incoming = request.headers.get("x-request-id", "")
        trace_id = incoming if 8 <= len(incoming) <= 64 and incoming.isascii() else uuid.uuid4().hex
        request.state.trace_id = trace_id
        token = trace_id_var.set(trace_id)
        started = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            trace_id_var.reset(token)
        response.headers["X-Request-ID"] = trace_id
        for key, value in SECURITY_HEADERS.items():
            response.headers.setdefault(key, value)
        if request.url.path not in DOCS_PATHS:
            response.headers.setdefault(
                "Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'"
            )
        if settings.is_production:
            response.headers.setdefault("Strict-Transport-Security", "max-age=63072000; includeSubDomains")
        logger.info(
            "http.request",
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            ms=round((time.perf_counter() - started) * 1000, 1),
            trace_id=trace_id,
        )
        return response

    def problem(
        request: Request,
        status: int,
        code: str,
        title: str,
        detail: str | None = None,
        meta: dict[str, Any] | None = None,
        errors: list[dict[str, Any]] | None = None,
        headers: dict[str, str] | None = None,
    ) -> JSONResponse:
        body = problem_body(
            type_base=settings.error_type_base,
            status=status,
            code=code,
            title=title,
            detail=detail,
            trace_id=getattr(request.state, "trace_id", None),
            meta=meta,
            errors=errors,
        )
        return JSONResponse(body, status_code=status, media_type=PROBLEM_JSON, headers=headers)

    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        return problem(request, exc.status, exc.code, exc.title, exc.detail, exc.meta, headers=exc.headers)

    @app.exception_handler(RequestValidationError)
    async def handle_validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        fields = [
            {"field": ".".join(str(p) for p in e["loc"] if p != "body"), "message": e["msg"]}
            for e in exc.errors()
        ]
        return problem(request, 422, "VALIDATION_ERROR", "입력값을 확인해 주세요", errors=fields)

    @app.exception_handler(StarletteHTTPException)
    async def handle_http(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code, title = HTTP_TITLES.get(
            exc.status_code, (f"HTTP_{exc.status_code}", "요청을 처리하지 못했어요")
        )
        detail = exc.detail if isinstance(exc.detail, str) and exc.status_code not in HTTP_TITLES else None
        return problem(request, exc.status_code, code, title, detail, headers=dict(exc.headers or {}))

    @app.exception_handler(Exception)
    async def handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("http.unhandled", path=request.url.path)
        return problem(request, 500, "INTERNAL_ERROR", "서버에 문제가 생겼어요")

    app.include_router(health.router)
    app.include_router(api_router, prefix="/v1")
    # operator-uploaded place photos (infra.uploads). In production object storage + a CDN serve these.
    upload_dir = settings.upload_dir or uploads.default_upload_dir()
    upload_dir.mkdir(parents=True, exist_ok=True)
    app.mount(uploads.URL_PREFIX, StaticFiles(directory=upload_dir), name="uploads")
    return app


app = create_app()
