"""The private llama.cpp service, started for real inside the OS sandbox.

Opt-in: set ``AXCESS_LLAMA_SERVER_DIR`` to a folder laid out by
``desktop/scripts/bundle-llama-server.py`` (one folder per accelerator).
No model is needed: the router starts with an empty model list and must
answer ``/health`` through its UNIX socket from inside the sandbox
(Bubblewrap on Linux, ``sandbox-exec`` on macOS). This checks the sandbox
rules for the socket and the program's own files, which unit tests with
fakes cannot. ``.github/workflows/ai-sandbox.yml`` runs it on Linux and
macOS.

With ``AXCESS_LLAMA_AI_DIR`` also set to a data folder's ``ai`` directory
whose Small models are downloaded, a second test loads both models and asks
each one question.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import sys
import tempfile
import threading
import time
from pathlib import Path

import httpx
import pytest

from audit.ai.catalog import load_catalog
from audit.ai.model_client import (
    GenerateRequest,
    ModelEndpoint,
    make_model_client,
    open_model_http_client,
)
from audit.ai.runtime import SOCKET_BASE_URL, LlamaRuntime

SERVER_DIR = os.environ.get("AXCESS_LLAMA_SERVER_DIR")
AI_DIR = os.environ.get("AXCESS_LLAMA_AI_DIR")

pytestmark = [
    pytest.mark.skipif(not SERVER_DIR, reason="set AXCESS_LLAMA_SERVER_DIR"),
    pytest.mark.skipif(sys.platform.startswith("win"), reason="no Windows sandbox yet"),
]


def _short_tmp() -> Path:
    # A UNIX socket path must stay under about 100 bytes; pytest's tmp_path
    # on macOS is long, so use a short private folder of our own.
    return Path(tempfile.mkdtemp(prefix="axl-", dir="/tmp" if Path("/tmp").is_dir() else None))  # noqa: S108 - mkdtemp makes a private folder


def test_router_answers_through_its_socket_inside_the_sandbox() -> None:
    assert SERVER_DIR
    ai_dir = _short_tmp() / "ai"
    try:
        runtime = LlamaRuntime(ai_dir, load_catalog(), bundled_dir=Path(SERVER_DIR))
        assert runtime.bundled(), f"no llama-server under {SERVER_DIR}"
        socket = runtime.start((), wait_s=60)
        try:
            assert runtime.running() and runtime.isolated
            assert Path(socket).exists()
            transport = httpx.HTTPTransport(uds=socket)
            with httpx.Client(transport=transport, base_url=SOCKET_BASE_URL, timeout=5) as http:
                assert http.get("/health").status_code == 200
                assert http.get("/models").json()["data"] == []
        finally:
            runtime.stop()
        assert not Path(socket).exists()
        assert not runtime.running()
    finally:
        shutil.rmtree(ai_dir.parent, ignore_errors=True)


@pytest.mark.skipif(not AI_DIR, reason="set AXCESS_LLAMA_AI_DIR with Small models downloaded")
def test_small_models_load_and_answer() -> None:
    assert SERVER_DIR and AI_DIR
    tier = load_catalog().tier("small")
    runtime = LlamaRuntime(Path(AI_DIR), load_catalog(), bundled_dir=Path(SERVER_DIR))
    socket = runtime.start((tier.text, tier.vision))
    schema = {
        "type": "object",
        "properties": {"answer": {"type": "string"}},
        "required": ["answer"],
        "additionalProperties": False,
    }

    async def ask() -> list[str]:
        endpoint = ModelEndpoint("llama_cpp", SOCKET_BASE_URL, socket)
        async with open_model_http_client(endpoint, timeout=180) as http:
            client = make_model_client("llama_cpp", http, base_url=endpoint.base_url)
            served = {m.name for m in await client.ready_models()}
            assert {tier.text.served_name, tier.vision.served_name} <= served
            return [
                await client.generate(
                    GenerateRequest(
                        model=model,
                        prompt="Answer in three words: what is alt text for?",
                        json_schema=schema,
                        temperature=0,
                        seed=1,
                        max_tokens=60,
                    )
                )
                for model in (tier.text.served_name, tier.vision.served_name)
            ]

    try:
        for answer in asyncio.run(ask()):
            assert '"answer"' in answer
    finally:
        runtime.stop()


def test_service_outlives_the_thread_that_started_it() -> None:
    """Setup starts the service from its download thread, which then ends.

    Bubblewrap's ``--die-with-parent`` follows the starting *thread*; before
    the runtime started every process from one long-lived thread, the
    service died as soon as setup finished.
    """
    assert SERVER_DIR
    ai_dir = _short_tmp() / "ai"
    runtime = LlamaRuntime(ai_dir, load_catalog(), bundled_dir=Path(SERVER_DIR))
    started: list[str] = []
    try:
        worker = threading.Thread(target=lambda: started.append(runtime.start((), wait_s=60)))
        worker.start()
        worker.join(90)
        assert started, "the service did not start"
        time.sleep(2)
        assert runtime.running(), "the service died with the thread that started it"
    finally:
        runtime.stop()
        shutil.rmtree(ai_dir.parent, ignore_errors=True)
