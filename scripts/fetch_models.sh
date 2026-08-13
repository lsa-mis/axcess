#!/usr/bin/env bash
# Pull VLM models via Ollama. Idempotent; safe to re-run.
set -euo pipefail

if ! command -v ollama >/dev/null 2>&1; then
  echo "ollama not installed. Install from https://ollama.com" >&2
  exit 1
fi

echo "==> Pulling qwen3-vl:2b-instruct (default local vision model)"
ollama pull qwen3-vl:2b-instruct

echo "==> Pulling moondream:2b (CPU fallback)"
ollama pull moondream:2b

echo "==> Done."
