"""The Images tab's alt text check follows Settings > AI features (2026-11-16).

``_alt_checker_factory_for`` decides whether the check is on and with which
model: the administrator's ``AUDIT_ALT_CHECK_MODEL`` first, else in the
desktop app the vision model chosen in AI features. AI features off in the
desktop app turns the check off; a cloud model or an Ollama that is not on
this computer never runs it.
"""

from __future__ import annotations

from typing import Any

import pytest

from audit.config import Settings
from audit.web import server


def _settings(**values: Any) -> Settings:
    base = {
        "ollama_base_url": "http://127.0.0.1:11434",
        "alt_check_model": "",
        "vlm_model": "qwen2.5vl:7b",
    }
    return Settings(**{**base, **values})


def _model(factory: Any) -> str | None:
    if factory is None:
        return None
    return str(factory(object())._model)


@pytest.fixture
def desktop(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    state: dict[str, Any] = {"enabled": True, "config": object()}
    monkeypatch.setattr(server, "ai_enabled", lambda _s: state["enabled"])
    monkeypatch.setattr(server, "load_ai_config", lambda _s: state["config"])
    return state


def test_a_server_install_uses_only_the_administrators_model() -> None:
    assert server._alt_checker_factory_for(_settings()) is None
    assert _model(server._alt_checker_factory_for(_settings(alt_check_model="llava:13b"))) == (
        "llava:13b"
    )


def test_the_desktop_app_uses_the_ai_features_vision_model(desktop: dict[str, Any]) -> None:
    assert _model(server._alt_checker_factory_for(_settings(desktop=True))) == "qwen2.5vl:7b"
    # The administrator's model still comes first.
    chosen = _settings(desktop=True, alt_check_model="llava:13b")
    assert _model(server._alt_checker_factory_for(chosen)) == "llava:13b"


def test_ai_features_off_or_not_set_up_turns_the_check_off(desktop: dict[str, Any]) -> None:
    desktop["enabled"] = False
    assert server._alt_checker_factory_for(_settings(desktop=True, alt_check_model="llava")) is None
    desktop["enabled"] = True
    desktop["config"] = None
    assert server._alt_checker_factory_for(_settings(desktop=True)) is None


def test_a_cloud_model_or_a_remote_ollama_never_runs_it(desktop: dict[str, Any]) -> None:
    assert server._alt_checker_factory_for(_settings(alt_check_model="qwen3-vl:235b-cloud")) is None
    remote = _settings(alt_check_model="llava", ollama_base_url="http://192.168.1.20:11434")
    assert server._alt_checker_factory_for(remote) is None


@pytest.mark.parametrize(
    ("backend", "path"), [("llama_cpp", "/v1/chat/completions"), ("ollama", "/api/generate")]
)
async def test_the_alt_check_speaks_each_services_own_format(backend: str, path: str) -> None:
    """The check sent a hand-built Ollama body to every service; the private
    llama.cpp service (every desktop) could not read it, so each "Suggest alt
    text" failed with "did not give a usable answer" (Windows, 2026-11-17)."""
    import json

    import httpx

    from audit.analyzer.vlm.alt_check import AltCheckInput, OllamaAltChecker

    seen: list[httpx.Request] = []
    answer = (
        '{"verdict": "good", "reason": "It says what the picture shows.", '
        '"suggestion": "A bar chart of monthly rainfall"}'
    )

    def respond(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": "vision"}]})
        seen.append(request)
        if backend == "llama_cpp":
            return httpx.Response(200, json={"choices": [{"message": {"content": answer}}]})
        return httpx.Response(200, json={"response": answer})

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
        checker = OllamaAltChecker(
            http, model="vision", base_url="http://localhost", backend=backend
        )
        await checker.check(b"\x89PNG fake", AltCheckInput("A chart", "", None))
    assert [r.url.path for r in seen] == [path]
    body = json.loads(seen[0].content)
    if backend == "llama_cpp":
        parts = body["messages"][0]["content"]
        assert parts[0]["type"] == "image_url" and parts[1]["type"] == "text"
    else:
        # The answer's exact shape, so the suggestion cannot be left out.
        assert body["images"]
        assert body["format"]["required"] == ["verdict", "reason", "suggestion"]


def test_good_alt_text_with_no_suggestion_keeps_the_current_one() -> None:
    """Bonsai 2 answered "good" with an empty suggestion (2026-11-17); the
    prompt allows repeating good alt text, so that is what is kept."""
    from audit.analyzer.vlm.alt_check import OllamaError, parse_answer

    raw = '{"verdict": "good", "reason": "It says what it shows.", "suggestion": ""}'
    result = parse_answer(
        raw, has_alt=True, model="m", prompt_version="v", current_alt="Status legend"
    )
    assert result.suggestion == "Status legend" and result.verdict == "good"
    with pytest.raises(OllamaError, match="no suggestion"):
        parse_answer(
            raw.replace('"good"', '"needs_better"'),
            has_alt=True,
            model="m",
            prompt_version="v",
            current_alt="x",
        )


def test_images_sent_to_a_model_are_at_most_1024_px() -> None:
    import io

    from PIL import Image

    from audit.ai.model_image import fit_for_model

    big = io.BytesIO()
    Image.new("RGB", (1536, 1024), "white").save(big, format="PNG")
    data, mime = fit_for_model(big.getvalue())
    with Image.open(io.BytesIO(data)) as im:
        assert max(im.size) == 1024 and im.size == (1024, 683)
    assert mime == "image/jpeg"
    small = io.BytesIO()
    Image.new("RGBA", (300, 200)).save(small, format="PNG")
    assert fit_for_model(small.getvalue()) == (small.getvalue(), "image/png")
    assert fit_for_model(b"not an image") == (b"not an image", None)
