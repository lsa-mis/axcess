"""Offline AI runtime guards and registry imports; all network clients are fake."""

from __future__ import annotations

import hashlib
import json
import subprocess
import threading
from pathlib import Path
from unittest.mock import Mock

import httpx
import pytest

from audit.ai.catalog import load_catalog
from audit.ai.downloader import download_model, model_present
from audit.ai.manager import AIManager
from audit.ai.runtime import OllamaRuntime
from audit.ai.sandbox import IsolationError, Sandbox, build_sandbox, macos_profile
from audit.ai.sandbox import test_network_boundary as check_network
from audit.ai.state import (
    AIConfig,
    AIPreferences,
    effective_settings,
    save_config,
    save_preferences,
    trust_private_runtime,
)
from audit.config import Settings


def test_macos_profile_denies_default_and_allows_only_loopback_network(tmp_path: Path) -> None:
    profile = macos_profile(tmp_path / "runtime", tmp_path / "models", tmp_path / "scratch")
    assert "(deny default)" in profile
    network = [line for line in profile.splitlines() if "allow network" in line]
    assert len(network) == 3
    assert all('ip "localhost:*"' in line for line in network)
    assert "(allow network*)" not in profile
    assert str((tmp_path / "models").resolve()) in profile
    assert "(allow file-read*)" not in profile


def test_macos_profile_allows_only_named_gpu_services(tmp_path: Path) -> None:
    """Metal needs the GPU driver and shader compiler; nothing broader."""
    profile = macos_profile(tmp_path / "runtime", tmp_path / "models", tmp_path / "scratch")
    assert '(global-name "com.apple.MTLCompilerService")' in profile
    assert "AGXDeviceUserClient" in profile
    assert "(allow mach-lookup)" not in profile
    assert "(allow iokit-open)" not in profile
    mach = [line for line in profile.splitlines() if "allow mach-lookup" in line]
    assert mach == ['(allow mach-lookup (global-name "com.apple.MTLCompilerService"))']


