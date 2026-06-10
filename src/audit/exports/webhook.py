"""Env-gated webhook for posting scan results to an external collector.

Disabled by default. The caller must set ``AUDIT_WEBHOOK_URL`` to opt in;
optionally ``AUDIT_WEBHOOK_TOKEN`` is sent as a bearer header. The payload
is the same deterministic JSON that :func:`audit.exports.json_export.to_payload`
produces, plus a ``source`` field identifying this tool.

Dispatch is best-effort: network / HTTP errors are logged and swallowed so
a failing webhook never fails the scan itself.
"""

from __future__ import annotations

import os
from typing import Any

import httpx

from audit import __version__
from audit.exports.collector import ExportScan
from audit.exports.json_export import to_payload
from audit.logging import get_logger

log = get_logger(__name__)

ENV_URL = "AUDIT_WEBHOOK_URL"
ENV_TOKEN = "AUDIT_WEBHOOK_TOKEN"  # noqa: S105 (env var name, not a secret)
DEFAULT_TIMEOUT_S = 15.0


def is_enabled(env: dict[str, str] | None = None) -> bool:
    env = env if env is not None else dict(os.environ)
    return bool(env.get(ENV_URL, "").strip())


def build_payload(scan: ExportScan) -> dict[str, Any]:
    """Return the JSON body the webhook will POST."""
    payload = to_payload(scan)
    payload["source"] = {"tool": "accessible-accessibility", "version": __version__}
    return payload


async def post(
    scan: ExportScan,
    *,
    client: httpx.AsyncClient | None = None,
    env: dict[str, str] | None = None,
    timeout_s: float = DEFAULT_TIMEOUT_S,
) -> int | None:
    """POST the scan payload to the configured webhook.

    Returns the HTTP status code on success, or ``None`` when the webhook is
    disabled or an error occurred. Callers can log on ``None`` but must not
    depend on delivery.
    """
    env_map = env if env is not None else dict(os.environ)
    url = env_map.get(ENV_URL, "").strip()
    if not url:
        return None
    token = env_map.get(ENV_TOKEN, "").strip()
    headers = {
        "Content-Type": "application/json",
        "User-Agent": f"accessible-accessibility/{__version__}",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    payload = build_payload(scan)

    owned = client is None
    active = client or httpx.AsyncClient(timeout=timeout_s)
    try:
        resp = await active.post(url, headers=headers, json=payload)
    except httpx.HTTPError as exc:
        log.warning("webhook.post_failed", url=url, error=str(exc))
        return None
    finally:
        if owned:
            await active.aclose()

    if resp.status_code >= 400:
        log.warning(
            "webhook.non_ok_status",
            url=url,
            status=resp.status_code,
            body=resp.text[:200],
        )
    return int(resp.status_code)
