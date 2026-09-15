"""Replay the three authorized KAFE captures in the installed browser.

Feasibility observations only. There is no scoring here, no truth file is read,
and the frozen detectors are not invoked. The questions are:

1. Does a 2021 mitmproxy capture load offline in Chromium 145 at all?
2. What resources go missing, and are they essential or benign (G4)?
3. Is a neutral, label-independent element census stable across fresh
   contexts, and does tagging perturb the page (G1)?
4. Does a safe, egress-blocked keyboard interaction work?

Every run, including failures, is written to derived/feasibility.json.
"""

from __future__ import annotations

import asyncio
import json
import traceback
from pathlib import Path

from playwright.async_api import async_playwright

from tools import flowfile, replay
from tools.census_flows import APPENDIX

HERE = Path(__file__).resolve().parent.parent
ARTIFACTS = HERE / "artifacts"
DERIVED = HERE / "derived"

VIEWPORT = {"width": 1920, "height": 1080}  # KAFE §5.1
SETTLE_MS = 3000
NAV_TIMEOUT_MS = 60_000
TAB_PRESSES = 15
REPEATS = 2


def _entry_url(index: flowfile.ExchangeIndex, subject: str) -> str | None:
    """The largest 200/text-html response: the page under test."""
    best, best_len = None, -1
    for url, exchanges in index.by_url.items():
        for exchange in exchanges:
            ctype = exchange.headers.get("content-type", "")
            if exchange.status == 200 and ctype.startswith("text/html"):
                if len(exchange.body) > best_len:
                    best, best_len = url, len(exchange.body)
    return best


async def _one_run(browser, capture: bytes, url: str, tagged: bool) -> dict:
    index = flowfile.load_exchanges(capture)
    router = replay.ReplayRouter(index)
    console: list[str] = []
    page_errors: list[str] = []

    context = await browser.new_context(viewport=VIEWPORT, service_workers="block")
    await router.attach(context)
    page = await context.new_page()
    page.on("console", lambda m: console.append(f"{m.type}:{m.text[:160]}"))
    page.on("pageerror", lambda e: page_errors.append(str(e)[:160]))

    record: dict = {"tagged": tagged, "url": url}
    try:
        response = await page.goto(url, timeout=NAV_TIMEOUT_MS, wait_until="load")
        record["http_status"] = response.status if response else None
        await page.wait_for_timeout(SETTLE_MS)

        if tagged:
            record["tagged_elements"] = await page.evaluate(
                replay.NEUTRAL_CENSUS_JS, replay.CENSUS_ATTR
            )
            record["census_ids"] = await page.evaluate(
                "(a) => Array.from(document.querySelectorAll('['+a+']'))"
                ".map(e => e.getAttribute(a))",
                replay.CENSUS_ATTR,
            )

        record["signature"] = await page.evaluate(replay.DOM_SIGNATURE_JS)
        record["title"] = await page.title()

        # Safe interaction with egress blocked: walk the tab order and record
        # where focus lands. No clicks, no form submission, no navigation.
        # The probe identifies elements structurally, so the tagged and
        # untagged arms are measured on identical terms (see FOCUS_PROBE_JS).
        focus_trail: list[str] = []
        for _ in range(TAB_PRESSES):
            await page.keyboard.press("Tab")
            focus_trail.append(await page.evaluate(replay.FOCUS_PROBE_JS))
        record["focus_trail"] = focus_trail
        record["distinct_focus_stops"] = len(set(focus_trail))
        record["ok"] = True
    except Exception as exc:  # noqa: BLE001 - failures are results here
        record["ok"] = False
        record["error"] = f"{type(exc).__name__}: {exc}"[:300]
        record["traceback_tail"] = traceback.format_exc()[-400:]
    finally:
        record["served"] = router.served
        record["denied"] = router.denied
        record["denial_report"] = router.denial_report()
        record["functionally_degraded"] = router.is_functionally_degraded()
        record["console_errors"] = [c for c in console if c.startswith("error")][:10]
        record["page_errors"] = page_errors[:10]
        await context.close()

    return record


async def main() -> None:
    results: list[dict] = []
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        version = browser.version
        for path in sorted(ARTIFACTS.glob("subject_*.bin")):
            subject = path.stem.replace("subject_", "")
            capture = path.read_bytes()
            url = _entry_url(flowfile.load_exchanges(capture), subject)
            if url is None:
                results.append({"subject": subject, "ok": False, "error": "no html doc"})
                continue
            for tagged in (False, True):
                for repeat in range(REPEATS):
                    run = await _one_run(browser, capture, url, tagged)
                    run["subject"] = subject
                    run["repeat"] = repeat
                    run["browser"] = version
                    results.append(run)
                    print(
                        f"{subject:>13} tagged={int(tagged)} r{repeat} "
                        f"ok={run.get('ok')} "
                        f"elems={run.get('signature', {}).get('total')} "
                        f"vis={run.get('signature', {}).get('visible')} "
                        f"served={run['served']} denied={run['denied']} "
                        f"essential_missing={len(run['denial_report']['essential'])} "
                        f"stops={run.get('distinct_focus_stops')}"
                    )
        await browser.close()

    DERIVED.mkdir(parents=True, exist_ok=True)
    (DERIVED / "feasibility.json").write_text(json.dumps(results, indent=2) + "\n")
    print(f"\nwrote {len(results)} runs to derived/feasibility.json")


if __name__ == "__main__":
    asyncio.run(main())
