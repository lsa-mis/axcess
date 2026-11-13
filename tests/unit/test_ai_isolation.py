"""Offline AI runtime guards and pinned model downloads; all network clients are fake."""

from __future__ import annotations

import hashlib
import subprocess
import sys
import threading
from pathlib import Path
from unittest.mock import Mock

import httpx
import pytest
from pydantic import ValidationError

from audit.ai import downloader
from audit.ai.catalog import GgufFile, ModelEntry, load_catalog, platform_key
from audit.ai.downloader import download_model, file_path, model_present, model_remaining
from audit.ai.manager import AIManager
from audit.ai.runtime import LlamaRuntime, PausedError, RuntimeSetupError
from audit.ai.sandbox import (
    NETWORK_PROBE_FLAG,
    IsolationError,
    Sandbox,
    build_sandbox,
    macos_profile,
)
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
    # IP networking: loopback only (the router reaches its per-model children).
    ip_rules = [line for line in network if " ip " in line]
    assert len(ip_rules) == 3
    assert all('ip "localhost:*"' in line for line in ip_rules)
    # The one other network rule is the service's own UNIX socket, and only
    # inside the scratch folder.
    other = [line for line in network if line not in ip_rules]
    scratch = str((tmp_path / "scratch").resolve())
    assert other == [
        f'(allow network-bind network-inbound (local unix-socket (subpath "{scratch}")))'
    ]
    assert "network-outbound" not in other[0]
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
    # No graphics devices unless a GPU build asks for them.
    assert "/dev/dri" not in sandbox.prefix
    assert sandbox.command(["llama-server", "--offline"])[-2:] == ["llama-server", "--offline"]


def test_linux_gpu_builder_adds_devices_but_keeps_the_private_network(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr("audit.ai.sandbox.shutil.which", lambda tool: "/usr/bin/bwrap")
    sandbox = build_sandbox(
        tmp_path, tmp_path / "models", tmp_path / "scratch", platform="linux", gpu=True
    )
    assert "--unshare-net" in sandbox.prefix
    assert "--share-net" not in sandbox.prefix
    devices = [sandbox.prefix[i + 1] for i, a in enumerate(sandbox.prefix) if a == "--dev-bind-try"]
    assert "/dev/dri" in devices
    assert all(d.startswith("/dev/") for d in devices)
    # GPU discovery reads are read-only.
    reads = [sandbox.prefix[i + 1] for i, a in enumerate(sandbox.prefix) if a == "--ro-bind-try"]
    assert reads and all(r.startswith("/sys/") for r in reads)
    writable = [sandbox.prefix[i + 1] for i, a in enumerate(sandbox.prefix) if a == "--bind"]
    assert writable == [
        str((tmp_path / "models").resolve()),
        str((tmp_path / "scratch").resolve()),
    ]


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


def _probe_command(monkeypatch) -> list[str]:
    seen: list[list[str]] = []

    def run(argv, **_kwargs):
        seen.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout="AXCESS_NETWORK_BLOCKED\n")

    monkeypatch.setattr("audit.ai.sandbox.subprocess.run", run)
    check_network(Sandbox(["sandbox"]))
    return seen[0]


def test_probe_uses_python_flags_when_not_packaged(monkeypatch) -> None:
    monkeypatch.delattr("sys.frozen", raising=False)
    command = _probe_command(monkeypatch)
    assert command[0] == "sandbox"
    assert command[2:5] == ["-I", "-S", "-c"]


def test_packaged_backend_gets_its_probe_flag_not_python_flags(monkeypatch) -> None:
    """A PyInstaller backend ignores -I -S -c and exits with a usage error."""
    monkeypatch.setattr("sys.frozen", True, raising=False)
    command = _probe_command(monkeypatch)
    assert command[2:] == [NETWORK_PROBE_FLAG]


def test_backend_entry_answers_the_same_probe_flag() -> None:
    entry = (Path(__file__).parents[2] / "desktop" / "backend_entry.py").read_text()
    assert f'sys.argv[1:] == ["{NETWORK_PROBE_FLAG}"]' in entry
    assert entry.index("run_network_probe()") < entry.index("from audit.desktop_server")


