"""The Windows sandbox launcher, run for real (Windows only, opt-in).

Set ``AXCESS_LLAMA_SERVER_DIR`` to a folder laid out by
``desktop/scripts/bundle-llama-server.py`` with ``axcess-ai-launcher.exe``
built into it (``desktop/ai-launcher/build.ps1``). No model is needed:
llama-server runs in router mode with an empty preset, which loads nothing.
Checks what the app relies on: the launcher's boundary check passes, and
this Python process (httpx, through ``ModelRoutingTransport``) reaches the
sandboxed server through the launcher's port, which refuses other
processes. ``.github/workflows/ai-sandbox.yml`` runs it on windows-2022.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import sys
import tempfile
import threading
from pathlib import Path

import pytest

from audit.ai.model_client import ModelEndpoint, open_model_http_client
from audit.ai.windows_launcher import (
    LAUNCHER_NAME,
    LauncherService,
    ModelProcess,
    run_check,
)

SERVER_DIR = os.environ.get("AXCESS_LLAMA_SERVER_DIR")

pytestmark = [
    pytest.mark.skipif(not sys.platform.startswith("win"), reason="Windows only"),
    pytest.mark.skipif(not SERVER_DIR, reason="set AXCESS_LLAMA_SERVER_DIR"),
]


def test_python_reaches_the_sandboxed_server_through_the_launcher() -> None:
    assert SERVER_DIR
    runtime = Path(SERVER_DIR).resolve()
    launcher = runtime / LAUNCHER_NAME
    server = next((runtime / "cpu").rglob("llama-server.exe"))
    work = Path(tempfile.mkdtemp(prefix="axw-"))
    scratch, models = work / "scratch", work / "models"
    scratch.mkdir()
    models.mkdir()
    log = work / "launcher.log"
    try:
        run_check(launcher, runtime, models, scratch, log, gpu=False)
        preset = scratch / "models.ini"
        preset.write_text("version = 1\n", encoding="utf-8")
        argv = [str(server), "--models-preset", str(preset), "--no-webui", "--offline"]
        sock = scratch / "router.sock"
        service = LauncherService(launcher)
        routes = service.start(
            [ModelProcess("router", sock, [*argv, "--host", str(sock)])],
            runtime,
            models,
            scratch,
            log,
            gpu=False,
        )
        try:
            service.wait_ready(threading.Event(), wait_s=60)

            async def ask() -> tuple[int, int]:
                endpoint = ModelEndpoint(
                    "llama_cpp", "http://localhost", None, tuple(routes.items())
                )
                async with open_model_http_client(endpoint, timeout=10) as http:
                    health = await http.get("/health")
                    named = await http.get("/models", params={"model": "router"})
                    return health.status_code, named.status_code

            assert asyncio.run(ask()) == (200, 200)
        finally:
            service.stop()
        assert not service.running()
    finally:
        if log.exists():
            print(log.read_text(encoding="utf-8", errors="replace")[-4000:])
        shutil.rmtree(work, ignore_errors=True)
