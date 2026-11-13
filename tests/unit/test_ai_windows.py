"""The Windows private AI path, without Windows: the model router, the saved
routes, and the launcher protocol driven by a stand-in launcher script."""

from __future__ import annotations

import json
import sys
import threading
from pathlib import Path

import httpx
import pytest

from audit.ai.model_client import ModelEndpoint, ModelRoutingTransport, open_model_http_client
from audit.ai.sandbox import IsolationError
from audit.ai.state import AIConfig, effective_settings, save_config, trust_private_runtime
from audit.ai.windows_launcher import LauncherService, ModelProcess, run_check, spec_text
from audit.config import Settings

pytestmark = pytest.mark.skipif(sys.platform.startswith("win"), reason="POSIX stand-in script")


def _servers(seen: list[str], *, loading: str | None = None) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(f"{request.url.port} {request.method} {request.url.path}")
        name = {1001: "text", 1002: "vision"}[request.url.port or 0]
        if request.url.path == "/health":
            if name == loading:
                return httpx.Response(503, json={"error": {"message": "Loading model"}})
            return httpx.Response(200, json={"status": "ok"})
        if request.url.path == "/v1/models":
            return httpx.Response(200, json={"object": "list", "data": [{"id": name}]})
        return httpx.Response(200, json={"choices": [{"message": {"content": name}}]})

    return httpx.MockTransport(handler)


ROUTES = {"text": "http://127.0.0.1:1001", "vision": "http://127.0.0.1:1002"}


async def test_router_sends_each_request_to_its_models_server() -> None:
    seen: list[str] = []
    transport = ModelRoutingTransport(ROUTES, _servers(seen))
    async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as http:
        reply = await http.post("/v1/chat/completions", json={"model": "vision", "messages": []})
        assert reply.json()["choices"][0]["message"]["content"] == "vision"
        reply = await http.get("/props", params={"model": "text"})
        assert reply.status_code == 200
        missing = await http.post("/v1/chat/completions", json={"model": "other"})
        assert missing.status_code == 404
        models = await http.get("/v1/models")
        assert [m["id"] for m in models.json()["data"]] == ["text", "vision"]
        assert (await http.get("/health")).status_code == 200
    assert seen[:2] == ["1002 POST /v1/chat/completions", "1001 GET /props"]


async def test_router_health_waits_for_every_model() -> None:
    transport = ModelRoutingTransport(ROUTES, _servers([], loading="vision"))
    async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as http:
        assert (await http.get("/health")).status_code == 503


def test_routed_endpoint_uses_the_router() -> None:
    endpoint = ModelEndpoint("llama_cpp", "http://localhost", None, tuple(sorted(ROUTES.items())))
    client = open_model_http_client(endpoint)
    assert isinstance(client._transport, ModelRoutingTransport)


def test_saved_windows_routes_fail_closed_until_this_process_started_them(tmp_path: Path) -> None:
    desktop = Settings(data_dir=tmp_path, desktop=True)
    config = AIConfig(
        source="private",
        base_url="http://localhost",
        backend="llama_cpp",
        routes=ROUTES,
        tier="small",
        text_model="text",
        vision_model="vision",
    )
    save_config(desktop, config)
    unstarted = effective_settings(desktop)
    assert unstarted.model_backend == "llama_cpp"
    assert unstarted.llama_cpp_routes == dict.fromkeys(ROUTES, "http://127.0.0.1:0")
    trust_private_runtime(desktop, json.dumps(ROUTES, sort_keys=True), lambda: True)
    assert effective_settings(desktop).llama_cpp_routes == ROUTES
    # A different set of ports is not the service this process started.
    save_config(desktop, config.model_copy(update={"routes": {"text": "http://127.0.0.1:9"}}))
    assert effective_settings(desktop).llama_cpp_routes == {"text": "http://127.0.0.1:0"}


@pytest.fixture(autouse=True)
def _run_stand_ins_with_python(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "audit.ai.windows_launcher._argv0", lambda launcher: [sys.executable, str(launcher)]
    )


