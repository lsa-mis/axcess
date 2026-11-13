"""The AI setup this computer chose, saved in ``data_dir/ai/config.json``.

Only the desktop app reads it. ``effective_settings`` lays it over the
environment settings, so a server or command-line install keeps working
exactly as configured by its administrator.
"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Callable
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, ValidationError, field_validator

from audit.config import Settings

SYSTEM_OLLAMA_URL = "http://127.0.0.1:11434"
log = logging.getLogger(__name__)
_PRIVATE_RUNTIMES: dict[Path, tuple[str, Callable[[], bool]]] = {}


def trust_private_runtime(settings: Settings, url: str, running: Callable[[], bool]) -> None:
    """Process-local proof, never a saved flag that could survive an unsafe restart."""
    _PRIVATE_RUNTIMES[ai_dir(settings).resolve()] = (url, running)


def private_runtime_url(settings: Settings, config: AIConfig) -> str:
    trusted = _PRIVATE_RUNTIMES.get(ai_dir(settings).resolve())
    if trusted is not None and trusted[0] == config.base_url and trusted[1]():
        return trusted[0]
    # A previous private port could now belong to an unisolated service. Never
    # send evidence there merely because its address is in the saved setup.
    return "http://127.0.0.1:0"


class AIStateError(Exception):
    """Saved AI choices cannot be read safely."""


class AIPreferences(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    enabled: bool = False
    choice_recorded: bool = False


def load_preferences(settings: Settings) -> AIPreferences:
    path = ai_dir(settings) / "preferences.json"
    try:
        return AIPreferences.model_validate_json(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        # Older installations had only the model setup file.
        configured = load_config(settings) is not None
        return AIPreferences(enabled=configured, choice_recorded=configured)
    except (OSError, ValueError) as exc:
        raise AIStateError(
            "Saved AI settings could not be read. AI is off to keep your choice safe. "
            "Check the application log before trying again."
        ) from exc


def save_preferences(settings: Settings, preferences: AIPreferences) -> None:
    path = ai_dir(settings) / "preferences.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(preferences.model_dump_json(indent=2), encoding="utf-8")
    os.replace(tmp, path)


def initialize_preferences(settings: Settings, *, existing_install: bool) -> None:
    if not settings.desktop or (ai_dir(settings) / "preferences.json").exists():
        return
    configured = load_config(settings) is not None
    save_preferences(
        settings,
        AIPreferences(
            enabled=configured or (existing_install and settings.suggestions_enabled),
            choice_recorded=existing_install or configured,
        ),
    )


def ai_enabled(settings: Settings) -> bool:
    if not settings.desktop:
        return True
    try:
        return load_preferences(settings).enabled
    except AIStateError:
        log.exception("ai.preferences_unreadable")
        return False


class AIConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # "system": an Ollama the person already runs on port 11434.
    # "private": the pinned Ollama Axcess downloaded into ``data_dir/ai``.
    source: Literal["system", "private"]
    base_url: str

    @field_validator("base_url")
    @classmethod
    def local_service_only(cls, value: str) -> str:
        parsed = urlsplit(value)
        if (
            parsed.scheme != "http"
            or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("The desktop AI service must use a local address on this computer.")
        return value.rstrip("/")

    tier: Literal["small", "standard", "large"]
    text_model: str
    vision_model: str
    ollama_version: str | None = None


def ai_dir(settings: Settings) -> Path:
    return Path(settings.data_dir) / "ai"


def config_path(settings: Settings) -> Path:
    return ai_dir(settings) / "config.json"


def load_config(settings: Settings) -> AIConfig | None:
    try:
        raw = json.loads(config_path(settings).read_text(encoding="utf-8"))
        return AIConfig.model_validate(raw)
    except (OSError, ValueError, ValidationError):
        return None


def save_config(settings: Settings, config: AIConfig) -> None:
    path = config_path(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(config.model_dump_json(indent=2), encoding="utf-8")
    os.replace(tmp, path)


def clear_config(settings: Settings) -> None:
    config_path(settings).unlink(missing_ok=True)


def effective_settings(settings: Settings) -> Settings:
    """Settings with the desktop AI setup applied, or unchanged if none."""
    if not settings.desktop:
        return settings
    enabled = ai_enabled(settings)
    config = load_config(settings)
    if config is None:
        if settings.suggestions_enabled == enabled:
            return settings
        return settings.model_copy(update={"suggestions_enabled": enabled})
    return settings.model_copy(
        update={
            "ollama_base_url": (
                private_runtime_url(settings, config)
                if config.source == "private"
                else config.base_url
            ),
            "vlm_model": config.vision_model,
            "suggestion_text_model": config.text_model,
            "suggestion_vision_model": config.vision_model,
            "suggestions_enabled": enabled,
        }
    )


def semantic_model(settings: Settings) -> str | None:
    """The one text model for scan-time checks, when the AI setup chose one."""
    if not settings.desktop:
        return None
    config = load_config(settings)
    return config.text_model if config else None
