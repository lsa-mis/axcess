"""The llama.cpp backend against a real ``llama-server`` (opt-in).

Skipped unless ``AXCESS_LLAMA_SOCKET`` names the UNIX socket of a running
``llama-server`` that serves one vision model (started with ``--mmproj``).
Nothing here starts, stops or downloads anything. Optional:
``AXCESS_LLAMA_MODEL`` picks the model name; the default is the first one
the server lists.

These tests prove the request and response shapes work against a real
server: health, the model list, and JSON-schema output with and without an
image, plus two analyzer call sites switched to the backend. They do not
measure answer quality; the prompts were tuned on Ollama (plan, Phase 3).
"""

from __future__ import annotations

import asyncio
import functools
import http.server
import io
import json
import os
import shutil
import socketserver
import sqlite3
import threading
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from PIL import Image, ImageDraw, ImageFont

from audit.ai.model_client import (
    GenerateRequest,
    HealthState,
    ModelClient,
    ModelEndpoint,
    make_model_client,
    open_model_http_client,
)
from audit.analyzer.semantic.ollama_text import OllamaTextProvider
from audit.analyzer.vlm.vision import OllamaVisionProvider
from audit.crawler.orchestrator import CrawlConfig, run_crawl

FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "site"
SOCKET = os.environ.get("AXCESS_LLAMA_SOCKET", "")
pytestmark = pytest.mark.skipif(
    not SOCKET, reason="set AXCESS_LLAMA_SOCKET to a running llama-server's UNIX socket"
)
BASE = "http://llama"
TIMEOUT_S = 180.0

SUM_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"answer": {"type": "integer"}},
    "required": ["answer"],
    "additionalProperties": False,
}
IMAGE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "contains_text": {"type": "boolean"},
        "text": {"type": "string", "maxLength": 80},
    },
    "required": ["contains_text", "text"],
    "additionalProperties": False,
}


def _text_banner() -> bytes:
    image = Image.new("RGB", (480, 160), "white")
    draw = ImageDraw.Draw(image)
    draw.text((30, 40), "SALE 50% OFF", fill="black", font=ImageFont.load_default(size=56))
    out = io.BytesIO()
    image.save(out, format="PNG")
    return out.getvalue()


@pytest.fixture
async def llama_http() -> AsyncIterator[httpx.AsyncClient]:
    endpoint = ModelEndpoint("llama_cpp", BASE, SOCKET)
    async with open_model_http_client(endpoint, timeout=TIMEOUT_S) as client:
        yield client


@pytest.fixture
def client(llama_http: httpx.AsyncClient) -> ModelClient:
    return make_model_client("llama_cpp", llama_http, base_url=BASE)


@pytest.fixture
async def model(client: ModelClient) -> str:
    chosen = os.environ.get("AXCESS_LLAMA_MODEL")
    if chosen:
        return chosen
    models = await client.list_models()
    assert models, "llama-server lists no model"
    return models[0].name


async def test_health_and_model_list(client: ModelClient, model: str) -> None:
    health = await client.health()
    assert health.state is HealthState.READY, health
    models = await client.list_models()
    assert model in {m.name for m in models}
    assert all(m.size_bytes is None or m.size_bytes > 0 for m in models)
    assert await client.has_model(model)
    assert not await client.has_model("no-such-model")
    assert [m.name for m in await client.ready_models()] == [m.name for m in models]


async def test_text_with_schema_is_valid_and_repeatable(client: ModelClient, model: str) -> None:
    request = GenerateRequest(
        model=model,
        prompt="What is 2 + 3? Reply as JSON with the number in the field 'answer'.",
        json_schema=SUM_SCHEMA,
        temperature=0,
        seed=1,
        max_tokens=64,
    )
    first = await client.generate(request, timeout_s=TIMEOUT_S)
    parsed = json.loads(first)
    assert set(parsed) == {"answer"} and isinstance(parsed["answer"], int), first
    assert await client.generate(request, timeout_s=TIMEOUT_S) == first