def _script(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "launcher.py"
    path.write_text(f"import sys\n{body}\n", encoding="utf-8")
    return path


@pytest.mark.parametrize(
    ("output", "code", "passes"),
    [
        ("AXCESS_NETWORK_BLOCKED WSAEACCES\nAXCESS_FILES_LIMITED\nAXCESS_SOCKET_OK", 0, True),
        ("AXCESS_NETWORK_BLOCKED WSAEACCES\nAXCESS_SOCKET_OK", 0, False),
        ("AXCESS_CHECK_FAILED network_reachable", 4, False),
        ("AXCESS_NETWORK_BLOCKED x\nAXCESS_FILES_LIMITED\nAXCESS_SOCKET_OK", 1, False),
    ],
)
def test_check_passes_only_on_every_line_and_exit_zero(
    tmp_path: Path, output: str, code: int, passes: bool
) -> None:
    launcher = _script(tmp_path, f"print({output!r}); sys.exit({code})")
    log = tmp_path / "log"
    if passes:
        run_check(launcher, tmp_path, tmp_path, tmp_path, log, gpu=True)
    else:
        with pytest.raises(IsolationError) as err:
            run_check(launcher, tmp_path, tmp_path, tmp_path, log, gpu=False)
        assert err.value.reason == "network_test_failed"


def test_spec_lists_each_model_socket_and_argument(tmp_path: Path) -> None:
    text = spec_text([ModelProcess("text", tmp_path / "m0.sock", ["C:/x/llama-server.exe", "-m"])])
    assert text == (
        f"MODEL text\nSOCKET {tmp_path / 'm0.sock'}\nARG C:/x/llama-server.exe\nARG -m\n"
    )
    with pytest.raises(ValueError, match="line break"):
        spec_text([ModelProcess("t", tmp_path / "a.sock", ["a\nb"])])


def test_serve_reads_ports_and_stops_when_its_input_closes(tmp_path: Path) -> None:
    stopped = tmp_path / "stopped"
    launcher = _script(
        tmp_path,
        "print('PORT text 1001', flush=True)\nprint('PORT vision 1002', flush=True)\n"
        "print('READY', flush=True)\nsys.stdin.read()\n"
        f"open({str(stopped)!r}, 'w').write('yes')",
    )
    service = LauncherService(launcher)
    processes = [
        ModelProcess("text", tmp_path / "m0.sock", ["x"]),
        ModelProcess("vision", tmp_path / "m1.sock", ["x"]),
    ]
    routes = service.start(processes, tmp_path, tmp_path, tmp_path, tmp_path / "log", gpu=False)
    assert routes == ROUTES
    assert service.running()
    service.stop()
    assert stopped.read_text() == "yes"
    assert not service.running()


def test_serve_reports_a_model_that_exits_while_loading(tmp_path: Path) -> None:
    launcher = _script(
        tmp_path,
        "print('PORT text 1', flush=True)\nprint('READY', flush=True)\n"
        "print('EXIT text 3221225477', flush=True)\nsys.stdin.read()",
    )
    service = LauncherService(launcher)
    service.start(
        [ModelProcess("text", tmp_path / "m0.sock", ["x"])],
        tmp_path,
        tmp_path,
        tmp_path,
        tmp_path / "log",
        gpu=True,
    )
    from audit.ai.windows_launcher import LauncherModelError

    with pytest.raises(LauncherModelError):
        service.wait_ready(threading.Event(), wait_s=5)
    service.stop()


def test_serve_refuses_when_the_launcher_reports_an_error(tmp_path: Path) -> None:
    launcher = _script(tmp_path, "print('AXCESS_ERROR CreateProcessW 5', flush=True)")
    service = LauncherService(launcher)
    with pytest.raises(IsolationError):
        service.start(
            [ModelProcess("text", tmp_path / "m0.sock", ["x"])],
            tmp_path,
            tmp_path,
            tmp_path,
            tmp_path / "log",
            gpu=False,
        )
    assert not service.running()
