"""Which check each page of a running scan is on, for the progress page.

The progress page shows one row per page and one column per check. The
durable record cannot fill that table: the queue knows that a page is being
worked on, and the scan row counts finished checks, but nothing stores which
check a page has reached. This module keeps that in memory, in the process
running the crawl, while the scan runs.

It is a display aid, not evidence. Nothing here is saved or exported, and a
scan run in another process (the command line) or read after a restart has
no entries: the progress page then falls back to the queue's own states,
waiting, being checked, and checked.

The page being worked on is carried in a context variable, so the browser
fetcher and the analyzers mark their check without being told the scan or
the URL. Outside a crawl the variable is unset and every call is a no-op.
"""

from __future__ import annotations

import threading
from collections import OrderedDict
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Literal

CheckState = Literal["waiting", "running", "done", "not_run"]

# Finished pages kept per scan, newest last. The progress page shows a
# handful; this only bounds memory on a long scan.
_KEEP_FINISHED = 25

_current: ContextVar[tuple[int, str] | None] = ContextVar("live_progress_page", default=None)
# Written by the crawl's event loop, read by request threads.
_lock = threading.Lock()
_scans: dict[int, OrderedDict[str, dict[str, Any]]] = {}


@contextmanager
def page(scan_id: int, url: str, checks: Iterable[str]) -> Iterator[None]:
    """Track ``url`` for the length of the block, every check waiting at first.

    A check still waiting when the page ends did not apply to it (a page the
    browser could not open gets no browser checks), and one still running
    ended with an error: both are recorded as not run, not as done.
    """
    entry: dict[str, Any] = {"finished": False, "checks": dict.fromkeys(checks, "waiting")}
    with _lock:
        pages = _scans.setdefault(scan_id, OrderedDict())
        pages.pop(url, None)
        pages[url] = entry
    token = _current.set((scan_id, url))
    try:
        yield
    finally:
        _current.reset(token)
        with _lock:
            states = entry["checks"]
            for key, state in states.items():
                if state != "done":
                    states[key] = "not_run"
            entry["finished"] = True
            _trim(pages)


@contextmanager
def check(key: str) -> Iterator[None]:
    """Mark ``key`` running on the current page for the block, then done.

    An exception leaves it running, which ``page`` then records as not run.
    """
    _set(key, "running")
    yield
    _set(key, "done")


def snapshot(scan_id: int) -> list[dict[str, Any]]:
    """The tracked pages of ``scan_id``, oldest first, as plain copies."""
    with _lock:
        pages = _scans.get(scan_id)
        if not pages:
            return []
        return [
            {"url": url, "finished": entry["finished"], "checks": dict(entry["checks"])}
            for url, entry in pages.items()
        ]


def forget(scan_id: int) -> None:
    """Drop everything tracked for ``scan_id``, once the scan has ended."""
    with _lock:
        _scans.pop(scan_id, None)


def _set(key: str, state: CheckState) -> None:
    current = _current.get()
    if current is None:
        return
    scan_id, url = current
    with _lock:
        pages = _scans.get(scan_id)
        entry = pages.get(url) if pages is not None else None
        if entry is not None and key in entry["checks"]:
            entry["checks"][key] = state


def _trim(pages: OrderedDict[str, dict[str, Any]]) -> None:
    finished = [url for url, entry in pages.items() if entry["finished"]]
    for url in finished[: max(0, len(finished) - _KEEP_FINISHED)]:
        del pages[url]
