"""The pinned Ollama release and the model tiers, read from ``catalog.json``.

The JSON is the single source: release tooling refreshes its checksums, and
the setup page shows its sizes and licences as they are.
"""

from __future__ import annotations

import json
import platform
import sys
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

CATALOG_PATH = Path(__file__).with_name("catalog.json")
TierId = Literal["small", "standard", "large"]


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class RuntimeAsset(_Frozen):
    name: str
    size: int
    sha256: str
    binary: str


class OllamaRelease(_Frozen):
    version: str
    release_url: str
    licence: str
    assets: dict[str, RuntimeAsset]

    def download_url(self, asset: RuntimeAsset) -> str:
        return f"https://github.com/ollama/ollama/releases/download/v{self.version}/{asset.name}"


class ModelEntry(_Frozen):
    tag: str
    size: int
    licence: str


class Tier(_Frozen):
    id: TierId
    label: str
    min_memory_gb: int
    text: ModelEntry
    vision: ModelEntry

    @property
    def size(self) -> int:
        return self.text.size + self.vision.size


class Catalog(_Frozen):
    ollama: OllamaRelease
    tiers: tuple[Tier, ...]

    def tier(self, tier_id: str) -> Tier:
        for tier in self.tiers:
            if tier.id == tier_id:
                return tier
        raise KeyError(tier_id)


@lru_cache(maxsize=1)
def load_catalog(path: Path = CATALOG_PATH) -> Catalog:
    return Catalog.model_validate(json.loads(path.read_text(encoding="utf-8")))


def platform_key() -> str:
    """``darwin-arm64``, ``win32-x64``, ``linux-x64`` and so on."""
    machine = platform.machine().lower()
    arch = "arm64" if machine in {"arm64", "aarch64"} else "x64"
    os_name = "win32" if sys.platform.startswith("win") else sys.platform
    if os_name.startswith("linux"):
        os_name = "linux"
    return f"{os_name}-{arch}"
