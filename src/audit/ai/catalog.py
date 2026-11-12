"""The pinned llama.cpp release and the model tiers, read from ``catalog.json``.

The JSON is the single source: release tooling refreshes its checksums, and
the setup page shows its sizes and licences as they are.

Each tier names its models twice. ``tag`` is the Ollama name, used when an
administrator points a web or server install at their own Ollama
(``AUDIT_OLLAMA_BASE_URL``); ``served_name`` is the same name without a
colon, which the private llama.cpp service answers to.
``gguf`` (and ``mmproj`` for a vision model) are the exact files the desktop
app downloads for its private service: a Hugging Face repository pinned to
one commit, with the file's size and SHA-256.
"""

from __future__ import annotations

import json
import platform
import re
import sys
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

CATALOG_PATH = Path(__file__).with_name("catalog.json")
TierId = Literal["small", "standard", "large"]
Accelerator = Literal["metal", "vulkan", "cpu"]


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class RuntimeAsset(_Frozen):
    name: str = Field(pattern=r"^[A-Za-z0-9._-]+$")
    size: int
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    accelerator: Accelerator


class LlamaCppRelease(_Frozen):
    version: str = Field(pattern=r"^b[0-9]+$")
    release_url: str
    licence: str
    # Per platform, the builds to try in order: a GPU build first, then the
    # CPU build that works on any computer of that kind.
    assets: dict[str, tuple[RuntimeAsset, ...]]

    def download_url(self, asset: RuntimeAsset) -> str:
        return (
            f"https://github.com/ggml-org/llama.cpp/releases/download/{self.version}/{asset.name}"
        )


_HF_REPO = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9][A-Za-z0-9_.-]*$")


class GgufFile(_Frozen):
    repo: str = Field(pattern=_HF_REPO.pattern)
    revision: str = Field(pattern=r"^[a-f0-9]{40}$")
    file: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*\.gguf$")
    size: int = Field(gt=0)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")

    @property
    def url(self) -> str:
        # A commit, not a branch: the same URL always returns the same bytes.
        return f"https://huggingface.co/{self.repo}/resolve/{self.revision}/{self.file}"


class ModelEntry(_Frozen):
    tag: str
    size: int
    licence: str
    gguf: GgufFile
    mmproj: GgufFile | None = None

    @property
    def served_name(self) -> str:
        """The name the private llama.cpp service answers to.

        The tag with ":" replaced: llama-server's router reads the part of a
        model name after a colon as a Hugging Face quantization label and
        renames the model (checked on b12284: ``qwen3:4b-instruct-2507-q4_K_M``
        was served as ``qwen3:Q4_K_M``).
        """
        return self.tag.replace(":", "-")

    @property
    def files(self) -> tuple[GgufFile, ...]:
        return (self.gguf,) if self.mmproj is None else (self.gguf, self.mmproj)


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
    llama_cpp: LlamaCppRelease
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
