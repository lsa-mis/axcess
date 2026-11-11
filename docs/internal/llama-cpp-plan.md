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

Done 2026-11-11 (`src/audit/ai/model_client.py`; settings `model_backend`,
`llama_cpp_url`, `llama_cpp_socket`). Verified against a real
llama-server (b12284, CPU build, Qwen3-VL-2B Q4_K_M with its projector,
UNIX socket): `/v1/chat/completions` carries an image (data URL or raw
base64) and a JSON schema (`response_format` `json_schema`, `strict`) in
one call, answers are schema-valid and repeat exactly at temperature 0
and seed 1, and a crawl of the local fixture site classified image text
through it. Opt-in test: `AXCESS_LLAMA_SOCKET=<socket> pytest
tests/integration/test_llama_cpp_live.py`. Ollama request parity is
checked against copies of the old code only (no live Ollama run); two
bodies have one key in a new position, same keys and values.

Carried into Phase 2:
- The launcher sets the context size (`-c`) to at least 8192 (fix
  suggestions ask for 8192; llama.cpp takes it at launch, not per
  request) and `--alias` to the model names Axcess asks for.
- A saved desktop AI setup forces `model_backend="ollama"` until the
  private runtime's trust check knows llama.cpp
  (`ai/state.py: effective_settings`).
- Protected scans (helper app) and local sign-in scans still use Ollama:
  their locality checks are written for loopback Ollama URLs and need a
  socket-aware check.
- `ai/runtime.py: ollama_version()` belongs to the private Ollama
  installer and goes with it.
- Not yet checked on a real server: the 503 "loading" health state,
  router mode, `--alias` naming, `max_tokens` cut-off, and error bodies.

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
  `--unshare-net` and a UNIX socket. Windows: see
  `docs/internal/windows-ai-sandbox.md` (research, 2026-11-11). It
  recommends an LPAC AppContainer with no network capabilities inside a
  job object, started by a small native launcher (Python's `subprocess`
  cannot set AppContainer capabilities). Unconfirmed and to test first:
  whether the official Windows llama-server build listens on AF_UNIX,
  whether an AF_UNIX socket made inside the AppContainer is reachable
  from outside it, and whether Vulkan works inside an LPAC. Python has
  no AF_UNIX on Windows, so the backend needs a shim or a bridge.
- Router mode starts its child servers on loopback TCP, which an LPAC
  blocks; plan on one llama-server process per model.
- Likely bug to fix in this phase (found by reading, not yet run): the
  sandbox's network probe runs `sys.executable -I -S -c ...`. In the
  packaged desktop app `sys.executable` is the frozen backend, whose
  entry point (`desktop/backend_entry.py`) ignores those flags and
  starts the server, so the probe would fail and private AI would never
  start in the packaged app, macOS included. Confirm on a packaged
  build; the native launcher (or an explicit probe entry point) fixes it.
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
| 1 | Keep "use my own Ollama" for the web and server versions? | Yes, through the Ollama backend; it costs little. | Yes, as recommended (2026-11-11; not yet confirmed by the developer) |
| 2 | GPU builds to ship | Metal (macOS), Vulkan (Windows, Linux), CPU fallback; no CUDA/ROCm. | Yes (developer, 2026-11-11) |
| 3 | Windows isolation | Needs research: AppContainer, a firewall rule bound to the binary, or none with a clear warning. | Research first (developer, 2026-11-11) |
| 4 | Which llama.cpp build to pin | A tested build number, updated on purpose; releases come out several times a day. | Open |
| 5 | Test Phase 1 against a real llama-server | Download one llama.cpp build and one small model, outside the repo. | Approved (developer, 2026-11-11) |
