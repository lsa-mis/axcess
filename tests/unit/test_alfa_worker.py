"""The scan-long Alfa worker's client: snapshot checks and reply parsing.

The worker process itself needs Node and the pinned Alfa packages, so these
tests stop at the boundary: what Axcess accepts from the page, and what it
accepts back from the worker.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from audit.analyzer import alfa_worker
from audit.analyzer.alfa import AlfaError
from audit.analyzer.alfa_worker import AlfaSnapshot, AlfaWorker, _parse_response


class _Target:
    url = "https://example.test/page"

    def __init__(self, returns: Any) -> None:
        self.returns = returns

    async def evaluate(self, expression: str, arg: Any = None) -> Any:
        return self.returns


def _ready_worker(monkeypatch: pytest.MonkeyPatch) -> AlfaWorker:
    worker = AlfaWorker()

    async def started() -> None:
        worker._snapshot_script = "async () => '{}'"

    monkeypatch.setattr(worker, "start", started)
    return worker


_GOOD = json.dumps({"url": "https://example.test/page", "node": {"type": "document"}, "device": {}})


@pytest.mark.asyncio
async def test_snapshot_keeps_a_valid_snapshot(monkeypatch: pytest.MonkeyPatch) -> None:
    worker = _ready_worker(monkeypatch)

    snap = await worker.snapshot(_Target(_GOOD))

    assert snap == AlfaSnapshot(url="https://example.test/page", payload=_GOOD)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("returned", "reason"),
    [
        (None, "no snapshot"),
        ("not json", "not valid JSON"),
        ('{"node": [], "device": {}}', "unexpected shape"),
        # A page that replaced JSON.stringify to smuggle a second request.
        (_GOOD + '\n{"id": 2}', "not valid JSON"),
    ],
)
async def test_snapshot_refuses_what_the_page_should_not_send(
    monkeypatch: pytest.MonkeyPatch, returned: Any, reason: str
) -> None:
    worker = _ready_worker(monkeypatch)

    with pytest.raises(AlfaError, match=reason):
        await worker.snapshot(_Target(returned))


@pytest.mark.asyncio
async def test_snapshot_puts_a_multiline_snapshot_on_one_line(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    worker = _ready_worker(monkeypatch)
    pretty = json.dumps(json.loads(_GOOD), indent=2)

    snap = await worker.snapshot(_Target(pretty))

    assert "\n" not in snap.payload
    assert json.loads(snap.payload) == json.loads(_GOOD)


@pytest.mark.asyncio
async def test_snapshot_over_the_size_limit_says_how_large(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    worker = _ready_worker(monkeypatch)
    monkeypatch.setattr(alfa_worker, "MAX_SNAPSHOT_BYTES", 10)

    with pytest.raises(AlfaError, match="too large for Alfa"):
        await worker.snapshot(_Target(_GOOD))


def _reply(**extra: Any) -> bytes:
    payload = {
        "id": 7,
        "protocol_version": 1,
        "engine": "alfa",
        "url": "https://example.test/page",
        "status": 200,
        "outcome_counts": {"failed": 0, "cantTell": 0},
        "findings": [],
    }
    payload.update(extra)
    return json.dumps(payload).encode() + b"\n"


def test_parse_response_reads_a_result() -> None:
    result = _parse_response(_reply(), 7)

    assert result.failed_total == 0
    assert result.findings == ()


def test_parse_response_refuses_an_answer_to_another_request() -> None:
    with pytest.raises(AlfaError, match="different request"):
        _parse_response(_reply(id=8), 7)


def test_parse_response_passes_the_worker_error_on() -> None:
    line = json.dumps({"id": 7, "error": "TypeError: x is undefined"}).encode()

    with pytest.raises(AlfaError, match="TypeError: x is undefined"):
        _parse_response(line, 7)