# "image/png" sends a data: URL; None sends raw base64 (fix suggestions do).
@pytest.mark.parametrize("mime", ["image/png", None])
async def test_image_with_schema_in_one_call(
    client: ModelClient, model: str, mime: str | None
) -> None:
    raw = await client.generate(
        GenerateRequest(
            model=model,
            prompt=(
                "Does this image contain readable text? Reply as JSON: contains_text "
                "(true or false) and text (the words you can read, or an empty string)."
            ),
            image=_text_banner(),
            image_mime=mime,
            json_schema=IMAGE_SCHEMA,
            temperature=0,
            seed=1,
            max_tokens=128,
        ),
        timeout_s=TIMEOUT_S,
    )
    parsed = json.loads(raw)
    assert set(parsed) == {"contains_text", "text"}, raw
    assert isinstance(parsed["contains_text"], bool) and isinstance(parsed["text"], str)
    # Shown with -s; quality is not asserted (prompts were tuned on Ollama).
    print(f"llama-server image answer ({mime}): {raw}")


async def test_analyzer_call_sites_on_llama_cpp(llama_http: httpx.AsyncClient, model: str) -> None:
    vision = OllamaVisionProvider(
        llama_http, model=model, base_url=BASE, backend="llama_cpp", timeout_s=TIMEOUT_S
    )
    assert await vision.healthy()
    described = await vision.describe_json(
        _text_banner(),
        "Reply with a JSON object with one field, 'words', listing the words in the image.",
    )
    assert isinstance(described, dict)

    text = OllamaTextProvider(
        llama_http, model=model, base_url=BASE, backend="llama_cpp", timeout_s=TIMEOUT_S
    )
    parsed = await text.generate_json(
        "Reply with a JSON object with one boolean field 'ok' set to true."
    )
    assert isinstance(parsed, dict)
    print(f"llama-server call-site answers: {described} {parsed}")


@pytest.mark.skipif(shutil.which("tesseract") is None, reason="tesseract not installed")
def test_crawl_classifies_images_through_the_socket(
    tmp_db: sqlite3.Connection, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A real crawl of the local fixture site reaches llama-server via the socket.

    Exercises the orchestrator's own socket client (``model_socket``), not
    one the test passes in.
    """
    blob_dir = tmp_path / "blobs"
    blob_dir.mkdir()
    monkeypatch.setenv("AUDIT_BLOB_DIR", str(blob_dir))
    with httpx.Client(transport=httpx.HTTPTransport(uds=SOCKET)) as sync_http:
        listed = sync_http.get(f"{BASE}/v1/models").json()["data"]
    model = os.environ.get("AXCESS_LLAMA_MODEL") or listed[0]["id"]

    handler = functools.partial(_QuietHandler, directory=str(FIXTURE_ROOT))
    with socketserver.TCPServer(("127.0.0.1", 0), handler) as site:
        thread = threading.Thread(target=site.serve_forever, daemon=True)
        thread.start()
        try:
            summary = asyncio.run(
                run_crawl(
                    tmp_db,
                    CrawlConfig(
                        seed_url=f"http://127.0.0.1:{site.server_address[1]}/gallery.html",
                        js_eager=False,
                        max_pages=5,
                        rps=100.0,
                        workers=2,
                        ocr_max_workers=0,
                        vlm_enabled=True,
                        vlm_model=model,
                        vlm_base_url=BASE,
                        model_backend="llama_cpp",
                        model_socket=SOCKET,
                        semantic_enabled=False,
                        visual_checks_enabled=False,
                    ),
                )
            )
        finally:
            site.shutdown()
            thread.join(timeout=5)
    print(
        f"crawl: {summary.ocr_text_candidates} text candidates, "
        f"{summary.vlm_classified} classified, {summary.vlm_errors} errors"
    )
    assert summary.status == "completed"
    assert summary.ocr_text_candidates >= 1
    assert summary.vlm_classified >= 1
    assert summary.vlm_errors == 0


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        return