def test_linux_builder_binds_the_executables_folder(tmp_path, monkeypatch) -> None:
    """The packaged backend runs the probe, so its folder must exist inside."""
    app = tmp_path / "app"
    (app / "_internal").mkdir(parents=True)
    (app / "axcess-server").write_text("")
    monkeypatch.setattr("audit.ai.sandbox.shutil.which", lambda tool: "/usr/bin/bwrap")
    monkeypatch.setattr("sys.executable", str(app / "axcess-server"))
    monkeypatch.setattr("sys.base_prefix", str(app / "_internal"))
    sandbox = build_sandbox(tmp_path, tmp_path / "models", tmp_path / "scratch", platform="linux")
    binds = [sandbox.prefix[i + 1] for i, a in enumerate(sandbox.prefix) if a == "--ro-bind"]
    assert str(app.resolve()) in binds


# -- pinned Hugging Face GGUF downloads ---------------------------------------

REVISION = "0123456789abcdef0123456789abcdef01234567"


def gguf(payload: bytes, name: str = "model-Q4_K_M.gguf", **extra) -> GgufFile:
    fields = {
        "repo": "example-org/Example-GGUF",
        "revision": REVISION,
        "file": name,
        "size": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
    }
    fields.update(extra)
    return GgufFile(**fields)


def model_entry(*files: GgufFile, tag: str = "text:test") -> ModelEntry:
    return ModelEntry(
        tag=tag,
        size=sum(f.size for f in files),
        licence="Apache-2.0",
        gguf=files[0],
        mmproj=files[1] if len(files) > 1 else None,
    )


def hf_client(files: dict[str, bytes], *, status: int | None = None, extra: bytes = b""):
    """A fake Hugging Face host serving ``files`` by URL path; honours Range."""
    seen: list[tuple[str, str, str | None]] = []

    def respond(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, str(request.url), request.headers.get("range")))
        assert request.url.scheme == "https" and request.url.host == "huggingface.co"
        if status is not None:
            return httpx.Response(status)
        body = files[request.url.path] + extra
        ranged = request.headers.get("range")
        if ranged:
            start = int(ranged.removeprefix("bytes=").removesuffix("-"))
            return httpx.Response(206, content=body[start:])
        return httpx.Response(200, content=body)

    return httpx.Client(transport=httpx.MockTransport(respond)), seen


def _path(entry: GgufFile) -> str:
    return f"/{entry.repo}/resolve/{entry.revision}/{entry.file}"


def test_downloader_fetches_pinned_files_and_verifies_them(tmp_path) -> None:
    weights, projector = b"model weights!", b"image add-on"
    text, mmproj = gguf(weights), gguf(projector, name="mmproj-F16.gguf")
    model = model_entry(text, mmproj, tag="vision:test")
    client, seen = hf_client({_path(text): weights, _path(mmproj): projector})
    progress: list[tuple[int, int]] = []
    assert model_remaining(tmp_path, model) == model.size
    download_model(tmp_path, model, lambda d, t: progress.append((d, t)), threading.Event(), client)
    assert model_present(tmp_path, model)
    assert model_remaining(tmp_path, model) == 0
    assert progress[-1] == (model.size, model.size)
    # Only GETs of the exact pinned commit; no branch names, no other host.
    assert [(m, url) for m, url, _ in seen] == [
        ("GET", f"https://huggingface.co/example-org/Example-GGUF/resolve/{REVISION}/{f.file}")
        for f in (text, mmproj)
    ]
    for entry, data in ((text, weights), (mmproj, projector)):
        target = file_path(tmp_path, entry)
        assert target.is_relative_to(tmp_path)
        assert target.read_bytes() == data
    assert not list(tmp_path.rglob("*.part"))
    # Verified files are reused without asking the server again.
    seen.clear()
    download_model(tmp_path, model, lambda d, t: None, threading.Event(), client)
    assert seen == []


def test_downloader_resumes_a_partial_file_with_a_range_request(tmp_path) -> None:
    payload = b"0123456789abcdefghij"
    entry = gguf(payload)
    model = model_entry(entry)
    partial = file_path(tmp_path, entry).with_name(entry.file + ".part")
    partial.parent.mkdir(parents=True)
    partial.write_bytes(payload[:8])
    assert model_remaining(tmp_path, model) == len(payload) - 8
    client, seen = hf_client({_path(entry): payload})
    download_model(tmp_path, model, lambda d, t: None, threading.Event(), client)
    assert [r for _, _, r in seen] == ["bytes=8-"]
    assert model_present(tmp_path, model)
    assert file_path(tmp_path, entry).read_bytes() == payload


