"""The Ollama requests did not change when the call sites moved to the client.

Each ``_old_*`` builder below is a verbatim copy of the payload code each
call site had before ``audit.ai.model_client`` existed (commit 3d10fac).
Each test drives the moved call site through a fake transport and compares
the bytes it sent with the bytes httpx makes from the old payload.

Three call sites send identical bytes. Two now write their keys in the
client's one fixed order: the semantic text check with JSON output on
(``format`` used to come last) and fix suggestions with an image
(``images`` used to come last). For those the test compares the bodies with
keys sorted, which still pins every key, value and value type (``0`` versus
``0.0``). Ollama decodes the body into a struct, so key order cannot change
what it does. Verified only against fakes: no real Ollama ran here.
"""

from __future__ import annotations

import base64
import json
from typing import Any

import httpx
import pytest

from audit.analyzer.semantic.ollama_text import OllamaTextProvider
from audit.analyzer.vlm.base import ClassifyContext
from audit.analyzer.vlm.ollama import OllamaProvider, _for_prompt, load_prompt
from audit.analyzer.vlm.vision import OllamaVisionProvider
from audit.protected.local_ai import ProtectedLocalOllama
from audit.suggest.provider import (
    ANSWER_SCHEMA,
    CONTEXT_TOKENS,
    KEEP_ALIVE,
    MAX_ANSWER_TOKENS,
    OllamaSuggestionProvider,
)

BASE = "http://127.0.0.1:11434"
IMAGE = b"\x89PNG\r\n\x1a\n-image-bytes-\x00\xff"


def _wire(payload: dict[str, Any]) -> bytes:
    """The bytes httpx sends for ``json=payload``, as the old code did."""
    return httpx.Request("POST", f"{BASE}/api/generate", json=payload).content


def _sorted(content: bytes) -> str:
    return json.dumps(json.loads(content), sort_keys=True)


class _Capture:
    def __init__(self, reply: dict[str, Any]) -> None:
        self.requests: list[httpx.Request] = []
        self._reply = reply

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return httpx.Response(200, json=self._reply)

    @property
    def body(self) -> bytes:
        assert len(self.requests) == 1
        assert self.requests[0].url.path == "/api/generate"
        return self.requests[0].content


# --- old payload code, copied verbatim ---------------------------------------


def _old_vlm_classify(model: str, filled: str, image_bytes: bytes) -> dict[str, Any]:
    return {
        "model": model,
        "prompt": filled,
        "images": [base64.b64encode(image_bytes).decode("ascii")],
        "stream": False,
        "format": "json",
        "options": {"temperature": 0.0},
    }


_old_vision_describe = _old_vlm_classify  # identical code in vision.py


def _old_protected(model: str, prompt: str, image: bytearray) -> dict[str, Any]:
    return {
        "model": model,
        "prompt": prompt,
        "images": [base64.b64encode(bytes(image)).decode("ascii")],
        "stream": False,
        "format": "json",
        "options": {"temperature": 0.0},
    }


def _old_semantic(
    model: str, prompt: str, keep_alive: str | int, temperature: float, force_json: bool
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "keep_alive": keep_alive,
        "options": {"temperature": temperature},
    }
    if force_json:
        payload["format"] = "json"
    return payload


def _old_suggest(model: str, prompt: str, image: bytes | None) -> dict[str, object]:
    payload: dict[str, object] = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "format": ANSWER_SCHEMA,
        "keep_alive": KEEP_ALIVE,
        "options": {
            "temperature": 0,
            "num_ctx": CONTEXT_TOKENS,
            "num_predict": MAX_ANSWER_TOKENS,
        },
    }
    if image is not None:
        payload["images"] = [base64.b64encode(image).decode("ascii")]
    return payload


# --- identical bytes -----------------------------------------------------------


async def test_vlm_classify_bytes_unchanged() -> None:
    capture = _Capture({"response": json.dumps({"label": "logo", "rationale": "r"})})
    context = ClassifyContext(
        alt_text="Banner", figcaption=None, context_snippet="A banner", ocr_text="BUY NOW"
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(capture)) as http:
        provider = OllamaProvider(http, model="qwen3-vl:2b-instruct", base_url=BASE)
        await provider.classify(IMAGE, "image/png", context)
    filled = load_prompt().format(
        alt=_for_prompt("Banner"),
        figcaption=_for_prompt(None),
        snippet=_for_prompt("A banner"),
        ocr=_for_prompt("BUY NOW"),
    )
    assert capture.body == _wire(_old_vlm_classify("qwen3-vl:2b-instruct", filled, IMAGE))
    # The per-request timeout is unchanged too.
    assert capture.requests[0].extensions["timeout"]["read"] == 120.0


