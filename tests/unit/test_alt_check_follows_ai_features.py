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