def test_downloader_starts_again_when_the_server_ignores_the_range(tmp_path) -> None:
    payload = b"0123456789abcdefghij"
    entry = gguf(payload)
    partial = file_path(tmp_path, entry).with_name(entry.file + ".part")
    partial.parent.mkdir(parents=True)
    partial.write_bytes(b"stale-junk")

    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=payload)  # ignores Range

    client = httpx.Client(transport=httpx.MockTransport(respond))
    download_model(tmp_path, model_entry(entry), lambda d, t: None, threading.Event(), client)
    assert file_path(tmp_path, entry).read_bytes() == payload


def test_downloader_deletes_a_file_with_the_wrong_checksum(tmp_path) -> None:
    payload = b"a model!"
    entry = gguf(payload, sha256="0" * 64)
    model = model_entry(entry)
    client, _ = hf_client({_path(entry): payload})
    with pytest.raises(RuntimeSetupError, match="checksum"):
        download_model(tmp_path, model, lambda d, t: None, threading.Event(), client)
    assert not model_present(tmp_path, model)
    assert not file_path(tmp_path, entry).exists()
    assert not list(tmp_path.rglob("*.part"))


def test_downloader_rejects_a_file_larger_than_pinned(tmp_path) -> None:
    payload = b"a model!"
    entry = gguf(payload)
    model = model_entry(entry)
    client, _ = hf_client({_path(entry): payload}, extra=b"and more")
    with pytest.raises(RuntimeSetupError, match="larger than expected"):
        download_model(tmp_path, model, lambda d, t: None, threading.Event(), client)
    assert not model_present(tmp_path, model)
    assert not list(tmp_path.rglob("*.part"))


def test_downloader_reports_http_errors_in_plain_words(tmp_path) -> None:
    payload = b"a model!"
    entry = gguf(payload)
    client, _ = hf_client({_path(entry): payload}, status=404)
    with pytest.raises(RuntimeSetupError, match=r"HTTP 404"):
        download_model(tmp_path, model_entry(entry), lambda d, t: None, threading.Event(), client)
    assert not model_present(tmp_path, model_entry(entry))


def test_downloader_pause_keeps_the_partial_file(tmp_path) -> None:
    payload = b"a model!"
    entry = gguf(payload)
    client, seen = hf_client({_path(entry): payload})
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(PausedError):
        download_model(tmp_path, model_entry(entry), lambda d, t: None, cancel, client)
    assert seen == []


def test_downloader_refuses_to_follow_a_redirect_off_https(tmp_path, monkeypatch) -> None:
    """The default client checks every request, redirects included."""
    payload = b"a model!"
    entry = gguf(payload)
    requested: list[str] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        if request.url.scheme != "https":
            return httpx.Response(200, content=payload)
        return httpx.Response(302, headers={"Location": "http://cdn.example/model.gguf"})

    real_client = httpx.Client

    def client_with_fake_transport(**kwargs):
        return real_client(transport=httpx.MockTransport(respond), **kwargs)

    monkeypatch.setattr(downloader.httpx, "Client", client_with_fake_transport)
    with pytest.raises(RuntimeSetupError, match="secure connection"):
        download_model(tmp_path, model_entry(entry), lambda d, t: None, threading.Event())
    assert requested == [entry.url]
    assert not model_present(tmp_path, model_entry(entry))


@pytest.mark.parametrize(
    "field,value",
    [
        ("repo", "../escape"),
        ("repo", "https://outside/model"),
        ("repo", "owner/../../escape"),
        ("file", "../escape.gguf"),
        ("file", "sub/dir.gguf"),
        ("file", ".hidden.gguf"),
        ("file", "model.bin"),
        ("revision", "main"),
        ("sha256", "not-a-checksum"),
    ],
)
def test_catalog_file_entries_reject_paths_branches_and_other_hosts(field, value) -> None:
    with pytest.raises(ValidationError):
        gguf(b"x", **{field: value})


