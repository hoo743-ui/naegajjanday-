# 내가짠데이 - developer tasks (Linux / macOS / WSL / Git Bash).
# Windows PowerShell equivalent: .\scripts\dev.ps1 <target>
#
#   make help

SHELL := /bin/bash
.DEFAULT_GOAL := help

API_DIR := apps/api
WEB_DIR := apps/web
TF_DIR  := infra/terraform
COMPOSE := docker compose

# Root .env (optional) is handed to uv so host processes and compose share one file.
# Relative on purpose: the checkout path may contain spaces, which $(abspath) cannot handle.
UV_RUN := uv run $(if $(wildcard .env),--env-file ../../.env,)

.PHONY: help setup api-dev web-dev worker-dev test test-api test-web lint lint-api lint-web lint-infra fmt migrate seed \
        compose-up compose-up-all compose-down compose-logs compose-ps tf-validate

help: ## Show this help
	@grep -hE '^[a-zA-Z0-9_-]+:.*## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*## "} {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

setup: ## Install api + web dependencies and create .env
	@test -f .env || (cp .env.example .env && echo "created .env from .env.example")
	cd $(API_DIR) && uv sync
	cd $(WEB_DIR) && npm ci

api-dev: ## FastAPI with auto reload on :8000 (needs `make compose-up`)
	cd $(API_DIR) && $(UV_RUN) uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

web-dev: ## Next.js dev server on :3000
	cd $(WEB_DIR) && npm run dev

worker-dev: ## Celery worker on the host
	cd $(API_DIR) && $(UV_RUN) celery -A app.workers.celery_app worker --loglevel=INFO --concurrency=2

test: test-api test-web ## Run all tests

test-api: ## pytest with coverage
	cd $(API_DIR) && uv run --with pytest-cov pytest --cov=app --cov-report=term-missing

test-web: ## Type check the web app (unit / e2e runners are not set up yet)
	cd $(WEB_DIR) && npm run typecheck

lint: lint-api lint-web lint-infra ## Lint everything

lint-api: ## ruff + mypy
	cd $(API_DIR) && uv run ruff check . && uv run ruff format --check . && uv run mypy app

lint-web: ## eslint + tsc
	cd $(WEB_DIR) && npm run lint && npm run typecheck

lint-infra: ## terraform fmt -check (skipped when terraform is not installed)
	@if command -v terraform >/dev/null 2>&1; then terraform fmt -check -recursive $(TF_DIR); else echo "terraform not installed - skipped"; fi

fmt: ## Auto-format python and terraform
	cd $(API_DIR) && uv run ruff check --fix . && uv run ruff format .
	@if command -v terraform >/dev/null 2>&1; then terraform fmt -recursive $(TF_DIR); fi

migrate: ## Create / upgrade the local schema
	cd $(API_DIR) && if [ -f alembic.ini ]; then $(UV_RUN) alembic upgrade head; else $(UV_RUN) python -m app.cli db init; fi

seed: migrate ## Load scoring config + file-based seed places
	cd $(API_DIR) && $(UV_RUN) python -m app.cli seed-config
	cd $(API_DIR) && $(UV_RUN) python -m app.cli ingest --provider file --all

compose-up: ## Start postgres, redis, elasticsearch
	$(COMPOSE) up -d --wait postgres redis elasticsearch

compose-up-all: ## Start everything incl. api, worker, beat, web (builds images)
	$(COMPOSE) --profile app up -d --build

compose-down: ## Stop all containers (volumes are kept)
	$(COMPOSE) --profile app down

compose-logs: ## Follow container logs
	$(COMPOSE) --profile app logs -f --tail=100

compose-ps: ## Container status
	$(COMPOSE) --profile app ps

tf-validate: ## terraform validate for every stack (no backend, no credentials)
	@for d in bootstrap envs/shared envs/staging envs/prod; do \
		echo "== $$d"; (cd $(TF_DIR)/$$d && terraform init -backend=false -input=false >/dev/null && terraform validate) || exit 1; \
	done
