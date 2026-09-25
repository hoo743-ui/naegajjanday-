# syntax=docker/dockerfile:1.7
# 내가짠데이 api — FastAPI 이미지 (non-root). api · worker · beat 가 같은 이미지를 쓰고 command 만 다르다.
#   docker build -t njd-api apps/api
#   docker run --rm -p 8000:8000 -e DATABASE_URL=postgresql+asyncpg://... -e JWT_SECRET=... njd-api
#
# 마이그레이션은 이미지가 하지 않는다. 배포 파이프라인(또는 compose 의 API_MIGRATE_CMD)이
# `alembic upgrade head` 를 먼저 돌린다.

FROM python:3.13-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
WORKDIR /app

# ── 1. 의존성 (uv.lock 고정, dev 그룹 제외) ────────────────
FROM base AS deps
COPY --from=ghcr.io/astral-sh/uv:0.5 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev

# ── 2. 실행 ────────────────────────────────────────────────
FROM base AS runner
ENV PATH="/app/.venv/bin:$PATH" \
    APP_ENV=production \
    LOG_JSON=true
# 실행에는 /app/.venv 만 쓴다. 시스템 pip(와 그 안에 번들된 msgpack · setuptools)는 필요 없고
# Trivy 가 HIGH 로 잡으므로 이미지에서 뺀다 (docs/56).
RUN groupadd -g 1001 app && useradd -u 1001 -g app -M -s /usr/sbin/nologin app \
 && rm -rf /usr/local/lib/python3.13/site-packages/pip /usr/local/lib/python3.13/site-packages/pip-* \
           /usr/local/lib/python3.13/ensurepip /usr/local/bin/pip /usr/local/bin/pip3*
COPY --from=deps /app/.venv ./.venv
COPY alembic.ini ./
COPY alembic ./alembic
COPY data ./data
COPY app ./app
USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=15s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=2)" || exit 1
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