@pytest.mark.parametrize(
    "model",
    [model for tier in load_catalog().tiers for model in (tier.text, tier.vision)],
    ids=lambda m: m.tag,
)
def test_every_catalog_model_is_pinned_to_a_commit_over_https(tmp_path, model) -> None:
    for entry in model.files:
        assert entry.url == (
            f"https://huggingface.co/{entry.repo}/resolve/{entry.revision}/{entry.file}"
        )
        assert file_path(tmp_path, entry).resolve().is_relative_to(tmp_path.resolve())
    assert not model_present(tmp_path, model)


# -- the manager and the service ---------------------------------------------

SMALL = load_catalog().tier("small")


def manager_for(tmp_path, *, enabled=True, desktop=True, source="private", backend="llama_cpp"):
    settings = Settings(data_dir=tmp_path, desktop=desktop)
    socket = str(tmp_path / "ai" / "scratch" / "llama.sock")
    save_config(
        settings,
        AIConfig(
            source=source,
            base_url="http://localhost" if source == "private" else "http://127.0.0.1:12345",
            backend=backend,
            socket_path=socket if backend == "llama_cpp" else None,
            tier="small",
            text_model=SMALL.text.served_name,
            vision_model=SMALL.vision.served_name,
        ),
    )
    save_preferences(settings, AIPreferences(enabled=enabled, choice_recorded=True))
    runtime = Mock(spec=LlamaRuntime(tmp_path / "ai", load_catalog()))
    runtime.running.return_value = False
    runtime.installed.return_value = True
    runtime.has_model.return_value = True
    runtime.download_remaining.return_value = 0
    runtime.isolation_reason = None
    runtime.start.return_value = socket
    runtime.service_fields.return_value = {"socket_path": socket, "routes": None}
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
    runtime.start.assert_called_with((SMALL.text, SMALL.vision))
    runtime.running.return_value = True
    assert manager.start_runtime().state == "already_running"
    assert manager.runtime_status().isolated
    manager.busy_reason = lambda: "scan running"
    assert manager.start_runtime().state == "busy"


def test_private_ollama_setup_from_before_llama_cpp_needs_a_new_download(tmp_path) -> None:
    """Its models are Ollama files nothing runs now; never start or trust it."""
    manager, runtime = manager_for(tmp_path, backend="ollama")
    result = manager.start_runtime()
    assert result.state == "model_missing"
    runtime.start.assert_not_called()
    manager.startup()
    runtime.start.assert_not_called()
    assert effective_settings(manager.settings).ollama_base_url == "http://127.0.0.1:0"


def test_setup_whose_models_left_the_catalog_needs_a_new_download(tmp_path) -> None:
    manager, runtime = manager_for(tmp_path)
    config = manager.config()
    assert config is not None
    save_config(manager.settings, config.model_copy(update={"text_model": "retired:model"}))
    assert manager.start_runtime().state == "model_missing"
    runtime.start.assert_not_called()


def test_runtime_refuses_unisolated_start_before_spawning(tmp_path, monkeypatch) -> None:
    runtime = LlamaRuntime(tmp_path, load_catalog())
    monkeypatch.setattr("audit.ai.sandbox.shutil.which", lambda tool: None)
    popen = Mock()
    monkeypatch.setattr("audit.ai.runtime.subprocess.Popen", popen)
    with pytest.raises(IsolationError):
        runtime.start((SMALL.text, SMALL.vision))
    popen.assert_not_called()
    assert not runtime.running()


def _installed_runtime(tmp_path, monkeypatch) -> tuple[LlamaRuntime, list[tuple[str, Path]]]:
    """A runtime with a fake program for every build and models marked present."""
    bundled = tmp_path / "llama-runtime"
    servers = []
    for asset in load_catalog().llama_cpp.assets[platform_key()]:
        server = bundled / asset.accelerator / "llama-b1" / "llama-server"
        server.parent.mkdir(parents=True)
        server.write_text("a checksum-verified test program")
        servers.append((asset.accelerator, server))
    runtime = LlamaRuntime(tmp_path / "ai", load_catalog(), bundled_dir=bundled)
    monkeypatch.setattr(runtime, "has_model", lambda model: True)
    return runtime, servers