def test_linux_builder_uses_private_network_and_readonly_program(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("audit.ai.sandbox.shutil.which", lambda tool: "/usr/bin/bwrap")
    sandbox = build_sandbox(tmp_path, tmp_path / "models", tmp_path / "scratch", platform="linux")
    assert "--unshare-net" in sandbox.prefix
    assert "--ro-bind" in sandbox.prefix
    assert "--share-net" not in sandbox.prefix
    assert sandbox.command(["ollama", "serve"])[-2:] == ["ollama", "serve"]


@pytest.mark.parametrize("platform", ["win32", "linux", "darwin"])
def test_missing_sandbox_fails_closed(tmp_path, monkeypatch, platform) -> None:
    monkeypatch.setattr("audit.ai.sandbox.shutil.which", lambda tool: None)
    with pytest.raises(IsolationError) as error:
        build_sandbox(tmp_path, tmp_path, tmp_path, platform=platform)
    assert error.value.reason == "sandbox_unavailable"


@pytest.mark.parametrize("code,output", [(1, ""), (0, ""), (0, "CONNECTED"), (-6, "")])
def test_broken_or_successful_outbound_probe_fails_closed(monkeypatch, code, output) -> None:
    monkeypatch.setattr(
        "audit.ai.sandbox.subprocess.run",
        lambda *a, **k: subprocess.CompletedProcess(a[0], code, stdout=output, stderr=""),
    )
    with pytest.raises(IsolationError, match="did not prove"):
        check_network(Sandbox(["sandbox"]))


def test_os_denial_passes_network_preflight(monkeypatch) -> None:
    monkeypatch.setattr(
        "audit.ai.sandbox.subprocess.run",
        lambda *a, **k: subprocess.CompletedProcess(a[0], 0, stdout="AXCESS_NETWORK_BLOCKED\n"),
    )
    check_network(Sandbox(["sandbox"]))


def registry_client(payload: bytes, *, wrong_blob: bool = False, wrong_manifest: bool = False):
    digest = "sha256:" + hashlib.sha256(payload).hexdigest()
    body = json.dumps(
        {
            "schemaVersion": 2,
            "config": {"digest": digest, "size": len(payload)},
            "layers": [{"digest": digest, "size": len(payload)}],
        }
    ).encode()
    seen = []

    def respond(request):
        seen.append((request.method, str(request.url)))
        assert request.url.scheme == "https" and request.url.host == "registry.ollama.ai"
        if "/manifests/" in request.url.path:
            checksum = "0" * 64 if wrong_manifest else hashlib.sha256(body).hexdigest()
            return httpx.Response(
                200, content=body, headers={"Docker-Content-Digest": "sha256:" + checksum}
            )
        return httpx.Response(200, content=b"bad-data" if wrong_blob else payload)

    return httpx.Client(transport=httpx.MockTransport(respond)), seen


def test_downloader_imports_checksum_verified_offline_model_without_pull(tmp_path) -> None:
    client, seen = registry_client(b"a model!")
    progress = []
    download_model(
        tmp_path, "text:test", lambda d, t: progress.append((d, t)), threading.Event(), client
    )
    assert model_present(tmp_path, "text:test")
    assert progress[-1] == (8, 8)
    assert all(method == "GET" and "/api/pull" not in url for method, url in seen)
    assert (tmp_path / "manifests/registry.ollama.ai/library/text/test").exists()
    # The verified local manifest and blob are reused without asking the registry again.
    seen.clear()
    download_model(tmp_path, "text:test", lambda d, t: None, threading.Event(), client)
    assert seen == []


@pytest.mark.parametrize("wrong_manifest,wrong_blob", [(True, False), (False, True)])
def test_downloader_rejects_wrong_checksums(tmp_path, wrong_manifest, wrong_blob) -> None:
    client, _ = registry_client(b"a model!", wrong_blob=wrong_blob, wrong_manifest=wrong_manifest)
    with pytest.raises(Exception, match="checksum"):
        download_model(tmp_path, "text:test", lambda d, t: None, threading.Event(), client)
    assert not model_present(tmp_path, "text:test")
    assert not list(tmp_path.rglob("*.part"))


@pytest.mark.parametrize(
    "tag", ["../escape:test", "https://outside/model:test", "text:../../escape"]
)
def test_downloader_rejects_paths_and_external_registry_names(tmp_path, tag) -> None:
    with pytest.raises(Exception, match="model name"):
        download_model(tmp_path, tag, lambda d, t: None, threading.Event())


def manager_for(tmp_path, *, enabled=True, desktop=True, source="private"):
    settings = Settings(data_dir=tmp_path, desktop=desktop)
    save_config(
        settings,
        AIConfig(
            source=source,
            base_url="http://127.0.0.1:12345",
            tier="small",
            text_model="text:test",
            vision_model="vision:test",
        ),
    )
    save_preferences(settings, AIPreferences(enabled=enabled, choice_recorded=True))
    runtime = Mock(spec=OllamaRuntime(tmp_path / "ai", load_catalog()))
    runtime.running.return_value = False
    runtime.installed.return_value = True
    runtime.has_model.return_value = True
    runtime.download_remaining.return_value = 0
    runtime.isolation_reason = None
    runtime.start.return_value = "http://127.0.0.1:12345"
    return AIManager(settings, Mock(), runtime=runtime), runtime


@pytest.mark.parametrize(
    "enabled,desktop,source,state",
    [
        (False, True, "private", "ai_off"),
        (True, False, "private", "not_desktop"),
        (True, True, "system", "system_ollama_not_managed"),
    ],
)
def test_start_never_manages_system_ollama_or_disabled_ai(
    tmp_path, enabled, desktop, source, state
):
    manager, runtime = manager_for(tmp_path, enabled=enabled, desktop=desktop, source=source)
    assert manager.start_runtime().state == state
    runtime.start.assert_not_called()
    runtime.stop.assert_not_called()
    runtime.download.assert_not_called()


def test_start_states_and_download_size(tmp_path) -> None:
    manager, runtime = manager_for(tmp_path)
    runtime.has_model.return_value = False
    missing = manager.start_runtime()
    assert (
        missing.state == "model_missing"
        and missing.download_bytes == load_catalog().tier("small").size
    )
    runtime.start.assert_not_called()
    runtime.has_model.return_value = True
    runtime.start.side_effect = IsolationError("network_test_failed", "blocked")
    assert manager.start_runtime().reason == "network_test_failed"
    runtime.start.side_effect = None
    assert manager.start_runtime().model_dump() == {
        "state": "started",
        "isolated": True,
        "reason": None,
        "download_bytes": None,
        "tier": None,
    }
    runtime.running.return_value = True
    assert manager.start_runtime().state == "already_running"
    assert manager.runtime_status().isolated
    manager.busy_reason = lambda: "scan running"
    assert manager.start_runtime().state == "busy"


def test_runtime_refuses_unisolated_start_before_spawning(tmp_path, monkeypatch) -> None:
    runtime = OllamaRuntime(tmp_path, load_catalog())
    monkeypatch.setattr("audit.ai.sandbox.shutil.which", lambda tool: None)
    popen = Mock()
    monkeypatch.setattr("audit.ai.runtime.subprocess.Popen", popen)
    with pytest.raises(IsolationError):
        runtime.start()
    popen.assert_not_called()


def test_runtime_uses_same_sandbox_for_probe_and_serve_with_clean_environment(
    tmp_path, monkeypatch
) -> None:
    runtime = OllamaRuntime(tmp_path, load_catalog())
    monkeypatch.setattr("audit.ai.runtime.sys.platform", "darwin")
    binary = runtime.binary
    assert binary is not None
    binary.parent.mkdir(parents=True)
    binary.write_text("a checksum-verified test program")
    sandbox = Sandbox(["sandbox-exec", "-p", "deny-outside"])
    monkeypatch.setattr("audit.ai.runtime.build_sandbox", lambda *args: sandbox)
    probe = Mock()
    monkeypatch.setattr("audit.ai.runtime.test_network_boundary", probe)
    process = Mock()
    process.poll.return_value = None
    spawn = Mock(return_value=process)
    monkeypatch.setattr("audit.ai.runtime.subprocess.Popen", spawn)
    monkeypatch.setattr("audit.ai.runtime.ollama_version", lambda *args, **kwargs: "test")
    monkeypatch.setenv("UNTRUSTED_MODEL_KEY", "not-inherited")
    url = runtime.start()
    assert url.startswith("http://127.0.0.1:")
    probe.assert_called_once_with(sandbox)
    argv = spawn.call_args.args[0]
    assert argv == sandbox.command([str(binary.resolve()), "serve"])
    assert "pull" not in argv
    env = spawn.call_args.kwargs["env"]
    assert env["OLLAMA_HOST"] == url.removeprefix("http://")
    assert env["OLLAMA_NO_CLOUD"] == "1"
    assert "UNTRUSTED_MODEL_KEY" not in env
    assert runtime.isolated
    runtime.stop()
    process.terminate.assert_called_once()
    assert not runtime.isolated


def test_saved_private_port_is_never_trusted_without_live_isolation(tmp_path):
    manager, runtime = manager_for(tmp_path)
    assert effective_settings(manager.settings).ollama_base_url == "http://127.0.0.1:0"
    trust_private_runtime(manager.settings, "http://127.0.0.1:12345", runtime.running)
    assert effective_settings(manager.settings).ollama_base_url == "http://127.0.0.1:0"
    runtime.running.return_value = True
    assert effective_settings(manager.settings).ollama_base_url == "http://127.0.0.1:12345"
    runtime.running.return_value = False
    assert effective_settings(manager.settings).ollama_base_url == "http://127.0.0.1:0"


@pytest.mark.parametrize(
    "url",
    [
        "https://model.example",
        "http://192.168.1.2:11434",
        "http://127.0.0.1/model",
        "http://localhost/?token=secret",
    ],
)
def test_desktop_model_addresses_cannot_send_evidence_off_host(url):
    with pytest.raises(ValueError, match="local address"):
        AIConfig(
            source="private",
            base_url=url,
            tier="small",
            text_model="text:test",
            vision_model="vision:test",
        )


def test_enabling_without_setup_never_silently_selects_system_ollama(tmp_path):
    from audit.ai.runtime import RuntimeSetupError

    settings = Settings(data_dir=tmp_path, desktop=True)
    manager = AIManager(settings, Mock(), find_system=lambda: "installed-system-version")
    with pytest.raises(RuntimeSetupError, match="not set up"):
        manager.set_enabled(True)
    assert not manager.preferences().enabled
