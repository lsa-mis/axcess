"""Unit tests never depend on this machine's memory."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _free_memory_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    """The service's free-memory check reads the real machine; unknown skips it.

    Tests of the check itself set their own value.
    """
    from audit.ai import hardware

    monkeypatch.setattr(hardware, "available_memory_bytes", lambda: None)


@pytest.fixture(autouse=True)
def _a_large_computer(monkeypatch: pytest.MonkeyPatch) -> None:
    """A 64 GB computer, so no size is refused or warned about for this
    machine's memory (hardware.size_refused). Tests of that rule pass their
    own probe.
    """
    from audit.ai import hardware

    monkeypatch.setattr(hardware, "_memory_bytes", lambda: 64 * 1024**3)


@pytest.fixture(autouse=True)
def _no_graphics_card_memory(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reading the graphics cards runs llama-server; tests never do. Tests of
    the card's memory set their own value."""
    from audit.ai.runtime import LlamaRuntime

    monkeypatch.setattr(LlamaRuntime, "devices", lambda self: [])