@pytest.mark.skipif(sys.platform.startswith("win"), reason="no UNIX socket service on Windows")
def test_runtime_uses_same_sandbox_for_probe_and_serve_with_clean_environment(
    tmp_path, monkeypatch
) -> None:
    runtime, servers = _installed_runtime(tmp_path, monkeypatch)
    sandbox = Sandbox(["sandbox", "--deny-outside"])
    built: list[dict] = []

    def fake_build(*args, **kwargs):
        built.append(kwargs)
        return sandbox

    monkeypatch.setattr("audit.ai.runtime.build_sandbox", fake_build)
    probe = Mock()
    monkeypatch.setattr("audit.ai.runtime.test_network_boundary", probe)
    process = Mock()
    process.poll.return_value = None
    sock = (tmp_path / "ai" / "scratch" / "llama.sock").resolve()

    def spawn(*_args, **_kwargs):
        sock.touch()  # the service creates its socket
        return process

    popen = Mock(side_effect=spawn)
    monkeypatch.setattr("audit.ai.runtime.subprocess.Popen", popen)
    monkeypatch.setattr(
        "audit.ai.runtime._model_states",
        lambda http: {SMALL.text.served_name: "loaded", SMALL.vision.served_name: "loaded"},
    )
    monkeypatch.setenv("UNTRUSTED_MODEL_KEY", "not-inherited")

    path = runtime.start((SMALL.text, SMALL.vision), wait_s=5)

    assert path == str(sock)
    probe.assert_called_once_with(sandbox)
    accelerator, server = servers[0]
    # The GPU build (first in the catalog) gets the GPU devices; CPU does not.
    assert built[-1].get("gpu") is (accelerator != "cpu")
    argv = popen.call_args.args[0]
    preset = (tmp_path / "ai" / "scratch" / "models.ini").resolve()
    assert argv == sandbox.command(
        [
            str(server.resolve()),
            "--models-preset",
            str(preset),
            "--models-max",
            "2",
            "--host",
            str(sock),
            "--no-webui",
            "--offline",
        ]
    )
    # A socket in the sandbox's scratch folder, never a TCP port.
    assert "--port" not in argv
    text = preset.read_text()
    assert f"[{SMALL.text.served_name}]" in text and f"[{SMALL.vision.served_name}]" in text
    env = popen.call_args.kwargs["env"]
    assert "UNTRUSTED_MODEL_KEY" not in env
    assert set(env) == {"PATH", "HOME", "TMPDIR", "LLAMA_CACHE", "LD_LIBRARY_PATH"}
    assert env["HOME"] == str((tmp_path / "ai" / "scratch").resolve())
    assert runtime.isolated and runtime.running()
    runtime.stop()
    process.terminate.assert_called_once()
    assert not runtime.isolated and not runtime.running()
    assert runtime.socket_path is None
    assert not sock.exists()


@pytest.mark.skipif(sys.platform.startswith("win"), reason="no UNIX socket service on Windows")
def test_runtime_falls_back_to_the_cpu_build_when_the_gpu_build_cannot_load(
    tmp_path, monkeypatch
) -> None:
    runtime, servers = _installed_runtime(tmp_path, monkeypatch)
    if len(servers) < 2:
        pytest.skip("this platform has one build")
    built: list[bool] = []

    def fake_build(*_args, gpu=False, **_kwargs):
        built.append(gpu)
        return Sandbox(["sandbox"])

    monkeypatch.setattr("audit.ai.runtime.build_sandbox", fake_build)
    monkeypatch.setattr("audit.ai.runtime.test_network_boundary", Mock())
    sock = (tmp_path / "ai" / "scratch" / "llama.sock").resolve()
    spawned: list[str] = []
    processes: list[Mock] = []

    def spawn(argv, **_kwargs):
        spawned.append(argv[1])
        sock.touch()
        process = Mock()
        process.poll.return_value = None
        processes.append(process)
        return process

    monkeypatch.setattr("audit.ai.runtime.subprocess.Popen", Mock(side_effect=spawn))
    tags = (SMALL.text.served_name, SMALL.vision.served_name)
    monkeypatch.setattr(
        "audit.ai.runtime._model_states",
        lambda http: {t: ("failed" if len(spawned) == 1 else "loaded") for t in tags},
    )
    path = runtime.start((SMALL.text, SMALL.vision), wait_s=5)
    assert path == str(sock)
    assert spawned == [str(s.resolve()) for _, s in servers]
    # Only the GPU build is given the graphics devices.
    assert built[-2:] == [True, False]
    processes[0].terminate.assert_called_once()
    assert runtime.accelerator == "cpu" and runtime.isolated


