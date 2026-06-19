# Hosting AccessibleAccessibility

This tool was built **local-first**: a single-user app that binds to
`127.0.0.1` with no authentication. That's the right default — but you
can host it for yourself and a small team on an always-on machine with
a few minutes of setup. This is the runbook for that ("Path A").

> **Before you expose it to anything beyond `localhost`, read the
> [Security](#security) section.** The app has no per-user accounts; the
> shared-token guard below is what keeps a network-reachable instance
> from being wide open.

---

## What "hosting" means here, and the honest caveats

* **One crawl at a time.** The server tracks the running crawl in a
  single process-global (`crawl_state` in `server.py`). If two people
  start scans at once, the second is rejected until the first finishes.
  Fine for a coordinating team; not multi-tenant. (Lifting this is
  "Path B" — replacing the global with the per-scan job queue.)
* **Heavy runtime.** Three of the four detection pipelines need a real
  browser, so the host must have Playwright + chromium installed
  (`make setup` does this). The image-of-text and semantic pipelines
  additionally need an [Ollama](https://ollama.com) daemon with the
  models pulled (`make fetch-models`); you can run without it (see
  [Without Ollama](#running-without-ollama)).
* **It's a crawler.** Anyone with access can point it at any URL. Keep
  access restricted to people you trust.

---

## Quick start (LAN, same network)

On the always-on machine, from the repo root:

```bash
# 1. One-time setup (deps, chromium, data dirs) — if not already done.
make setup
make migrate

# 2. Pick a shared token so the instance isn't open on your LAN.
export AUDIT_ACCESS_TOKEN=$(openssl rand -hex 16)
echo "Your token: $AUDIT_ACCESS_TOKEN"   # share this with your team

# 3. Build the SPA once (served at /app/).
make frontend-build

# 4. Host it. Binds 0.0.0.0 so other devices on the LAN can reach it.
make serve
```

Now anyone on the same network opens:

```
http://<machine-LAN-ip>:8765/app/?token=<the-token>
```

Find the machine's LAN IP with `ipconfig getifaddr en0` (macOS) or
`hostname -I` (Linux). The `?token=…` only needs to be pasted **once** —
the server sets a session cookie, so subsequent navigation works
without it.

A health check stays open without the token: `http://…:8765/health`.

---

## Reaching it off your network (Tailscale — recommended)

For team members who aren't on the same LAN, the cleanest path on your
own machine is [Tailscale](https://tailscale.com): a private mesh
network. No ports are exposed to the public internet, and only devices
you've added to your tailnet can connect.

```bash
# On the host machine:
#   1. Install Tailscale and sign in:  https://tailscale.com/download
#   2. Bring it up:
tailscale up
#   3. Note the machine's tailnet name / 100.x.y.z address:
tailscale ip -4
```

Run `make serve` as above. Team members (who've joined your tailnet)
reach it at:

```
http://<machine-tailscale-name>:8765/app/?token=<the-token>
```

Tailscale + the access token gives you two independent layers: the
network is private, and even within it the token is required.

> **Avoid raw public port-forwarding.** Opening `8765` on your router to
> the internet exposes an unauthenticated-by-default crawler to the
> world. If you genuinely need a public URL, use a
> [Cloudflare Tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/)
> with Cloudflare Access in front — that's closer to "Path C" territory
> and out of scope for this quick-start.

---

## Security

| Layer | What it does | How |
|---|---|---|
| **Shared token** | Blocks every request without the token (except `/health`). | `export AUDIT_ACCESS_TOKEN=…` before `make serve`. No-op when unset. |
| **Private network** | Keeps the port off the public internet. | LAN-only, or Tailscale. |

The token can be supplied three ways (the middleware checks all):

* `?token=…` in the URL (sets a cookie so you only do this once),
* an `X-Access-Token: …` request header (for API/CLI clients),
* an `Authorization: Bearer …` header.

The comparison is constant-time. The cookie is `HttpOnly` +
`SameSite=Lax` and is a session cookie (clears when the browser closes).

**This is deliberately a simple gate, not a multi-user auth system.**
It stops a network-reachable instance from being wide open. It does
*not* give people separate accounts, separate data, or audit logs —
that's Path B/C.

---

## Running without Ollama

If you don't want to run the local LLM daemon (it needs multi-GB models
and ideally a GPU), the tool still does plenty: axe-core, the
keyboard-trap probe, and the responsive/zoom probe all run on just
chromium. Start scans with the image-of-text + semantic pipelines off:

```bash
# CLI:
uv run audit crawl https://example.com --skip-vlm --skip-ocr --skip-semantic

# Or in the New Scan form, check "Skip VLM", "Skip OCR", and the
# semantic pipeline is skipped automatically when no Ollama is reachable.
```

The scan-detail "Methods used" row will show those pipelines struck
through, so anyone reading a report knows the coverage was partial.

---

## Keeping it running (autostart)

`make serve` runs in the foreground. To keep it up across reboots:

**macOS (launchd)** — create `~/Library/LaunchAgents/com.aa.serve.plist`
pointing at a small wrapper script that exports `AUDIT_ACCESS_TOKEN` and
runs `make serve` in the repo dir, then `launchctl load` it.

**Linux (systemd user service)** — a `~/.config/systemd/user/aa.service`
with `Environment=AUDIT_ACCESS_TOKEN=…`, `WorkingDirectory=<repo>`,
`ExecStart=/usr/bin/make serve`, then `systemctl --user enable --now aa`.

**Simplest** — run it inside `tmux`/`screen` so it survives your SSH
session disconnecting:

```bash
tmux new -s aa
export AUDIT_ACCESS_TOKEN=…
make serve
# detach with Ctrl-b d; reattach with `tmux attach -t aa`
```

---

## Upgrading later (Path B / C)

When one-crawl-at-a-time or the shared token stops being enough:

* **Path B (internal multi-user):** replace the process-global
  `crawl_state` with the SQLite-backed per-scan job queue the schema
  already supports, and swap the shared token for real accounts.
* **Path C (public SaaS):** add tenant isolation, per-user quotas, abuse
  controls on the crawler, and a hosted-GPU or cloud-LLM story to
  replace local Ollama.

Both are real projects, not config changes — the local-first design is
load-bearing. The quick-start above is the 95% case for a team.
