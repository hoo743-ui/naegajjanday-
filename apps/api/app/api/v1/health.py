"""Liveness / readiness / metrics / internal webhooks (doc 03 §8). Mounted at the root, not under /v1."""

from __future__ import annotations

import hashlib
import hmac
import time
from typing import Annotated, Any

from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel
from sqlalchemy import func, select, text

from app.core import errors
from app.core.deps import Container, ContainerDep, SessionDep
from app.infra.db.base import utcnow
from app.infra.db.models import IngestionJob, RecommendationLog
from app.schemas.common import Ok

router = APIRouter(tags=["ops"])
STARTED_AT = time.time()


class ComponentStatus(BaseModel):
    status: str  # ok | down | disabled
    backend: str | None = None


class Readiness(BaseModel):
    status: str
    components: dict[str, ComponentStatus]


async def check_components(container: Container) -> dict[str, ComponentStatus]:
    out: dict[str, ComponentStatus] = {}
    try:
        async with container.db.engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        out["database"] = ComponentStatus(status="ok", backend=container.db.dialect)
    except Exception:
        out["database"] = ComponentStatus(status="down", backend=container.db.dialect)
    cache_ok = await container.cache.ping()
    out["cache"] = ComponentStatus(status="ok" if cache_ok else "down", backend=container.cache.backend)
    if container.search is None:
        out["search"] = ComponentStatus(status="disabled", backend="sql-fallback")
    else:
        ok = await container.search.ping()
        out["search"] = ComponentStatus(status="ok" if ok else "down", backend=container.search.backend)
    out["llm"] = ComponentStatus(
        status="ok" if container.llm.available else "disabled", backend=container.llm.name
    )
    return out


@router.get("/healthz", response_model=Ok, summary="liveness")
async def healthz() -> Ok:
    return Ok()


@router.get("/readyz", response_model=Readiness, responses={503: {"model": Readiness}}, summary="readiness")
async def readyz(container: ContainerDep) -> JSONResponse:
    components = await check_components(container)
    # search/llm are optional (fallbacks exist); only the database and cache gate readiness
    ready = all(components[k].status == "ok" for k in ("database", "cache"))
    body = Readiness(status="ready" if ready else "not_ready", components=components)
    return JSONResponse(body.model_dump(), status_code=200 if ready else 503)


@router.get("/metrics", response_class=PlainTextResponse, summary="Prometheus (내부망 전용)")
async def metrics(session: SessionDep) -> str:
    total = await session.scalar(select(func.count(RecommendationLog.id))) or 0
    avg_latency = await session.scalar(select(func.avg(RecommendationLog.latency_ms))) or 0
    lines = [
        "# TYPE njd_uptime_seconds gauge",
        f"njd_uptime_seconds {time.time() - STARTED_AT:.0f}",
        "# TYPE njd_recommendations_total counter",
        f"njd_recommendations_total {total}",
        "# TYPE njd_recommendation_latency_ms_avg gauge",
        f"njd_recommendation_latency_ms_avg {float(avg_latency):.1f}",
    ]
    return "\n".join(lines) + "\n"


class IngestionWebhook(BaseModel):
    job_id: int
    status: str
    error: str | None = None


@router.post("/internal/webhooks/ingestion", response_model=Ok, summary="배치 완료 콜백 (HMAC 서명 검증)")
async def ingestion_webhook(
    request: Request,
    container: ContainerDep,
    session: SessionDep,
    x_signature: Annotated[str | None, Header()] = None,
) -> Ok:
    secret = container.settings.webhook_secret
    if not secret:
        raise errors.ServiceUnavailable("WEBHOOK_SECRET 이 설정되지 않았어요.")
    raw = await request.body()
    expected = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    if not x_signature or not hmac.compare_digest(expected, x_signature.removeprefix("sha256=")):
        raise errors.Unauthorized("서명이 올바르지 않아요.")
    payload = IngestionWebhook.model_validate_json(raw)
    job: Any = await session.get(IngestionJob, payload.job_id)
    if job is None:
        raise errors.NotFound()
    job.status, job.error, job.finished_at = payload.status, payload.error, utcnow()
    await session.commit()
    return Ok()
