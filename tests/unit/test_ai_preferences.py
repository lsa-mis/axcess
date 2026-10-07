"""Desktop AI choices persist independently of the downloaded files."""

from pathlib import Path
from unittest.mock import Mock

import pytest

from audit.ai.hardware import Hardware
from audit.ai.manager import AIBusyError, AIManager
from audit.ai.runtime import OllamaRuntime, RuntimeSetupError
from audit.ai.state import (
    AIConfig,
    AIPreferences,
    AIStateError,
    ai_enabled,
    effective_settings,
    initialize_preferences,
    load_config,
    load_preferences,
    save_config,
    save_preferences,
)
from audit.config import Settings
from audit.web.server import _build_crawl_config


def configured(settings: Settings, source: str = "private") -> AIConfig:
    config = AIConfig(
        source=source,
        base_url="http://127.0.0.1:1234",
        tier="small",
        text_model="text:test",
        vision_model="vision:test",
    )
    save_config(settings, config)
    return config


def test_fresh_choice_is_off_and_survives_restart(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path, desktop=True, suggestions_enabled=True)
    initialize_preferences(settings, existing_install=False)
    assert load_preferences(settings) == AIPreferences()
    assert not effective_settings(settings).suggestions_enabled
    save_preferences(settings, AIPreferences(enabled=False, choice_recorded=True))
    initialize_preferences(settings, existing_install=True)
    assert load_preferences(settings) == AIPreferences(enabled=False, choice_recorded=True)


@pytest.mark.parametrize("with_models", [False, True])
def test_existing_install_keeps_its_setting(tmp_path: Path, with_models: bool) -> None:
    settings = Settings(data_dir=tmp_path, desktop=True, suggestions_enabled=True)
    if with_models:
        configured(settings)
    initialize_preferences(settings, existing_install=True)
    assert load_preferences(settings).enabled
    assert load_preferences(settings).choice_recorded


def test_server_install_ignores_desktop_preference(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path, suggestions_enabled=True)
    save_preferences(settings, AIPreferences(enabled=False, choice_recorded=True))
    assert effective_settings(settings) is settings
    assert ai_enabled(settings)


def test_malformed_preference_fails_closed_and_reports_error(tmp_path: Path, caplog) -> None:
    settings = Settings(data_dir=tmp_path, desktop=True, suggestions_enabled=True)
    initialize_preferences(settings, existing_install=False)
    (tmp_path / "ai" / "preferences.json").write_text("{bad json")
    with pytest.raises(AIStateError, match="could not be read"):
        load_preferences(settings)
    assert not effective_settings(settings).suggestions_enabled
    assert "ai.preferences_unreadable" in caplog.text


@pytest.mark.parametrize("source", ["private", "system"])
def test_off_keeps_models_and_on_reuses_them(tmp_path: Path, source: str) -> None:
    settings = Settings(data_dir=tmp_path, desktop=True)
    config = configured(settings, source)
    marker = tmp_path / "ai" / "models" / "kept"
    marker.parent.mkdir()
    marker.write_text("model")
    runtime = Mock(spec=OllamaRuntime)
    runtime.start.return_value = config.base_url
    applied = []
    manager = AIManager(settings, applied.append, runtime=runtime)
    assert manager.set_enabled(False).enabled is False
    assert marker.read_text() == "model"
    assert load_config(settings) == config
    assert not effective_settings(settings).suggestions_enabled
    runtime.start.assert_not_called()
    manager.startup()
    runtime.start.assert_not_called()
    assert manager.set_enabled(True).enabled
    assert effective_settings(settings).suggestions_enabled
    runtime.remove.assert_not_called()
    runtime.download.assert_not_called()
    if source == "private":
        runtime.start.assert_called_once_with(preferred_url=config.base_url)
    else:
        runtime.start.assert_not_called()


def test_start_failure_keeps_ai_off(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path, desktop=True)
    configured(settings)
    save_preferences(settings, AIPreferences(enabled=False, choice_recorded=True))
    runtime = Mock(spec=OllamaRuntime)
    runtime.start.side_effect = RuntimeSetupError("Ollama could not start.")
    manager = AIManager(settings, Mock(), runtime=runtime)
    with pytest.raises(RuntimeSetupError, match="could not start"):
        manager.set_enabled(True)
    assert not load_preferences(settings).enabled


@pytest.mark.parametrize("operation", ["off", "remove"])
def test_busy_work_keeps_setting_and_runtime(tmp_path: Path, operation: str) -> None:
    settings = Settings(data_dir=tmp_path, desktop=True)
    configured(settings)
    runtime = Mock(spec=OllamaRuntime)
    manager = AIManager(
        settings, Mock(), runtime=runtime, busy_reason=lambda: "Finish the current scan."
    )
    with pytest.raises(AIBusyError, match="Finish the current scan"):
        manager.set_enabled(False) if operation == "off" else manager.remove()
    assert load_preferences(settings).enabled
    runtime.stop.assert_not_called()
    runtime.remove.assert_not_called()


def test_busy_download_prevents_toggle(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path, desktop=True)
    configured(settings)
    installer = Mock()
    installer.running = True
    manager = AIManager(settings, Mock(), installer=installer)
    with pytest.raises(AIBusyError, match="Pause the AI download"):
        manager.set_enabled(False)
    assert load_preferences(settings).enabled


def test_failed_application_rolls_back_preference(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path, desktop=True)
    configured(settings)
    save_preferences(settings, AIPreferences(enabled=False, choice_recorded=True))
    runtime = Mock(spec=OllamaRuntime)
    runtime.start.return_value = "http://127.0.0.1:1234"
    manager = AIManager(settings, Mock(side_effect=RuntimeError("worker failed")), runtime=runtime)
    with pytest.raises(RuntimeError, match="worker failed"):
        manager.set_enabled(True)
    assert not load_preferences(settings).enabled
    runtime.stop.assert_called_once()


def test_failed_setup_stops_private_runtime_while_ai_is_off(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path, desktop=True)
    runtime = Mock(spec=OllamaRuntime)
    manager = AIManager(
        settings,
        Mock(),
        runtime=runtime,
        probe=lambda: Hardware(16 * 1024**3, 100 * 10**9, True, None, "darwin", "arm64"),
        find_system=lambda: "0.33.0",
    )
    manager.installer.pull = Mock(side_effect=RuntimeSetupError("download stopped"))
    manager.install("small")
    assert manager.installer._thread is not None
    manager.installer._thread.join(3)
    assert not manager.installer.running
    assert manager.installer.status.state == "failed"
    assert not load_preferences(settings).enabled
    runtime.stop.assert_called_once()


def test_ai_off_preserves_regular_motion_checks(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path, desktop=True)
    save_preferences(settings, AIPreferences(enabled=False, choice_recorded=True))
    config = _build_crawl_config(
        {
            "url": "https://example.com",
            "skip_vlm": False,
            "skip_semantic": False,
            "skip_visual": False,
            "skip_ocr": False,
            "max_pages": 1,
            "max_depth": 1,
            "include_subdomain": False,
            "ignore_robots": False,
            "rps": 1,
            "workers": 1,
        },
        settings,
    )
    assert not config.vlm_enabled
    assert not config.semantic_enabled
    assert config.visual_checks_enabled
    assert config.ocr_enabled
