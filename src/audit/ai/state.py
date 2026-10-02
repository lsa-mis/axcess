"""The AI setup this computer chose, saved in ``data_dir/ai/config.json``.

Only the desktop app reads it. ``effective_settings`` lays it over the
environment settings, so a server or command-line install keeps working
exactly as configured by its administrator.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, ValidationError

from audit.config import Settings

SYSTEM_OLLAMA_URL = "http://127.0.0.1:11434"


class AIConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # "system": an Ollama the person already runs on port 11434.
    # "private": the pinned Ollama Axcess downloaded into ``data_dir/ai``.
    source: Literal["system", "private"]
    base_url: str
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
    config = load_config(settings)
    if config is None:
        return settings
    return settings.model_copy(
        update={
            "ollama_base_url": config.base_url,
            "vlm_model": config.vision_model,
            "suggestion_text_model": config.text_model,
            "suggestion_vision_model": config.vision_model,
            "suggestions_enabled": True,
        }
    )


def semantic_model(settings: Settings) -> str | None:
    """The one text model for scan-time checks, when the AI setup chose one."""
    if not settings.desktop:
        return None
    config = load_config(settings)
    return config.text_model if config else None
