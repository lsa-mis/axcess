"""The cloud-model guard against a real Ollama daemon (gated).

``audit.analyzer.ollama_base.why_not_local`` relies on Ollama's documented
``/api/tags`` shape (https://docs.ollama.com/api/tags): each model an object
with ``name`` and ``model``, and ``remote_host`` / ``remote_model`` set only
for a model that runs on another host. The unit tests mock that shape; this
test reads a real daemon's list, so a daemon that changes the shape is
caught. It reads the list only and sends nothing to any model.

Run with ``AUDIT_OLLAMA_LIVE=1`` (the same gate as the live semantic
calibration). With ``AUDIT_OLLAMA_CLOUD_ALIAS`` set to a model name made
with ``ollama cp <a cloud model> <name>``, it also checks that the alias is
refused. Making that alias signs in to ollama.com, so it is never done here.
"""

from __future__ import annotations

import os

import httpx
import pytest

from audit.analyzer.ollama_base import model_list, why_not_local

pytestmark = pytest.mark.skipif(
    os.environ.get("AUDIT_OLLAMA_LIVE") != "1",
    reason="set AUDIT_OLLAMA_LIVE=1 to read a real Ollama daemon's model list",
)

BASE = os.environ.get("AUDIT_OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")


@pytest.mark.asyncio
async def test_the_daemon_list_has_the_documented_shape_and_local_models_pass() -> None:
    async with httpx.AsyncClient(trust_env=False) as client:
        listed = await model_list(client, f"{BASE}/api/tags")
        assert listed is not None, "the daemon's /api/tags is not the documented shape"
        local, _remote = listed
        if not local:
            pytest.skip("no local model installed")
        for name in sorted(local):
            assert await why_not_local(client, f"{BASE}/api/tags", name) is None, name
        missing = "axcess-not-installed:1b"
        assert await why_not_local(client, f"{BASE}/api/tags", missing) is not None


@pytest.mark.skipif(
    not os.environ.get("AUDIT_OLLAMA_CLOUD_ALIAS"),
    reason="set AUDIT_OLLAMA_CLOUD_ALIAS to a local name for a cloud model",
)
@pytest.mark.asyncio
async def test_a_cloud_model_under_a_local_name_is_refused() -> None:
    alias = os.environ["AUDIT_OLLAMA_CLOUD_ALIAS"]
    async with httpx.AsyncClient(trust_env=False) as client:
        reason = await why_not_local(client, f"{BASE}/api/tags", alias)
    assert reason is not None and "cloud model" in reason
