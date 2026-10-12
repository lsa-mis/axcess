"""Desktop AI pack: catalogue, hardware tiers, settings overlay, install job."""

from __future__ import annotations

import hashlib
import io
import tarfile
import threading
from pathlib import Path

import httpx
import pytest

from audit.ai import hardware as hw
from audit.ai.catalog import load_catalog, platform_key
from audit.ai.installer import Installer
from audit.ai.manager import AIManager, NotEnoughSpaceError
from audit.ai.runtime import OllamaRuntime, RuntimeSetupError
from audit.ai.state import (
    AIConfig,
    effective_settings,
    load_config,
    save_config,
    semantic_model,
    trust_private_runtime,
)
from audit.analyzer.semantic.registry import build_analyzers, supported_criteria
from audit.config import Settings

GB = hw.GB


def machine(memory_gb: float, disk_gb: float = 500, apple: bool = True, gpu: str | None = None):
    return hw.Hardware(
        memory_bytes=int(memory_gb * 1024**3),
        free_disk_bytes=int(disk_gb * GB),
        apple_silicon=apple,
        gpu=gpu,
        os="darwin",
        arch="arm64",
    )


def test_catalog_pins_every_platform_and_only_open_licences() -> None:
    catalog = load_catalog()
    assert {"darwin-arm64", "darwin-x64", "linux-x64", "linux-arm64", "win32-x64"} <= set(
        catalog.ollama.assets
    )
    for asset in catalog.ollama.assets.values():
        assert len(asset.sha256) == 64
    assert [t.id for t in catalog.tiers] == ["small", "standard", "large"]
    for tier in catalog.tiers:
        assert tier.text.licence == tier.vision.licence == "Apache-2.0"
    assert platform_key().split("-")[1] in {"arm64", "x64"}


@pytest.mark.parametrize(
    ("memory", "apple", "gpu", "expected"),
    [
        (4, True, None, None),
        (8, True, None, "small"),
        (16, True, None, "standard"),
        (24, True, None, "standard"),
        (36, True, None, "large"),
        (64, False, None, "small"),  # no GPU: bigger models are too slow
        (64, False, "NVIDIA", "large"),
    ],
)
def test_recommend_picks_the_largest_tier_that_fits(memory, apple, gpu, expected) -> None:
    tier = hw.recommend(machine(memory, apple=apple, gpu=gpu), load_catalog())
    assert (tier.id if tier else None) == expected


def test_recommend_respects_free_disk_space() -> None:
    catalog = load_catalog()
    assert hw.recommend(machine(64, disk_gb=12), catalog).id == "standard"  # type: ignore[union-attr]
    assert hw.recommend(machine(64, disk_gb=5), catalog) is None


def _config(tmp_path: Path, **extra) -> AIConfig:
    return AIConfig(
        source="private",
        base_url="http://127.0.0.1:50123",
        tier="small",
        text_model="text:1",
        vision_model="vision:1",
        **extra,
    )


def test_effective_settings_only_applies_on_desktop(tmp_path: Path) -> None:
    server = Settings(data_dir=tmp_path)
    desktop = Settings(data_dir=tmp_path, desktop=True)
    assert effective_settings(desktop) is desktop  # nothing set up yet
    save_config(desktop, _config(tmp_path))

    assert effective_settings(server) is server
    assert semantic_model(server) is None

    assert effective_settings(desktop).ollama_base_url == "http://127.0.0.1:0"
    trust_private_runtime(desktop, "http://127.0.0.1:50123", lambda: True)
    applied = effective_settings(desktop)
    assert applied.ollama_base_url == "http://127.0.0.1:50123"
    assert applied.suggestion_text_model == "text:1"
    assert applied.suggestion_vision_model == applied.vlm_model == "vision:1"
    assert applied.suggestions_enabled is True
    assert semantic_model(desktop) == "text:1"


def test_corrupt_config_is_ignored(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path, desktop=True)
    (tmp_path / "ai").mkdir()
    (tmp_path / "ai" / "config.json").write_text("{not json")
    assert load_config(settings) is None
    assert effective_settings(settings) is settings


def test_semantic_model_override_replaces_every_pick() -> None:
    class _Provider:
        model = "default"

    analyzers = build_analyzers(supported_criteria(), _Provider(), model_override="one:model")  # type: ignore[arg-type]
    assert analyzers
    assert {a._model for a in analyzers} == {"one:model"}  # type: ignore[attr-defined]


