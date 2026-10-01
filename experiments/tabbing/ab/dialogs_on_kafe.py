"""Click-Through's dialog checks on the KAFE replays: volume, cost, leads.

Two arms per subject, each on a fresh replay (offline, default-deny):

* ``before``: Click-Through as it was before the dialog work: the old
  candidate list (no ``a[href="#"]``) and no dialog checks.
* ``after``: the current candidate list with the dialog checks on, and the
  time spent inside them measured separately.

KAFE labels no dialogs, so this measures what the checks cost and how often
they fire on real pages; the leads are written out for a person to review.

    uv run python experiments/tabbing/ab/dialogs_on_kafe.py OUT.jsonl [SUBJECT...]
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
LITREP = REPO / "experiments" / "tabbing" / "literature-replication"
for extra in (REPO, REPO / "src", LITREP):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from playwright.async_api import async_playwright  # noqa: E402

import audit.analyzer.interaction.probe as probe_module  # noqa: E402
from audit.analyzer.axe import AxeAnalyzer  # noqa: E402
from audit.analyzer.interaction import InteractionProbe, dialogs  # noqa: E402

_OLD_SELECTOR = probe_module._CANDIDATE_SELECTOR.replace(', a[href="#"], a[href=""]', "")
_NEW_SELECTOR = probe_module._CANDIDATE_SELECTOR
SPENT = {"ms": 0.0}


def _timed(fn):  # type: ignore[no-untyped-def]
    async def wrapper(*args, **kwargs):  # type: ignore[no-untyped-def]
        t = time.perf_counter()
        try:
            return await fn(*args, **kwargs)
        finally:
            SPENT["ms"] += (time.perf_counter() - t) * 1000

    return wrapper


for name in ("overlay_ids", "new_overlays", "check_opened", "check_escape"):
    setattr(dialogs, name, _timed(getattr(dialogs, name)))


async def one(browser, subject: str, arm: str) -> dict:  # type: ignore[no-untyped-def]
    from tools import flowfile, kafe_matrix, replay

    index = flowfile.load_exchanges(kafe_matrix.capture_path(subject).read_bytes())
    url = kafe_matrix.entry_url(index)
    router = replay.ReplayRouter(index)
    ctx = await browser.new_context(viewport=kafe_matrix.VIEWPORT, service_workers="block")
    try:
        await router.attach(ctx)
        page = await ctx.new_page()
        await page.goto(url, wait_until="load", timeout=60_000)
        await page.wait_for_timeout(3000)
        probe_module._CANDIDATE_SELECTOR = _OLD_SELECTOR if arm == "before" else _NEW_SELECTOR
        probe = InteractionProbe(
            axe=AxeAnalyzer.from_bundled(), level="AA", dialog_checks=arm == "after", timeout_s=180
        )
        SPENT["ms"] = 0.0
        t = time.perf_counter()
        result = await probe.run(page)
        return {
            "s": subject,
            "arm": arm,
            "ms": round((time.perf_counter() - t) * 1000),
            "dialog_ms": round(SPENT["ms"]),
            "clicks": result.clicks_succeeded,
            "states": result.states,
            "dialogs_opened": result.dialogs_opened,
            "limits": list(result.limits),
            "leads": [
                [f.rule_id, f.criterion_sc, f.target_selector, f.failure_summary[:200]]
                for f in result.keyboard_findings
            ],
        }
    except Exception as exc:
        return {"s": subject, "arm": arm, "err": f"{type(exc).__name__}: {exc}"[:160]}
    finally:
        await ctx.close()


async def main(out: Path, subjects: list[str]) -> None:
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        with out.open("a") as fh:
            for subject in subjects:
                for arm in ("before", "after"):
                    fh.write(json.dumps(await one(browser, subject, arm)) + "\n")
                    fh.flush()
        await browser.close()


if __name__ == "__main__":
    out = Path(sys.argv[1])
    subjects = sys.argv[2:] or [
        json.loads(line)["subject"] for line in (LITREP / "derived" / "kafe_matrix.jsonl").open()
    ]
    asyncio.run(main(out, subjects))
