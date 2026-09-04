"""Search and dynamically revealed routes in an actual Vue/Vue Router app."""

from __future__ import annotations

import asyncio
import http.server
import sqlite3
from pathlib import Path

import pytest
from playwright.async_api import async_playwright

from audit.analyzer.axe import AxeAnalyzer
from audit.analyzer.interaction import InteractionProbe
from audit.crawler.js_fetcher import JsFetcher
from audit.crawler.orchestrator import CrawlConfig, build_search_explorer, run_crawl
from audit.crawler.search import SearchConfig, SearchField, SearchTarget

pytestmark = pytest.mark.integration
FIXTURE = Path(__file__).parents[1] / "fixtures" / "vue-search"


class VueHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        super().__init__(*args, directory=str(FIXTURE), **kwargs)

    def do_GET(self) -> None:
        if not self.path.startswith("/vendor/"):
            self.path = "/index.html"
        super().do_GET()

    def log_message(self, format: str, *args: object) -> None:
        pass


@pytest.mark.parametrize("mode", ["public", "login", "login-hash"])
def test_real_vue_search_reaches_all_51_routes(tmp_db: sqlite3.Connection, mode: str) -> None:
    import socketserver
    import threading

    with socketserver.TCPServer(("127.0.0.1", 0), VueHandler) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_address[1]}"
        suffix = "?router=hash#/" if mode == "login-hash" else ""
        seed = base + "/" + suffix
        config = CrawlConfig(
            seed_url=seed,
            browser_only=mode != "public",
            whole_host=True,
            max_pages=100,
            max_depth=5,
            workers=2,
            rps=100,
            ignore_robots=True,
            image_extraction_enabled=False,
            ocr_enabled=False,
            vlm_enabled=False,
            semantic_enabled=False,
            synthesize_enabled=False,
            keyboard_probe_enabled=False,
            focus_checks_enabled=False,
            responsive_checks_enabled=False,
            visual_checks_enabled=False,
            capture_screenshots=False,
            search=SearchConfig(
                confirmed=True,
                fields=(SearchField(target="Search reports", value="sample"),),
                results_selector="[role=option]",
                next_button=SearchTarget(target="Next results"),
                max_results=50,
                max_result_pages=3,
            ),
        )

        async def crawl():  # type: ignore[no-untyped-def]
            axe = AxeAnalyzer.from_bundled()
            explorer = build_search_explorer(config, axe)
            async with async_playwright() as pw:
                browser = await pw.chromium.launch()
                context = await browser.new_context()
                page = await context.new_page()
                try:
                    if mode != "public":
                        await page.goto(
                            base + ("/?router=hash&auth=session#/" if suffix else "/?auth=session")
                        )
                        await page.get_by_role("button", name="Complete test sign-in").click()
                        await page.goto(seed)
                    fetcher = JsFetcher(
                        user_agent="test",
                        idle_timeout_ms=100,
                        axe_analyzer=axe,
                        interaction_probe=InteractionProbe(axe=axe),
                        search_explorer=explorer,
                        shared_context=context if mode != "public" else None,
                        shared_pages=(page,) if mode != "public" else (),
                    )
                    async with fetcher:
                        return await run_crawl(tmp_db, config, js_fetcher=fetcher)
                finally:
                    await browser.close()

        try:
            summary = asyncio.run(crawl())
        finally:
            server.shutdown()
            thread.join(timeout=5)
    rows = tmp_db.execute(
        "SELECT url_normalized, status_code FROM pages WHERE scan_id=?", (summary.scan_id,)
    ).fetchall()
    root = seed[:-1] if mode == "login-hash" else base
    expected = {seed, root + "/about", root + "/help"}
    expected.update(root + f"/reports/{i}{tail}" for i in range(1, 25) for tail in ("", "/details"))
    assert {row["url_normalized"] for row in rows} == expected
    assert all(row["status_code"] == 200 for row in rows)
    outcome = tmp_db.execute(
        "SELECT * FROM scan_search_runs WHERE scan_id=?", (summary.scan_id,)
    ).fetchone()
    assert outcome["status"] == "completed", dict(outcome)
    assert outcome["states"] == 3
    assert summary.axe_pages_scanned == len(expected)