def _fake_release(tmp_path: Path) -> tuple[bytes, str]:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tf:
        data = b"#!/bin/sh\necho ollama\n"
        info = tarfile.TarInfo("ollama")
        info.size = len(data)
        info.mode = 0o755
        tf.addfile(info, io.BytesIO(data))
    payload = buffer.getvalue()
    return payload, hashlib.sha256(payload).hexdigest()


def _runtime_with(tmp_path: Path, payload: bytes, sha: str) -> OllamaRuntime:
    catalog = load_catalog()
    asset = {"name": "ollama-darwin.tgz", "size": len(payload), "sha256": sha, "binary": "ollama"}
    data = catalog.model_dump()
    data["ollama"]["assets"] = {platform_key(): asset}
    return OllamaRuntime(tmp_path / "ai", type(catalog).model_validate(data))


def test_download_resumes_checks_sha_and_unpacks(tmp_path: Path) -> None:
    payload, sha = _fake_release(tmp_path)
    runtime = _runtime_with(tmp_path, payload, sha)
    part = tmp_path / "ai" / "downloads" / "ollama-darwin.tgz.part"
    part.parent.mkdir(parents=True)
    part.write_bytes(payload[:10])
    seen: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers.get("range"))
        return httpx.Response(206, content=payload[10:])

    client = httpx.Client(transport=httpx.MockTransport(handler))
    assert runtime.download_remaining() == len(payload) - 10
    runtime.download(lambda d, t: None, threading.Event(), client=client)
    assert seen == ["bytes=10-"]
    assert runtime.installed()
    assert not part.exists()


def test_download_with_wrong_checksum_is_deleted(tmp_path: Path) -> None:
    payload, _ = _fake_release(tmp_path)
    runtime = _runtime_with(tmp_path, payload, "0" * 64)
    client = httpx.Client(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, content=payload))
    )
    with pytest.raises(RuntimeSetupError, match="checksum"):
        runtime.download(lambda d, t: None, threading.Event(), client=client)
    assert not runtime.installed()
    assert not (tmp_path / "ai" / "downloads" / "ollama-darwin.tgz.part").exists()


def test_install_keeps_system_ollama_separate_and_saves_private_setup(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path, desktop=True)
    changes: list[AIConfig | None] = []
    pulled: list[str] = []

    def fake_pull(models_dir, tag, progress, cancel):  # type: ignore[no-untyped-def]
        assert models_dir == tmp_path / "ai" / "models"
        pulled.append(tag)
        progress(1, 1)

    manager = AIManager(
        settings,
        changes.append,
        probe=lambda: machine(24),
        find_system=lambda: "0.33.0",
    )
    manager.runtime.download = lambda *a: None
    manager.runtime.start = lambda *a, **kw: "http://127.0.0.1:50123"
    manager.installer.pull = fake_pull
    manager.installer.find_system = lambda: "0.33.0"
    plan = manager.plan()
    assert plan.recommended == "standard"
    assert plan.program.download_bytes == manager.runtime.download_remaining()

    manager.install("small")
    manager.installer._thread.join(5)  # type: ignore[union-attr]
    assert manager.installer.status.state == "done"
    tier = load_catalog().tier("small")
    assert pulled == [tier.text.tag, tier.vision.tag]
    saved = load_config(settings)
    assert saved is not None and saved.source == "private" and saved.tier == "small"
    assert changes[-1] == saved

    manager.remove()
    assert load_config(settings) is None
    assert changes[-1] is None
    assert manager.installer.status.state == "idle"


def test_install_failure_is_reported_in_plain_words(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path, desktop=True)

    def failing_pull(*_args):  # type: ignore[no-untyped-def]
        raise RuntimeSetupError("Ollama could not download m: no space")

    installer = Installer(
        load_catalog(),
        OllamaRuntime(tmp_path / "ai", load_catalog()),
        lambda c: save_config(settings, c),
        find_system=lambda: "0.33.0",
        pull=failing_pull,
    )
    installer.runtime.download = lambda *a: None
    installer.start(load_catalog().tier("small"))
    installer._thread.join(5)  # type: ignore[union-attr]
    assert installer.status.state == "failed"
    assert installer.status.error == "Ollama could not download m: no space"
    assert load_config(settings) is None


def test_install_refuses_to_start_without_disk_space(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path, desktop=True)
    manager = AIManager(
        settings,
        lambda _c: None,
        probe=lambda: machine(64, disk_gb=5),
        find_system=lambda: "0.33.0",
    )
    with pytest.raises(NotEnoughSpaceError, match="Not enough free disk space for the Large size"):
        manager.install("large")
    assert manager.installer.status.state == "idle"
    assert not manager.installer.running
