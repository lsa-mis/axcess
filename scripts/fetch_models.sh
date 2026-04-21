#!/usr/bin/env bash
# Pull VLM models via Ollama. Idempotent; safe to re-run.
set -euo pipefail

if ! command -v ollama >/dev/null 2>&1; then
  echo "ollama not installed. Install from https://ollama.com" >&2
  exit 1
fi

echo "==> Pulling qwen2-vl:2b (default on Apple Silicon)"
ollama pull qwen2-vl:2b

echo "==> Pulling moondream:2b (CPU fallback)"
ollama pull moondream:2b

echo "==> Done."
