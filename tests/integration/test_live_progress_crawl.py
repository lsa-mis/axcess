"""A real browser crawl fills the running scan's pages-by-checks table.

The unit tests drive ``live_progress`` by hand. This one runs the crawler
over the hash-router fixture site with the browser checks on and reads what
the progress page would have been given: while a page's keyboard check runs,
its rule check (axe) is already done and its zoom and layout check still
waits; once the crawl ends, every page shows every check done.
"""

from __future__ import annotations

import asyncio
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import pytest

from audit.crawler import live_progress
from audit.crawler.orchestrator import CrawlConfig, run_crawl

from .test_crawl_end_to_end import _serve

pytestmark = pytest.mark.integration

CHECKS = ("axe", "keyboard", "responsive", "interaction")


def test_a_browser_crawl_records_each_check_on_each_page(
    tmp_db: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    during_keyboard: list[dict[str, str]] = []
    at_end: list[dict[str, Any]] = []
    scan_ids: list[int] = []

    def _snapshot() -> list[dict[str, Any]]:
        return live_progress.snapshot(scan_ids[0]) if scan_ids else []

    real_check = live_progress.check
    real_forget = live_progress.forget

    @contextmanager
    def watching_check(key: str) -> Iterator[None]:
        with real_check(key):
            if key == "keyboard":
                current = [entry for entry in _snapshot() if not entry["finished"]]
                during_keyboard.extend(entry["checks"] for entry in current)
            yield

    def remembering_forget(scan_id: int) -> None:
        at_end.extend(live_progress.snapshot(scan_id))
        real_forget(scan_id)

    real_page = live_progress.page

    @contextmanager
    def noting_page(scan_id: int, url: str, checks: Any) -> Iterator[None]:
        if not scan_ids:
            scan_ids.append(scan_id)
        with real_page(scan_id, url, checks):
            yield

    monkeypatch.setattr(live_progress, "check", watching_check)
    monkeypatch.setattr(live_progress, "forget", remembering_forget)
    monkeypatch.setattr(live_progress, "page", noting_page)

    with _serve() as base:
        seed = f"{base}/hash-spa/index.html"
        config = CrawlConfig(
            js_eager=True,
            seed_url=seed,
            max_pages=10,
            rps=100.0,
            workers=1,
            image_extraction_enabled=False,
            axe_enabled=True,
            alfa_enabled=False,
            vlm_enabled=False,
            semantic_enabled=False,
            keyboard_probe_enabled=True,
            responsive_checks_enabled=True,
            focus_checks_enabled=False,
            visual_checks_enabled=False,
            interaction_checks_enabled=True,
            capture_screenshots=False,
        )
        summary = asyncio.run(run_crawl(tmp_db, config))

    assert summary.status == "completed"
    # One page at a time (one worker): while its keyboard check ran, the rule
    # check had finished and the checks the browser runs after it
    # (Click-Through, then zoom and layout) had not started.
    assert during_keyboard, "the keyboard check never ran inside a tracked page"
    for checks in during_keyboard:
        assert checks == {
            "axe": "done",
            "keyboard": "running",
            "responsive": "waiting",
            "interaction": "waiting",
        }, checks
    # Every page the crawl saved ends with every check done, and the scan's
    # record is dropped once the scan is finished.
    pages = {
        row["url_normalized"]
        for row in tmp_db.execute(
            "SELECT url_normalized FROM pages WHERE scan_id = ?", (summary.scan_id,)
        )
    }
    assert {entry["url"] for entry in at_end} == pages
    for entry in at_end:
        assert entry["finished"] is True
        assert entry["checks"] == dict.fromkeys(CHECKS, "done"), entry
    assert live_progress.snapshot(summary.scan_id) == []
