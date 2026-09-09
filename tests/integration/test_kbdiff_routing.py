"""Real browser checks for the local fixture transport; no listening server."""

# The optional experiment is outside the installed audit package.
import sys
from pathlib import Path

import pytest
from playwright.async_api import async_playwright

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from experiments.tabbing.runner.serve import ContextFactory, page_url

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_fixture_http_and_websocket_requests_stay_local(tmp_path):
    (tmp_path / "index.html").write_text("<!doctype html><title>Local routing test</title>")
    (tmp_path / "worker.js").write_text("self.addEventListener('fetch', () => {});")
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        factory = ContextFactory(browser, {"width": 1280, "height": 900}, tmp_path)
        try:
            context = await factory()
            page = await context.new_page()
            await page.goto(page_url("index.html"))
            result = await page.evaluate("""async () => {
                const ping = await (await fetch('/api/ping')).json();
                const blocked = await fetch('https://tabbing.axcess.test.evil.invalid/nope')
                    .then(() => false, () => true);
                const missing = await fetch('/missing-file').then(() => false, () => true);
                const socketClosed = await new Promise((resolve) => {
                    const timer=setTimeout(() => resolve(false), 3000);
                    const ws=new WebSocket('wss://example.invalid/socket');
                    ws.onclose=() => { clearTimeout(timer); resolve(true); };
                });
                return {ping, blocked, missing, socketClosed};
            }""")
            assert result == {
                "ping": {"ok": True},
                "blocked": True,
                "missing": True,
                "socketClosed": True,
            }
            assert factory.totals["ping"] == 1
            assert factory.totals["blocked"] == 2
            assert factory.totals["missing"] == 1
            assert factory.totals["websocket"] == 1
            registration = await page.evaluate("""async () => Promise.race([
                navigator.serviceWorker.register('/worker.js')
                    .then(registration => Boolean(registration), () => false),
                new Promise(resolve => setTimeout(() => resolve('pending'), 500))
            ])""")
            assert registration is False
            assert await page.evaluate("navigator.serviceWorker.getRegistrations()") == []
            assert not context.service_workers
            assert factory.totals["served"] == 1  # worker script was never requested
            await page.evaluate("localStorage.setItem('trial', 'changed')")
            second = await factory()
            fresh = await second.new_page()
            await fresh.goto(page_url("index.html"))
            assert await fresh.evaluate("localStorage.getItem('trial')") is None
        finally:
            await factory.close_open_contexts()
            await browser.close()
        assert not factory._contexts
