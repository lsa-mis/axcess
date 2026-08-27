.PHONY: help setup run run-stable serve protected-maintenance test test-unit test-integration test-ui quality-gate detection-evals lint lint-fix typecheck migrate migrate-rollback fetch-models fixture-site a11y-check clean frontend-install frontend-lint frontend-build frontend-dev alfa-install desktop-install desktop-setup desktop-run desktop-test desktop-backend desktop-browsers desktop-ocr desktop-package

PY := uv run
DB := data/audit.db
MIGRATIONS := src/audit/db/migrations
FRONTEND := src/audit/web/frontend
ALFA_RUNNER := src/audit/alfa_runner
DESKTOP := desktop
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

fetch-models: ## Pull VLM models via Ollama (qwen3-vl:2b-instruct, moondream:2b)
	@command -v ollama >/dev/null 2>&1 || { echo "ollama not installed; see https://ollama.com"; exit 1; }
	ollama pull qwen3-vl:2b-instruct || true
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

run-stable: ## Start the local review UI without reloads (safe for long login scans)
	$(PY) uvicorn audit.web.server:app --host $(HOST) --port $(PORT)

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

protected-maintenance: ## Run required managed-KMS retention cleanup for protected reports
	$(PY) audit protected-maintenance

frontend-install: ## Install React SPA dependencies (one-time)
	cd $(FRONTEND) && npm install

frontend-lint: ## Run JSX accessibility and React lint rules
	cd $(FRONTEND) && npm run lint

frontend-build: ## Build the React SPA into dist/ (served by FastAPI at /app/)
	cd $(FRONTEND) && npm run build

frontend-dev: ## Run Vite dev server on :5173 (proxies /api to FastAPI)
	cd $(FRONTEND) && npm run dev

alfa-install: ## Install the optional, pinned Siteimprove Alfa local runner
	cd $(ALFA_RUNNER) && npm ci

desktop-install: ## Install the Electron desktop-shell dependencies
	cd $(DESKTOP) && npm ci

desktop-setup: frontend-install alfa-install desktop-install ## Prepare desktop development
	uv sync --group desktop

desktop-run: frontend-build desktop-install ## Start Axcess as a desktop application
	cd $(DESKTOP) && npm start

desktop-test: ## Run desktop launcher and migration tests
	cd $(DESKTOP) && npm test
	$(PY) pytest tests/unit/test_desktop_server.py tests/unit/test_alfa_scan_engine.py

desktop-backend: frontend-build alfa-install ## Bundle the Python/React/Alfa backend sidecar
	uv sync --group desktop
	$(PY) pyinstaller --clean --noconfirm --distpath $(DESKTOP)/backend-dist --workpath build/desktop-pyinstaller $(DESKTOP)/backend.spec

desktop-browsers: ## Bundle the platform-matched Chromium used by Playwright
	PLAYWRIGHT_BROWSERS_PATH="$(CURDIR)/$(DESKTOP)/playwright-browsers" $(PY) playwright install chromium

desktop-ocr: ## Bundle the platform-matched relocatable Tesseract OCR runtime
ifeq ($(OS),Windows_NT)
	powershell -NoProfile -ExecutionPolicy Bypass -File "$(DESKTOP)/scripts/bundle-tesseract-windows.ps1"
else
	$(DESKTOP)/scripts/bundle-tesseract-macos.sh
endif

desktop-package: desktop-install desktop-backend desktop-browsers desktop-ocr ## Build this platform's installer
	cd $(DESKTOP) && npm run make

test: ## Run full test suite
	$(PY) pytest

test-unit: ## Run unit tests only
	$(PY) pytest tests/unit

test-integration: ## Run integration tests only
	$(PY) pytest tests/integration -m integration

test-ui: ## Run UI tests (Playwright + axe-core)
	$(PY) pytest tests/ui -m ui

quality-gate: ## Enforce the versioned labeled detector precision gate (<5% corpus FDR)
	$(PY) python -m audit.quality_benchmark tests/quality/corpora/detection_precision_v1.json
	$(PY) pytest tests/quality

detection-evals: ## Evaluate detector efficacy plus evidence-path efficiency and scale
	$(PY) python -m audit.detection_evals \
		--config tests/quality/detection_eval_config.json \
		--output-dir artifacts/detection-evals

a11y-check: ## Run axe-core accessibility checks against the UI
	$(PY) pytest tests/ui -m ui -k axe

lint: ## Check lint + format
	$(PY) ruff check src tests scripts
	$(PY) ruff format --check src tests scripts
	cd $(FRONTEND) && npm run lint

lint-fix: ## Apply lint + format fixes
	$(PY) ruff check --fix src tests scripts
	$(PY) ruff format src tests scripts
	cd $(FRONTEND) && npm run lint:fix

typecheck: ## Run mypy strict on src/
	$(PY) mypy
	cd $(FRONTEND) && npm run typecheck

clean: ## Remove database and blob storage (irreversible)
	rm -rf data/audit.db data/audit.db-wal data/audit.db-shm data/blobs data/logs