def _fake_service(tmp_path, monkeypatch, states):
    """Patch the sandbox and process so ``start`` runs without a real server."""
    monkeypatch.setattr("audit.ai.runtime.build_sandbox", lambda *a, **k: Sandbox(["sandbox"]))
    monkeypatch.setattr("audit.ai.runtime.test_network_boundary", Mock())
    sock = (tmp_path / "ai" / "scratch" / "llama.sock").resolve()
    process = Mock()
    process.poll.return_value = None

    def spawn(*_args, **_kwargs):
        sock.touch()
        return process

    monkeypatch.setattr("audit.ai.runtime.subprocess.Popen", Mock(side_effect=spawn))
    monkeypatch.setattr("audit.ai.runtime._model_states", states)
    return sock, process


@pytest.mark.skipif(sys.platform.startswith("win"), reason="no UNIX socket service on Windows")
def test_stop_makes_a_start_still_loading_models_give_up(tmp_path, monkeypatch) -> None:
    runtime, _ = _installed_runtime(tmp_path, monkeypatch)
    loading = threading.Event()

    def states(_http):
        loading.set()
        return {SMALL.text.served_name: "loading", SMALL.vision.served_name: "loading"}

    sock, process = _fake_service(tmp_path, monkeypatch, states)
    errors: list[BaseException] = []

    def start() -> None:
        try:
            runtime.start((SMALL.text, SMALL.vision), wait_s=10)
        except BaseException as exc:
            errors.append(exc)

    thread = threading.Thread(target=start)
    thread.start()
    assert loading.wait(5)
    runtime.stop()
    thread.join(5)
    assert not thread.is_alive()
    assert len(errors) == 1 and isinstance(errors[0], RuntimeSetupError)
    assert "stopped while it was starting" in str(errors[0])
    process.terminate.assert_called()
    assert not runtime.running() and runtime.socket_path is None
    assert not sock.exists()
    # The stop request does not linger: the next start works.
    monkeypatch.setattr(
        "audit.ai.runtime._model_states",
        lambda http: {SMALL.text.served_name: "loaded", SMALL.vision.served_name: "loaded"},
    )
    assert runtime.start((SMALL.text, SMALL.vision), wait_s=5) == str(sock)


@pytest.mark.skipif(sys.platform.startswith("win"), reason="no UNIX socket service on Windows")
def test_start_without_models_waits_for_router_health(tmp_path, monkeypatch) -> None:
    runtime, _ = _installed_runtime(tmp_path, monkeypatch)
    sock, _process = _fake_service(tmp_path, monkeypatch, lambda http: {})
    checks: list[int] = []

    def healthy(_http) -> bool:
        checks.append(1)
        return len(checks) > 1  # not ready on the first look

    monkeypatch.setattr("audit.ai.runtime._healthy", healthy)
    monkeypatch.setattr("audit.ai.runtime.time.sleep", lambda _s: None)
    assert runtime.start((), wait_s=5) == str(sock)
    assert len(checks) == 2 and runtime.isolated


def test_saved_private_socket_is_never_trusted_without_live_isolation(tmp_path):
    manager, runtime = manager_for(tmp_path)
    socket = str(tmp_path / "ai" / "scratch" / "llama.sock")
    not_started = tmp_path / "ai" / "scratch" / "not-started.sock"
    assert effective_settings(manager.settings).model_backend == "llama_cpp"
    assert effective_settings(manager.settings).llama_cpp_socket == not_started
    trust_private_runtime(manager.settings, socket, runtime.running)
    assert effective_settings(manager.settings).llama_cpp_socket == not_started
    runtime.running.return_value = True
    assert str(effective_settings(manager.settings).llama_cpp_socket) == socket
    runtime.running.return_value = False
    assert effective_settings(manager.settings).llama_cpp_socket == not_started
    # A running service at another path does not vouch for the saved one.
    trust_private_runtime(manager.settings, socket + ".other", lambda: True)
    assert effective_settings(manager.settings).llama_cpp_socket == not_started


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
    settings = Settings(data_dir=tmp_path, desktop=True)
    manager = AIManager(settings, Mock())
    with pytest.raises(RuntimeSetupError, match="not set up"):
        manager.set_enabled(True)
    assert not manager.preferences().enabled
    assert manager.config() is None
    assert effective_settings(settings).ollama_base_url == settings.ollama_base_url
    assert effective_settings(settings).model_backend == settings.model_backend