async def test_vision_describe_bytes_unchanged() -> None:
    capture = _Capture({"response": "{}"})
    async with httpx.AsyncClient(transport=httpx.MockTransport(capture)) as http:
        provider = OllamaVisionProvider(http, model="qwen2-vl:7b", base_url=BASE)
        await provider.describe_json(IMAGE, "Is the reading order right?")
    assert capture.body == _wire(
        _old_vision_describe("qwen2-vl:7b", "Is the reading order right?", IMAGE)
    )


async def test_protected_bytes_unchanged() -> None:
    capture = _Capture(
        {"response": json.dumps({"contains_meaningful_text": True, "impact": "minor"})}
    )
    async with ProtectedLocalOllama(
        base_url=BASE, model="local-test", transport=httpx.MockTransport(capture)
    ) as local:
        assert await local.assess_image(bytearray(IMAGE)) is not None
    sent_prompt = json.loads(capture.body)["prompt"]
    assert capture.body == _wire(_old_protected("local-test", sent_prompt, bytearray(IMAGE)))
    # The prompt is the module's fixed text, not something the test chose.
    assert sent_prompt.startswith("You are reviewing one image for an authorized")


@pytest.mark.parametrize(("keep_alive", "temperature"), [(-1, 0.0), ("5m", 0.3)])
async def test_semantic_plain_text_bytes_unchanged(
    keep_alive: str | int, temperature: float
) -> None:
    capture = _Capture({"response": "free text"})
    async with httpx.AsyncClient(transport=httpx.MockTransport(capture)) as http:
        provider = OllamaTextProvider(
            http, model="qwen2.5:7b-instruct", base_url=BASE, keep_alive=keep_alive
        )
        await provider.generate(
            "PROMPT", model="qwen2.5:14b-instruct", force_json=False, temperature=temperature
        )
    assert capture.body == _wire(
        _old_semantic("qwen2.5:14b-instruct", "PROMPT", keep_alive, temperature, False)
    )


async def test_suggest_text_only_bytes_unchanged() -> None:
    capture = _Capture({"response": "{}"})
    async with httpx.AsyncClient(transport=httpx.MockTransport(capture)) as http:
        provider = OllamaSuggestionProvider(http, base_url=BASE, timeout_s=30)
        await provider.generate("PROMPT", model="coder:7b", image=None)
    assert capture.body == _wire(_old_suggest("coder:7b", "PROMPT", None))


# --- same keys, values and types; key order now fixed ---------------------------


async def test_semantic_json_mode_same_content() -> None:
    capture = _Capture({"response": "{}"})
    async with httpx.AsyncClient(transport=httpx.MockTransport(capture)) as http:
        provider = OllamaTextProvider(http, model="qwen2.5:7b-instruct", base_url=BASE)
        await provider.generate("PROMPT")
    old = _wire(_old_semantic("qwen2.5:7b-instruct", "PROMPT", -1, 0.0, True))
    assert _sorted(capture.body) == _sorted(old)
    # Only the position of "format" moved.
    assert list(json.loads(capture.body)) == [
        "model",
        "prompt",
        "stream",
        "format",
        "keep_alive",
        "options",
    ]


async def test_suggest_with_image_same_content() -> None:
    capture = _Capture({"response": "{}"})
    async with httpx.AsyncClient(transport=httpx.MockTransport(capture)) as http:
        provider = OllamaSuggestionProvider(http, base_url=BASE, timeout_s=30)
        await provider.generate("PROMPT", model="vision:7b", image=IMAGE)
    assert _sorted(capture.body) == _sorted(_wire(_old_suggest("vision:7b", "PROMPT", IMAGE)))
    # Only the position of "images" moved.
    assert list(json.loads(capture.body))[2] == "images"


# --- the model-list requests ------------------------------------------------------


async def test_model_list_requests_unchanged() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"models": [{"name": "m"}]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        await OllamaTextProvider(http, model="m", base_url=BASE + "/").healthy()
        await OllamaSuggestionProvider(http, base_url=BASE, timeout_s=30).installed_models()
    assert [(r.method, str(r.url), r.content) for r in seen] == [
        ("GET", f"{BASE}/api/tags", b""),
        ("GET", f"{BASE}/api/tags", b""),
    ]
    # Both used a 5 second timeout before and still do.
    assert [r.extensions["timeout"]["read"] for r in seen] == [5.0, 5.0]
