"""Tests for the general vision→JSON provider (screenshot + prompt → dict).

The HTTP layer (``_post_with_retries``) is stubbed so these stay offline and
deterministic — we're testing payload construction + JSON parsing + error
handling, not the live daemon.
"""

from __future__ import annotations

import base64
import json
from typing import Any

import httpx
import pytest

from audit.analyzer.ollama_base import OllamaError
from audit.analyzer.vlm.vision import OllamaVisionProvider


def _provider(monkeypatch: pytest.MonkeyPatch, *, raw: str | Exception) -> OllamaVisionProvider:
    client = httpx.AsyncClient()
    p = OllamaVisionProvider(client, model="qwen2-vl:7b")
    captured: dict[str, Any] = {}

    async def _stub(payload: dict[str, Any]) -> str:
        captured["payload"] = payload
        if isinstance(raw, Exception):
            raise raw
        return raw

    monkeypatch.setattr(p, "_post_with_retries", _stub)
    p.captured = captured  # type: ignore[attr-defined]
    return p


@pytest.mark.asyncio
async def test_describe_json_parses_object(monkeypatch: pytest.MonkeyPatch) -> None:
    p = _provider(monkeypatch, raw='{"reads_in_order": false, "reason": "left col first"}')
    out = await p.describe_json(b"\x89PNG_fake", "Is the reading order correct?")
    assert out == {"reads_in_order": False, "reason": "left col first"}


@pytest.mark.asyncio
async def test_describe_json_sends_image_and_prompt(monkeypatch: pytest.MonkeyPatch) -> None:
    p = _provider(monkeypatch, raw="{}")
    img = b"screenshot-bytes"
    await p.describe_json(img, "PROMPT TEXT")
    payload = p.captured["payload"]  # type: ignore[attr-defined]
    assert payload["model"] == "qwen2-vl:7b"
    assert payload["prompt"] == "PROMPT TEXT"
    assert payload["format"] == "json"
    assert payload["images"] == [base64.b64encode(img).decode("ascii")]


@pytest.mark.asyncio
async def test_describe_json_rejects_non_json(monkeypatch: pytest.MonkeyPatch) -> None:
    p = _provider(monkeypatch, raw="not json at all")
    with pytest.raises(OllamaError):
        await p.describe_json(b"x", "prompt")


@pytest.mark.asyncio
async def test_describe_json_rejects_non_object(monkeypatch: pytest.MonkeyPatch) -> None:
    p = _provider(monkeypatch, raw=json.dumps([1, 2, 3]))
    with pytest.raises(OllamaError):
        await p.describe_json(b"x", "prompt")


@pytest.mark.asyncio
async def test_describe_json_propagates_transport_error(monkeypatch: pytest.MonkeyPatch) -> None:
    p = _provider(monkeypatch, raw=OllamaError("daemon down"))
    with pytest.raises(OllamaError):
        await p.describe_json(b"x", "prompt")
