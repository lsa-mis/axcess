#!/usr/bin/env bash
# Idempotent setup: install deps, playwright chromium, pull Ollama models.
set -euo pipefail

cd "$(dirname "$0")/.."

echo "==> uv sync"
uv sync

echo "==> Playwright chromium"
uv run playwright install chromium

echo "==> Data directories"
mkdir -p data/blobs data/logs

echo "==> Migrations"
uv run yoyo apply --database "sqlite:///data/audit.db" --batch src/audit/db/migrations

echo "==> Fetch VLM models (optional; requires ollama daemon)"
if command -v ollama >/dev/null 2>&1; then
  ollama pull qwen2-vl:2b || true
  ollama pull moondream:2b || true
else
  echo "ollama not installed — skipping model download. See https://ollama.com"
fi

echo "==> Setup complete."
