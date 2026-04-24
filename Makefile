.PHONY: help setup run test test-unit test-integration test-ui lint lint-fix typecheck migrate migrate-rollback fetch-models fixture-site a11y-check clean frontend-install frontend-build frontend-dev

PY := uv run
DB := data/audit.db
MIGRATIONS := src/audit/db/migrations
FRONTEND := src/audit/web/frontend
HOST ?= 127.0.0.1
PORT ?= 8765

help:
	@awk 'BEGIN {FS = ":.*## "} /^[a-zA-Z_-]+:.*## / {printf "  %-20s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

setup: ## Install deps, Playwright chromium, and prepare data dirs
	uv sync
	uv run playwright install chromium
	mkdir -p data/blobs data/logs
	@echo "Setup complete. Run 'make migrate' then 'make fetch-models'."

migrate: ## Apply database migrations
	mkdir -p data
	$(PY) yoyo apply --database sqlite:///$(DB) --batch $(MIGRATIONS)

migrate-rollback: ## Roll back the last migration
	$(PY) yoyo rollback --database sqlite:///$(DB) --batch $(MIGRATIONS)

fetch-models: ## Pull VLM models via Ollama (qwen2-vl:2b, moondream:2b)
	@command -v ollama >/dev/null 2>&1 || { echo "ollama not installed; see https://ollama.com"; exit 1; }
	ollama pull qwen2-vl:2b || true
	ollama pull moondream:2b || true

fixture-site: ## Serve tests/fixtures/site on :8000 for crawler tests
	$(PY) python scripts/run_fixture_site.py

run: ## Start the review UI on http://$(HOST):$(PORT)
	$(PY) uvicorn audit.web.server:app --host $(HOST) --port $(PORT) --reload

frontend-install: ## Install React SPA dependencies (one-time)
	cd $(FRONTEND) && npm install

frontend-build: ## Build the React SPA into dist/ (served by FastAPI at /app/)
	cd $(FRONTEND) && npm run build

frontend-dev: ## Run Vite dev server on :5173 (proxies /api to FastAPI)
	cd $(FRONTEND) && npm run dev

test: ## Run full test suite
	$(PY) pytest

test-unit: ## Run unit tests only
	$(PY) pytest tests/unit

test-integration: ## Run integration tests only
	$(PY) pytest tests/integration -m integration

test-ui: ## Run UI tests (Playwright + axe-core)
	$(PY) pytest tests/ui -m ui

a11y-check: ## Run axe-core accessibility checks against the UI
	$(PY) pytest tests/ui -m ui -k axe

lint: ## Check lint + format
	$(PY) ruff check src tests scripts
	$(PY) ruff format --check src tests scripts

lint-fix: ## Apply lint + format fixes
	$(PY) ruff check --fix src tests scripts
	$(PY) ruff format src tests scripts

typecheck: ## Run mypy strict on src/
	$(PY) mypy

clean: ## Remove database and blob storage (irreversible)
	rm -rf data/audit.db data/audit.db-wal data/audit.db-shm data/blobs data/logs
