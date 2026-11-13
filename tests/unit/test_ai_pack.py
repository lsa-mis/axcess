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
from audit.ai.runtime import LlamaRuntime, RuntimeSetupError, preset_text
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
        catalog.llama_cpp.assets
    )
    for key, builds in catalog.llama_cpp.assets.items():
        # A CPU build is always the last resort, after any GPU build.
        assert builds[-1].accelerator == ("metal" if key == "darwin-arm64" else "cpu")
        for asset in builds:
            assert len(asset.sha256) == 64
            assert catalog.llama_cpp.version in asset.name
    assert [t.id for t in catalog.tiers] == ["small", "standard", "large"]
    for tier in catalog.tiers:
        assert tier.text.licence == tier.vision.licence == "Apache-2.0"
        # Text models have no image add-on; image models need theirs.
        assert tier.text.mmproj is None and tier.vision.mmproj is not None
        for model in (tier.text, tier.vision):
            assert model.size == sum(f.size for f in model.files)
            for f in model.files:
                assert f.url.startswith(f"https://huggingface.co/{f.repo}/resolve/{f.revision}/")
    assert platform_key().split("-")[1] in {"arm64", "x64"}


def test_preset_names_each_model_by_its_served_name_and_turns_reasoning_off(tmp_path: Path) -> None:
    tier = load_catalog().tier("small")
    text = preset_text(
        [
            (tier.text, tmp_path / "t.gguf", None),
            (tier.vision, tmp_path / "v.gguf", tmp_path / "p.gguf"),
        ],
        gpu=True,
    )
    assert "c = 8192" in text and "reasoning = off" in text and "n-gpu-layers = 99" in text
    assert f"[{tier.text.served_name}]\nmodel = {tmp_path / 't.gguf'}" in text
    vision_section = (
        f"[{tier.vision.served_name}]\n"
        f"model = {tmp_path / 'v.gguf'}\n"
        f"mmproj = {tmp_path / 'p.gguf'}"
    )
    assert vision_section in text
    # llama-server's router renames a model whose name has a colon, so the
    # Ollama-style tag never names a section.
    assert ":" in tier.text.tag and f"[{tier.text.tag}]" not in text
    assert tier.text.served_name == tier.text.tag.replace(":", "-")
    assert "n-gpu-layers = 0" in preset_text([], gpu=False)


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
        base_url="http://localhost",
        backend="llama_cpp",
        socket_path=str(tmp_path / "ai" / "scratch" / "llama.sock"),
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

    # Not started by this process: a socket path that never exists.
    unstarted = effective_settings(desktop)
    assert unstarted.model_backend == "llama_cpp"
    assert unstarted.llama_cpp_socket == tmp_path / "ai" / "scratch" / "not-started.sock"
    socket = str(tmp_path / "ai" / "scratch" / "llama.sock")
    trust_private_runtime(desktop, socket, lambda: True)
    applied = effective_settings(desktop)
    assert applied.model_backend == "llama_cpp"
    assert str(applied.llama_cpp_socket) == socket
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


def test_private_ollama_setup_from_before_llama_cpp_fails_closed(tmp_path: Path) -> None:
    desktop = Settings(data_dir=tmp_path, desktop=True)
    save_config(
        desktop,
        AIConfig(
            source="private",
            base_url="http://127.0.0.1:50123",
            tier="small",
            text_model="text:1",
            vision_model="vision:1",
            ollama_version="0.33.0",
        ),
    )
    applied = effective_settings(desktop)
    assert applied.model_backend == "ollama"
    assert applied.ollama_base_url == "http://127.0.0.1:0"


def _fake_release(server_dir: str = "llama-b1") -> tuple[bytes, str]:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tf:
        data = b"#!/bin/sh\necho llama\n"
        info = tarfile.TarInfo(f"{server_dir}/llama-server")
        info.size = len(data)
        info.mode = 0o755
        tf.addfile(info, io.BytesIO(data))
    payload = buffer.getvalue()
    return payload, hashlib.sha256(payload).hexdigest()


def _runtime_with(tmp_path: Path, payload: bytes, sha: str) -> LlamaRuntime:
    catalog = load_catalog()
    asset = {
        "name": "llama-b1-bin.tar.gz",
        "size": len(payload),
        "sha256": sha,
        "accelerator": "cpu",
    }
    data = catalog.model_dump()
    data["llama_cpp"]["assets"] = {platform_key(): [asset]}
    return LlamaRuntime(tmp_path / "ai", type(catalog).model_validate(data))


def test_download_resumes_checks_sha_and_unpacks(tmp_path: Path) -> None:
    payload, sha = _fake_release()
    runtime = _runtime_with(tmp_path, payload, sha)
    part = tmp_path / "ai" / "downloads" / "llama-b1-bin.tar.gz.part"
    part.parent.mkdir(parents=True)
    part.write_bytes(payload[:10])
    seen: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers.get("range"))
        assert request.url.path.endswith("/llama-b1-bin.tar.gz")
        return httpx.Response(206, content=payload[10:])

    client = httpx.Client(transport=httpx.MockTransport(handler))
    assert runtime.download_remaining() == len(payload) - 10
    runtime.download(lambda d, t: None, threading.Event(), client=client)
    assert seen == ["bytes=10-"]
    assert runtime.installed()
    assert runtime.builds()[0][0] == "cpu"
    assert runtime.builds()[0][1].name == "llama-server"
    assert not part.exists()


