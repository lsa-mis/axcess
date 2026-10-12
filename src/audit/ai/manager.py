"""Ties the catalogue, hardware check, runtime and installer together.

The web layer calls this; it knows nothing about FastAPI so unit tests can
drive it with fakes.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from typing import Literal

from pydantic import BaseModel

from audit.ai import hardware as hw
from audit.ai.catalog import Catalog, Tier, load_catalog
from audit.ai.installer import Installer, InstallStatus
from audit.ai.runtime import OllamaRuntime, RuntimeSetupError, system_ollama
from audit.ai.sandbox import IsolationError
from audit.ai.state import (
    AIConfig,
    AIPreferences,
    AIStateError,
    ai_dir,
    ai_enabled,
    clear_config,
    load_config,
    load_preferences,
    save_config,
    save_preferences,
    trust_private_runtime,
)
from audit.config import Settings


class ModelInfo(BaseModel):
    tag: str
    size_bytes: int
    licence: str


class TierPlan(BaseModel):
    id: Literal["small", "standard", "large"]
    label: str
    min_memory_gb: int
    text: ModelInfo
    vision: ModelInfo
    models_bytes: int
    download_bytes: int
    fits: bool


class HardwareInfo(BaseModel):
    memory_bytes: int
    free_disk_bytes: int
    accelerator: Literal["apple", "nvidia", "amd", "none"]


class ProgramInfo(BaseModel):
    version: str
    licence: str
    release_url: str
    download_bytes: int
    available_for_this_computer: bool
    system_version: str | None


class AIPlan(BaseModel):
    preferences: AIPreferences
    hardware: HardwareInfo
    program: ProgramInfo
    tiers: list[TierPlan]
    recommended: Literal["small", "standard", "large"] | None
    current: AIConfig | None
    install: InstallStatus


class AiRuntimeStatus(BaseModel):
    running: bool = False
    isolated: bool = False
    reason: str | None = None


class AiRuntimeStartResponse(BaseModel):
    state: Literal[
        "started",
        "already_running",
        "model_missing",
        "not_isolated",
        "system_ollama_not_managed",
        "ai_off",
        "not_desktop",
        "busy",
    ]
    isolated: bool = False
    reason: str | None = None
    download_bytes: int | None = None
    tier: Literal["small", "standard", "large"] | None = None


class NotEnoughSpaceError(Exception):
    """The data folder's disk cannot hold what this size still has to download."""


class AIBusyError(Exception):
    """An AI setting cannot change until active work finishes."""


