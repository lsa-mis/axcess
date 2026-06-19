.PHONY: help setup run serve test test-unit test-integration test-ui lint lint-fix typecheck migrate migrate-rollback fetch-models fixture-site a11y-check clean frontend-install frontend-build frontend-dev

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

fetch-analyzer-models: ## Pull every model the analyzer_models.yaml recommends (required + recommended tiers)
	@command -v ollama >/dev/null 2>&1 || { echo "ollama not installed; see https://ollama.com"; exit 1; }
	@$(PY) python -c "from audit.analyzer.model_registry import all_fetch_tags; [print(t) for t in all_fetch_tags()]" \
		| while read tag; do echo ">>> ollama pull $$tag"; ollama pull "$$tag" || true; done

list-analyzer-models: ## Print the model recommendation matrix (per criterion)
	@$(PY) python -m audit.analyzer.model_registry_dump

fixture-site: ## Serve tests/fixtures/site on :8000 for crawler tests
	$(PY) python scripts/run_fixture_site.py

run: ## Start the review UI on http://$(HOST):$(PORT) (local dev, auto-reload)
	$(PY) uvicorn audit.web.server:app --host $(HOST) --port $(PORT) --reload

# SERVE_HOST defaults to 0.0.0.0 so other devices on your LAN / Tailscale
# net can reach it. Set AUDIT_ACCESS_TOKEN first — see docs/hosting.md.
SERVE_HOST ?= 0.0.0.0
serve: ## Host for LAN/Tailscale: no reload, binds 0.0.0.0 (set AUDIT_ACCESS_TOKEN!)
	@if [ -z "$$AUDIT_ACCESS_TOKEN" ]; then \
	  echo "WARNING: AUDIT_ACCESS_TOKEN is unset — the instance will be open to"; \
	  echo "         anyone who can reach $(SERVE_HOST):$(PORT). See docs/hosting.md."; \
	  echo "         Export a token, e.g.: export AUDIT_ACCESS_TOKEN=$$(openssl rand -hex 16)"; \
	  echo ""; \
	fi
	$(PY) uvicorn audit.web.server:app --host $(SERVE_HOST) --port $(PORT)

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
