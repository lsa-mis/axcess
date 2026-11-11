# Moving the private AI service from Ollama to llama.cpp

Status: started 2026-11-11. Agreed in Slack: Harry Gu proposed the move and
Regan Maharjan agreed. Regan also asked to package the installation and
sandbox it inside Axcess Desktop.

## Why

| Reason | Detail (checked 2026-11-11) |
| --- | --- |
| Smaller download | llama.cpp release b12284: macOS arm64 17 MB, Linux x64 Vulkan 36 MB, Windows x64 Vulkan 38 MB. Our pinned Ollama 0.33.0: macOS 154 MB, Linux x64 1.42 GB, Windows x64 1.46 GB (`src/audit/ai/catalog.json`). Small enough to ship inside Axcess Desktop instead of downloading it. |
| Graphics cards | Vulkan builds cover AMD and Intel GPUs on Windows and Linux; macOS builds use Metal. |
| Control | Context size, seed, temperature, schema-constrained output and the model files are ours to pin, not a registry's. |
| Linux sandbox | `llama-server --host` accepts a UNIX socket path ending in `.sock` (server README). Inside Bubblewrap with `--unshare-net` the service has no network at all and Axcess still reaches it through a socket in the shared scratch folder. Today the Ollama service cannot be reached inside its network namespace, so private AI refuses to start on Linux (`IsolationError("namespace_unreachable")`, `ai/runtime.py`). |

Not a reason: speed. Ollama runs a llama.cpp-derived engine; any speed
difference must be measured on our machines before it is claimed.

## What exists today (the Ollama path)

- Five places call Ollama's native API directly (`/api/generate`, with
  `/api/tags` and `/api/version` as health checks):
  `analyzer/ollama_base.py` (image-of-text VLM and AI wording review),
  `analyzer/vlm/vision.py`, `suggest/provider.py` (AI fix suggestions),
  `protected/local_ai.py` (helper app), and a readiness check in
  `web/server.py`. They use `format` (JSON or a JSON schema), base64
  `images`, `temperature` 0, `num_ctx` and `keep_alive`.
- `ai/` (from rayraycodes-ai-fix-suggestions): `catalog.json` pins an
  Ollama binary per platform with SHA-256 and three model tiers (Small,
  Standard, Large: a Qwen text model plus a Qwen3-VL vision model each,
  pulled from `registry.ollama.ai` by `ai/downloader.py`); `runtime.py`
  downloads, verifies and starts it; `sandbox.py` isolates it
  (`sandbox-exec` on macOS, Bubblewrap on Linux, nothing on Windows);
  `installer.py` and `manager.py` drive Settings > AI features.

## Plan

### Phase 1: one model client, two backends (no installer change)

Started first because it changes nothing a user sees and every later
phase needs it.

- A typed model client in one module with a small interface: generate
  text from a prompt, optionally with one image and a JSON schema, at a
  fixed temperature and seed; check health; list the models it serves.
- Two backends behind it:
  - **Ollama (native API)**: today's behaviour, moved, not changed, so
    every existing scan, test and the "use my own Ollama" path keep
    working.
  - **llama.cpp (`llama-server`)**: its HTTP API over TCP or a UNIX
    socket (`httpx` supports `uds=`). Verify against a real
    `llama-server` which request shape carries both a JSON schema and
    an image in one call before relying on it.
- The five call sites use the client. A setting picks the backend.
  Analysis-model settings stay separate from any future chat-model
  settings (AGENTS.md).
- Tests with fake servers for both backends. No model downloads.

### Phase 2: llama.cpp inside Axcess Desktop, sandboxed

- Ship a pinned `llama-server` build in each desktop package, verified
  by SHA-256 at packaging time, like `desktop/ocr-runtime`: Metal on
  macOS, Vulkan on Windows and Linux, with a CPU build as the fallback.
  No CUDA or ROCm builds (170 MB to 600 MB each).
- Models become pinned GGUF files from Hugging Face, each with its
  SHA-256 and licence, plus the vision model's projector file
  (`--mmproj`). The tiers keep their sizes and memory guidance.
- One server in router mode (`--models-dir`, `--models-max`), or one
  process per model; decide after trying router mode with a text and a
  vision model.
- Sandbox: macOS `sandbox-exec` as now; Linux Bubblewrap with
  `--unshare-net` and a UNIX socket; Windows needs a design (none
  today, so private AI does not start there).
- Settings > AI features: the download is the model only.

### Phase 3: wording, docs and measurement

- Every "Ollama" in the interface and docs becomes accurate to the
  backend in use (`lib/terms.ts`, `docs/glossary.md`, setup page,
  errors).
- Re-measure the AI checks (image text, AI wording review, fix
  suggestions) on the new backend: the prompts were tuned on Ollama.
  This needs the user's approval for model downloads and real pages
  ("Building a check: real pages first").
- Then remove the private Ollama install; keep "use my own Ollama" only
  if the user decides to (see Decisions).

## Decisions

| # | Question | Recommendation | Decided |
| --- | --- | --- | --- |
| 1 | Keep "use my own Ollama" for the web and server versions? | Yes, through the Ollama backend; it costs little. | Open |
| 2 | GPU builds to ship | Metal (macOS), Vulkan (Windows, Linux), CPU fallback; no CUDA/ROCm. | Open |
| 3 | Windows isolation | Needs research: AppContainer, a firewall rule bound to the binary, or none with a clear warning. | Open |
| 4 | Which llama.cpp build to pin | A tested build number, updated on purpose; releases come out several times a day. | Open |
