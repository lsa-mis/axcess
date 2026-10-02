"""Ties the catalogue, hardware check, runtime and installer together.

The web layer calls this; it knows nothing about FastAPI so unit tests can
drive it with fakes.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Literal

from pydantic import BaseModel

from audit.ai import hardware as hw
from audit.ai.catalog import Catalog, Tier, load_catalog
from audit.ai.installer import Installer, InstallStatus
from audit.ai.runtime import OllamaRuntime, RuntimeSetupError, system_ollama
from audit.ai.state import AIConfig, ai_dir, clear_config, load_config, save_config
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
    hardware: HardwareInfo
    program: ProgramInfo
    tiers: list[TierPlan]
    recommended: Literal["small", "standard", "large"] | None
    current: AIConfig | None
    install: InstallStatus


class NotEnoughSpaceError(Exception):
    """The data folder's disk cannot hold what this size still has to download."""


class AIManager:
    def __init__(
        self,
        settings: Settings,
        on_change: Callable[[AIConfig | None], None],
        *,
        catalog: Catalog | None = None,
        runtime: OllamaRuntime | None = None,
        probe: Callable[[], hw.Hardware] | None = None,
        find_system: Callable[[], str | None] = system_ollama,
        installer: Installer | None = None,
    ) -> None:
        self.settings = settings
        self.on_change = on_change
        self.catalog = catalog or load_catalog()
        self.dir = ai_dir(settings)
        self.runtime = runtime or OllamaRuntime(self.dir, self.catalog)
        self.probe = probe or (lambda: hw.probe(self.dir))
        self.find_system = find_system
        self.installer = installer or Installer(
            self.catalog, self.runtime, self._installed, find_system=find_system
        )

    def _installed(self, config: AIConfig) -> None:
        save_config(self.settings, config)
        self.on_change(config)

    def config(self) -> AIConfig | None:
        return load_config(self.settings)

    def plan(self) -> AIPlan:
        machine = self.probe()
        system = self.find_system()
        program_bytes = 0 if system else self.runtime.download_remaining()
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
        tier = self.catalog.tier(tier_id)
        status = self.installer.status
        if not (self.installer.running and status.tier == tier_id):
            self._check_space(tier, status)
        return self.installer.start(tier)

    def _check_space(self, tier: Tier, status: InstallStatus) -> None:
        # What a paused run of the same size already wrote is on disk, so
        # only the rest needs room. A system Ollama keeps models in its own
        # folder, which is usually on the same disk; this is a best guess.
        program = 0 if self.find_system() else self.runtime.download_remaining()
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
        return self.installer.pause()

    def remove(self) -> None:
        """Forget the setup; delete the private program and models if Axcess owns them.

        Models pulled into an Ollama the person already ran stay there: they
        may use them outside Axcess.
        """
        self.installer.reset()
        self.runtime.remove()
        clear_config(self.settings)
        self.on_change(None)

    def startup(self) -> None:
        """Start the private Ollama if the saved setup uses it."""
        config = self.config()
        if config is None or config.source != "private":
            return
        try:
            url = self.runtime.start(preferred_url=config.base_url)
        except RuntimeSetupError:
            return
        if url != config.base_url:
            config = config.model_copy(update={"base_url": url})
            save_config(self.settings, config)
        self.on_change(config)

    def shutdown(self) -> None:
        self.installer.pause()
        self.runtime.stop()
