"""Unit tests never depend on this machine's free memory."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _free_memory_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    """The service's free-memory check reads the real machine; unknown skips it.

    Tests of the check itself set their own value.
    """
    from audit.ai import hardware

    monkeypatch.setattr(hardware, "available_memory_bytes", lambda: None)