class AIManager:
    def __init__(
        self,
        settings: Settings,
        on_change: Callable[[AIConfig | None], None],
        *,
        catalog: Catalog | None = None,
        runtime: OllamaRuntime | None = None,
        probe: Callable[[], hw.Hardware] | None = None,
        find_system: Callable[[], str | None] | None = None,
        installer: Installer | None = None,
        busy_reason: Callable[[], str | None] = lambda: None,
    ) -> None:
        self._start_lock = threading.Lock()
        self.settings = settings
        self.on_change = on_change
        self.catalog = catalog or load_catalog()
        self.dir = ai_dir(settings)
        self.runtime = runtime or OllamaRuntime(self.dir, self.catalog)
        self.probe = probe or (lambda: hw.probe(self.dir))
        self.find_system = find_system or system_ollama
        self.busy_reason = busy_reason
        self.installer = installer or Installer(
            self.catalog,
            self.runtime,
            self._installed,
            find_system=self.find_system,
            on_stopped=self._download_stopped,
        )

    def _download_stopped(self) -> None:
        if not ai_enabled(self.settings):
            self.runtime.stop()

    def _installed(self, config: AIConfig) -> None:
        if config.source == "private":
            trust_private_runtime(self.settings, config.base_url, self.runtime.running)
        previous_config = self.config()
        previous_preferences = self.preferences()
        try:
            save_config(self.settings, config)
            save_preferences(self.settings, AIPreferences(enabled=True, choice_recorded=True))
            self.on_change(config)
        except Exception:
            # Keep the last usable setup if applying the new one fails.
            if previous_config is None:
                clear_config(self.settings)
            else:
                save_config(self.settings, previous_config)
            save_preferences(self.settings, previous_preferences)
            raise

    def preferences(self) -> AIPreferences:
        return load_preferences(self.settings)

    def _require_idle(self) -> None:
        reason = (
            "Pause the AI download before changing AI settings."
            if self.installer.running
            else self.busy_reason()
        )
        if reason:
            raise AIBusyError(reason)

    def set_enabled(self, enabled: bool) -> AIPreferences:
        previous = self.preferences()
        self._require_idle()
        config = self.config()
        if enabled and config is not None and config.source == "private":
            url = self.runtime.start(preferred_url=config.base_url)
            trust_private_runtime(self.settings, url, self.runtime.running)
            config = config.model_copy(update={"base_url": url})
            save_config(self.settings, config)
        elif enabled and config is None:
            raise RuntimeSetupError(
                "AI is not set up yet. Choose a size and select Download and set up."
            )
        next_preferences = AIPreferences(enabled=enabled, choice_recorded=True)
        try:
            save_preferences(self.settings, next_preferences)
            self.on_change(config)
        except Exception:
            # Roll back the saved choice if the effective worker change failed.
            save_preferences(self.settings, previous)
            if not previous.enabled:
                self.runtime.stop()
            raise
        if not enabled:
            self.runtime.stop()
        return next_preferences

    def config(self) -> AIConfig | None:
        return load_config(self.settings)

    def plan(self) -> AIPlan:
        machine = self.probe()
        # Setup discovery reads only the program version, never a model.
        system = self.find_system()
        program_bytes = self.runtime.download_remaining()
        accelerator: Literal["apple", "nvidia", "amd", "none"] = (
            "apple"
            if machine.apple_silicon
            else "nvidia"
            if machine.gpu == "NVIDIA"
            else "amd"
            if machine.gpu == "AMD"
            else "none"
        )
        recommended = hw.recommend(machine, self.catalog, program_bytes)
        release = self.catalog.ollama
        return AIPlan(
            preferences=self.preferences(),
            hardware=HardwareInfo(
                memory_bytes=machine.memory_bytes,
                free_disk_bytes=machine.free_disk_bytes,
                accelerator=accelerator,
            ),
            program=ProgramInfo(
                version=release.version,
                licence=release.licence,
                release_url=release.release_url,
                download_bytes=program_bytes,
                available_for_this_computer=self.runtime.asset is not None,
                system_version=system,
            ),
            tiers=[
                TierPlan(
                    id=t.id,
                    label=t.label,
                    min_memory_gb=t.min_memory_gb,
                    text=ModelInfo(tag=t.text.tag, size_bytes=t.text.size, licence=t.text.licence),
                    vision=ModelInfo(
                        tag=t.vision.tag, size_bytes=t.vision.size, licence=t.vision.licence
                    ),
                    models_bytes=t.size,
                    download_bytes=t.size + program_bytes,
                    fits=hw.fits(machine, t, program_bytes),
                )
                for t in self.catalog.tiers
            ],
            recommended=recommended.id if recommended else None,
            current=self.config(),
            install=self.installer.status,
        )

    def install(self, tier_id: str) -> InstallStatus:
        preferences = self.preferences()
        tier = self.catalog.tier(tier_id)
        status = self.installer.status
        if not (self.installer.running and status.tier == tier_id):
            self._require_idle()
            self._check_space(tier, status)
        save_preferences(self.settings, preferences.model_copy(update={"choice_recorded": True}))
        return self.installer.start(tier)

    def _check_space(self, tier: Tier, status: InstallStatus) -> None:
        # What a paused run of the same size already wrote is on disk, so
        # only the rest needs room. Private models stay in the data folder.
        program = self.runtime.download_remaining()
        done = status.done_bytes if status.tier == tier.id else 0
        needed = max(0, tier.size + program - done) + hw.DISK_MARGIN
        free = self.probe().free_disk_bytes
        if free < needed:
            raise NotEnoughSpaceError(
                f"Not enough free disk space for the {tier.label} size: it needs about "
                f"{needed / 1e9:.1f} GB and {free / 1e9:.1f} GB is free. Free up space "
                "or choose a smaller size."
            )

    def pause(self) -> InstallStatus:
        status = self.installer.pause()
        if not self.preferences().enabled:
            self.runtime.stop()
        return status

    def remove(self) -> None:
        """Forget the setup; delete the private program and models if Axcess owns them.

        Models pulled into an Ollama the person already ran stay there: they
        may use them outside Axcess.
        """
        self._require_idle()
        self.installer.reset()
        self.runtime.remove()
        clear_config(self.settings)
        save_preferences(self.settings, AIPreferences(enabled=False, choice_recorded=True))
        self.on_change(None)

    def runtime_status(self) -> AiRuntimeStatus:
        config = self.config()
        if config is not None and config.source == "system":
            return AiRuntimeStatus(reason="system_ollama_not_managed")
        reason = self.runtime.isolation_reason
        if not self.runtime.running() and reason is None:
            try:
                self.runtime.require_isolation()
            except IsolationError as exc:
                reason = exc.reason
        return AiRuntimeStatus(
            running=self.runtime.running(),
            isolated=self.runtime.running(),
            reason=reason,
        )

    def start_runtime(self) -> AiRuntimeStartResponse:
        if not self.settings.desktop:
            return AiRuntimeStartResponse(state="not_desktop")
        if not self._start_lock.acquire(blocking=False):
            return AiRuntimeStartResponse(state="busy")
        try:
            if not self.preferences().enabled:
                return AiRuntimeStartResponse(state="ai_off")
            try:
                self._require_idle()
            except AIBusyError:
                return AiRuntimeStartResponse(state="busy")
            config = self.config()
            if config is not None and config.source == "system":
                return AiRuntimeStartResponse(state="system_ollama_not_managed")
            if self.runtime.running():
                return AiRuntimeStartResponse(state="already_running", isolated=True)
            try:
                self.runtime.require_isolation()
            except IsolationError as exc:
                return AiRuntimeStartResponse(state="not_isolated", reason=exc.reason)
            tier = self.catalog.tier(config.tier) if config else None
            if (
                not self.runtime.installed()
                or config is None
                or not all(
                    self.runtime.has_model(tag) for tag in (config.text_model, config.vision_model)
                )
            ):
                return AiRuntimeStartResponse(
                    state="model_missing",
                    tier=tier.id if tier else None,
                    download_bytes=(tier.size + self.runtime.download_remaining())
                    if tier
                    else None,
                )
            try:
                url = self.runtime.start(preferred_url=config.base_url)
            except IsolationError as exc:
                return AiRuntimeStartResponse(state="not_isolated", reason=exc.reason)
            except RuntimeSetupError:
                return AiRuntimeStartResponse(state="not_isolated", reason="runtime_failed")
            trust_private_runtime(self.settings, url, self.runtime.running)
            previous = config
            config = config.model_copy(update={"base_url": url})
            try:
                save_config(self.settings, config)
                self.on_change(config)
            except Exception:
                save_config(self.settings, previous)
                self.runtime.stop()
                return AiRuntimeStartResponse(state="not_isolated", reason="runtime_failed")
            return AiRuntimeStartResponse(state="started", isolated=True)
        finally:
            self._start_lock.release()

    def startup(self) -> None:
        """Start the private Ollama if the saved setup uses it."""
        config = self.config()
        try:
            enabled = self.preferences().enabled
        except AIStateError:
            logging.getLogger(__name__).exception("ai.preferences_unreadable")
            return
        if not enabled or config is None or config.source != "private":
            return
        try:
            url = self.runtime.start(preferred_url=config.base_url)
        except (RuntimeSetupError, IsolationError):
            logging.getLogger(__name__).exception("ai.runtime_start_failed")
            return
        trust_private_runtime(self.settings, url, self.runtime.running)
        if url != config.base_url:
            config = config.model_copy(update={"base_url": url})
            save_config(self.settings, config)
        self.on_change(config)

    def shutdown(self) -> None:
        self.installer.pause()
        self.runtime.stop()