def test_download_with_wrong_checksum_is_deleted(tmp_path: Path) -> None:
    payload, _ = _fake_release()
    runtime = _runtime_with(tmp_path, payload, "0" * 64)
    client = httpx.Client(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, content=payload))
    )
    with pytest.raises(RuntimeSetupError, match="checksum"):
        runtime.download(lambda d, t: None, threading.Event(), client=client)
    assert not runtime.installed()
    assert not (tmp_path / "ai" / "downloads" / "llama-b1-bin.tar.gz.part").exists()


def test_bundled_program_needs_no_download(tmp_path: Path) -> None:
    catalog = load_catalog()
    bundled = tmp_path / "llama-runtime"
    builds = catalog.llama_cpp.assets[platform_key()]
    server = bundled / builds[-1].accelerator / "llama-b1" / "llama-server"
    server.parent.mkdir(parents=True)
    server.write_text("#!/bin/sh\n")
    runtime = LlamaRuntime(tmp_path / "ai", catalog, bundled_dir=bundled)
    assert runtime.bundled() and runtime.installed()
    assert runtime.download_remaining() == 0
    assert runtime.builds() == [(builds[-1].accelerator, server)]
    # Without the bundle, the same pinned builds are downloaded.
    plain = LlamaRuntime(tmp_path / "ai", catalog)
    assert not plain.bundled() and not plain.installed()
    assert plain.download_remaining() == sum(a.size for a in builds)


def test_remove_legacy_ollama_keeps_llama_files(tmp_path: Path) -> None:
    runtime = LlamaRuntime(tmp_path / "ai", load_catalog())
    for folder in ("models/blobs", "runtime/0.33.0", "runtime/llama-b1/cpu", "gguf/x"):
        (tmp_path / "ai" / folder).mkdir(parents=True)
    runtime.remove_legacy_ollama()
    assert not (tmp_path / "ai" / "models").exists()
    assert not (tmp_path / "ai" / "runtime" / "0.33.0").exists()
    assert (tmp_path / "ai" / "runtime" / "llama-b1" / "cpu").is_dir()
    assert (tmp_path / "ai" / "gguf" / "x").is_dir()


def test_install_saves_private_llama_cpp_setup(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path, desktop=True)
    changes: list[AIConfig | None] = []
    pulled: list[str] = []
    started: list[list[str]] = []
    socket = str(tmp_path / "ai" / "scratch" / "llama.sock")

    def fake_pull(models_dir, model, progress, cancel):  # type: ignore[no-untyped-def]
        assert models_dir == tmp_path / "ai" / "gguf"
        pulled.append(model.tag)
        progress(1, 1)

    def fake_start(models, **_kw):  # type: ignore[no-untyped-def]
        started.append([m.tag for m in models])
        manager.runtime.socket_path = socket
        return socket

    manager = AIManager(settings, changes.append, probe=lambda: machine(24))
    manager.runtime.require_isolation = lambda: None  # type: ignore[method-assign]
    manager.runtime.download = lambda *a: None  # type: ignore[method-assign]
    manager.runtime.start = fake_start  # type: ignore[method-assign]
    manager.installer.pull = fake_pull
    plan = manager.plan()
    assert plan.recommended == "standard"
    assert plan.program.download_bytes == manager.runtime.download_remaining()
    assert plan.program.version == load_catalog().llama_cpp.version

    manager.install("small")
    manager.installer._thread.join(5)  # type: ignore[union-attr]
    assert manager.installer.status.state == "done", manager.installer.status.error
    tier = load_catalog().tier("small")
    assert pulled == [tier.text.tag, tier.vision.tag]
    assert started == [[tier.text.tag, tier.vision.tag]]
    saved = load_config(settings)
    assert saved is not None and saved.source == "private" and saved.tier == "small"
    assert saved.backend == "llama_cpp" and saved.socket_path == socket
    # The saved setup names the models as the private service serves them.
    assert (saved.text_model, saved.vision_model) == (
        tier.text.served_name,
        tier.vision.served_name,
    )
    assert changes[-1] == saved

    manager.remove()
    assert load_config(settings) is None
    assert changes[-1] is None
    assert manager.installer.status.state == "idle"


def test_install_failure_is_reported_in_plain_words(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path, desktop=True)

    def failing_pull(*_args):  # type: ignore[no-untyped-def]
        raise RuntimeSetupError("The AI model download stopped. Try again.")

    runtime = LlamaRuntime(tmp_path / "ai", load_catalog())
    runtime.require_isolation = lambda: None  # type: ignore[method-assign]
    runtime.download = lambda *a: None  # type: ignore[method-assign]
    installer = Installer(
        load_catalog(), runtime, lambda c: save_config(settings, c), pull=failing_pull
    )
    installer.start(load_catalog().tier("small"))
    installer._thread.join(5)  # type: ignore[union-attr]
    assert installer.status.state == "failed"
    assert installer.status.error == "The AI model download stopped. Try again."
    assert load_config(settings) is None


def test_install_refuses_to_start_without_disk_space(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path, desktop=True)
    manager = AIManager(settings, lambda _c: None, probe=lambda: machine(64, disk_gb=5))
    with pytest.raises(NotEnoughSpaceError, match="Not enough free disk space for the Large size"):
        manager.install("large")
    assert manager.installer.status.state == "idle"
    assert not manager.installer.running
