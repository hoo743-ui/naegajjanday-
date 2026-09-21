# Local development with Docker Compose

`docker-compose.yml` lives in the repository root; this folder holds what it builds or mounts.

| Path | Used by | Purpose |
|---|---|---|
| `elasticsearch/Dockerfile` | `elasticsearch` | Elasticsearch 8.x + `analysis-nori` (Korean tokenizer used by the `places` index) |
| `postgres/init/01-extensions.sql` | `postgres` | `postgis`, `pg_trgm`, `unaccent` on first volume initialisation |

## Services

| Service | Image | Port | Profile | Health check |
|---|---|---|---|---|
| `postgres` | `postgis/postgis:16-3.4` | 5432 | default | `pg_isready` |
| `redis` | `redis:7-alpine` (`volatile-lru`, AOF) | 6379 | default | `redis-cli ping` |
| `elasticsearch` | built here, single node, security off | 9200 | default | `_cluster/health` >= yellow |
| `api` | `apps/api/Dockerfile` | 8000 | `app` | `GET /healthz` |
| `worker` | same image, `celery worker` | - | `app` | - |
| `beat` | same image, `celery beat` | - | `app` | - |
| `web` | `apps/web/Dockerfile` | 3000 | `app` | `GET /` |

Two ways of working:

```bash
cp .env.example .env

# 1) Infrastructure in Docker, code on the host with hot reload (day-to-day)
make compose-up            # Windows: .\scripts\dev.ps1 compose-up
make api-dev               # uvicorn --reload on :8000
make web-dev               # next dev on :3000

# 2) Everything in containers (checks the production images)
make compose-up-all        # docker compose --profile app up -d --build
```

`api` runs the migration command and then uvicorn; `worker` and `beat` wait until `api` is healthy, so they never start against an unmigrated schema. The migration command is `alembic upgrade head` (override with `API_MIGRATE_CMD` in `.env`).

Seed data: `make seed` (`python -m app.cli seed-config` + `python -m app.cli ingest --provider file --all`).

## Configuration

Everything is driven by the root `.env` (see `.env.example`); every variable has a default, so the stack also starts without one. Inside Compose the connection URLs (`DATABASE_URL`, `REDIS_URL`, `CELERY_*`, `ES_URL`) are always overridden with the service host names, so the same `.env` works for host processes (`localhost`) and containers.

`NEXT_PUBLIC_*` values are inlined by `next build`. The `web` image therefore receives them as build args; changing them needs `docker compose build web`.

## Expectations on the application Dockerfiles

These files belong to `apps/` and are not part of this folder. Compose, CI and ECS assume:

- `apps/api/Dockerfile`: Python 3.12, dependencies from `uv.lock`, the virtualenv's `bin` on `PATH` (so `alembic`, `uvicorn`, `celery`, `python -m app.cli` work without `uv run`), working directory = project root, non-root user, port 8000.
- `apps/web/Dockerfile`: multi-stage build using `output: "standalone"` (already set in `next.config.ts`), `ARG NEXT_PUBLIC_API_URL`, `ARG NEXT_PUBLIC_SITE_URL`, `ARG NEXT_PUBLIC_KAKAO_MAP_KEY` declared before `npm run build`, `CMD ["node", "server.js"]`, port 3000.

## Notes

- Elasticsearch needs `vm.max_map_count >= 262144` on Linux hosts; Docker Desktop (Windows / macOS) already sets it. If the container exits with code 78: `wsl -d docker-desktop sysctl -w vm.max_map_count=262144`.
- Heap defaults to 512 MB (`ES_JAVA_OPTS`). Give Docker Desktop at least 4 GB of memory for the full `app` profile.
- `pgvector` is not included in the `postgis/postgis` image. `user_preference.taste_vector` is optional in the ERD; switch the image if you start using it.
- AWS runs Amazon OpenSearch instead of Elasticsearch. The index settings are compatible, the Python client is not: see `infra/terraform/README.md`.
- Reset everything: `make compose-down` keeps volumes, `docker compose down -v` deletes them.
