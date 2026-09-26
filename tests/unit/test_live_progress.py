"""The progress page's per-page, per-check states, kept in memory by the crawl."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from typing import Any

import pytest

from audit.crawler import live_progress
from audit.web.server import _page_checks

SCAN = 9001


@pytest.fixture(autouse=True)
def _clean() -> Iterator[None]:
    live_progress.forget(SCAN)
    yield
    live_progress.forget(SCAN)


def _entry(url: str) -> dict[str, Any]:
    return next(entry for entry in live_progress.snapshot(SCAN) if entry["url"] == url)


def test_a_check_is_running_inside_its_block_and_done_after() -> None:
    with live_progress.page(SCAN, "https://a.test/", ["axe", "keyboard"]):
        assert _entry("https://a.test/")["checks"] == {"axe": "waiting", "keyboard": "waiting"}
        with live_progress.check("axe"):
            assert _entry("https://a.test/")["checks"]["axe"] == "running"
        assert _entry("https://a.test/")["checks"]["axe"] == "done"
        assert _entry("https://a.test/")["finished"] is False
    # Keyboard never ran on this page, so it ends as not run, not as done.
    assert _entry("https://a.test/") == {
        "url": "https://a.test/",
        "finished": True,
        "checks": {"axe": "done", "keyboard": "not_run"},
    }


def test_a_check_that_raises_is_not_run() -> None:
    with (
        pytest.raises(RuntimeError),
        live_progress.page(SCAN, "https://a.test/", ["alfa"]),
        live_progress.check("alfa"),
    ):
        raise RuntimeError("engine crashed")
    assert _entry("https://a.test/")["checks"] == {"alfa": "not_run"}


def test_outside_a_page_and_for_an_untracked_check_nothing_is_recorded() -> None:
    with live_progress.check("axe"):
        pass
    assert live_progress.snapshot(SCAN) == []
    with live_progress.page(SCAN, "https://a.test/", ["axe"]), live_progress.check("semantic"):
        pass
    assert _entry("https://a.test/")["checks"] == {"axe": "not_run"}


def test_concurrent_pages_each_mark_their_own_row() -> None:
    async def visit(url: str, delay: float) -> None:
        with live_progress.page(SCAN, url, ["axe"]):
            await asyncio.sleep(delay)
            with live_progress.check("axe"):
                await asyncio.sleep(0)

    async def main() -> None:
        slow = asyncio.create_task(visit("https://a.test/slow", 0.05))
        await visit("https://a.test/fast", 0)
        assert _entry("https://a.test/fast")["checks"] == {"axe": "done"}
        assert _entry("https://a.test/slow")["checks"] == {"axe": "waiting"}
        await slow

    asyncio.run(main())
    assert _entry("https://a.test/slow")["checks"] == {"axe": "done"}


def test_only_the_latest_finished_pages_are_kept() -> None:
    for index in range(30):
        with live_progress.page(SCAN, f"https://a.test/{index}", ["axe"]):
            pass
    urls = [entry["url"] for entry in live_progress.snapshot(SCAN)]
    assert len(urls) == 25
    assert urls[0] == "https://a.test/5"
    assert urls[-1] == "https://a.test/29"


def test_rows_put_pages_being_checked_first_then_latest_checked_then_waiting() -> None:
    with live_progress.page(SCAN, "https://a.test/one", ["axe"]), live_progress.check("axe"):
        pass
    with live_progress.page(SCAN, "https://a.test/two", ["axe"]):
        pass
    with live_progress.page(SCAN, "https://a.test/now", ["axe", "alfa"]):
        with live_progress.check("axe"):
            pass
        rows = _page_checks(
            SCAN,
            checking=["https://a.test/now", "https://a.test/other-process"],
            waiting=["https://a.test/next"],
            recent=["https://a.test/ignored-when-tracked"],
        )
    assert rows == [
        {
            "url": "https://a.test/now",
            "state": "checking",
            "checks": {"axe": "done", "alfa": "waiting"},
        },
        # Leased, but this process has no record of it: no check claimed.
        {"url": "https://a.test/other-process", "state": "checking", "checks": {}},
        {"url": "https://a.test/two", "state": "checked", "checks": {"axe": "not_run"}},
        {"url": "https://a.test/one", "state": "checked", "checks": {"axe": "done"}},
        {"url": "https://a.test/next", "state": "waiting", "checks": {}},
    ]


def test_without_a_record_the_rows_fall_back_to_the_queue() -> None:
    rows = _page_checks(
        SCAN,
        checking=["https://a.test/now"],
        waiting=[],
        recent=["https://a.test/now", "https://a.test/done"],
    )
    assert rows == [
        {"url": "https://a.test/now", "state": "checking", "checks": {}},
        {"url": "https://a.test/done", "state": "checked", "checks": {}},
    ]
