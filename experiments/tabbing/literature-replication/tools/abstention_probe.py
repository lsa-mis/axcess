"""Does raising the tab cap clear the 8 abstentions? Tested properly this time.

An earlier standalone check reported 0 stops for `spotify` at caps 212 and 2000
and concluded the abstention was a page property rather than a budget limit.
Claude Code caught that the scored run recorded **9** stops for the same subject
at the same cap, so the two disagreed and the standalone number was wrong.

The cause of that disagreement: `compute_tab_order` records a stop only when the
focused element carries a probe id, and the standalone test never applied the
census, so every marker was unnamed and `index` stayed empty. It measured a
different thing.

`capped` itself is decided by cycle detection, which is largely independent of
naming -- so the conclusion may still hold. "May still hold" is not evidence,
which is why this re-tests it under the scored run's actual conditions: same
replay router, same census, same `data-probe` mirroring.

Pre-registered:
  H-budget: the abstentions are a budget limit. Raising the cap 10x clears them
  and yields a complete walk.
  Falsified if a subject still reports `capped=True` with a cap many times its
  focusable count.
  Control: a subject that completed normally in the scored run must still
  complete here, confirming the harness reproduces the run's conditions.
  Every abstained subject is tested, not a convenient one.

Usage:
    uv run --offline --no-sync python -u -m tools.abstention_probe
"""

from __future__ import annotations

import asyncio
import json
import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO / "src"))

from playwright.async_api import async_playwright  # noqa: E402

from tools import flowfile, replay  # noqa: E402

from audit.analyzer.keyboard.kbdiff.taborder import compute_tab_order  # noqa: E402

HERE = pathlib.Path(__file__).resolve().parent.parent
SUBJECTS = HERE / "artifacts" / "subjects"
SCORED = HERE / "derived" / "kafe_scored.jsonl"
OUT = HERE / "derived" / "abstention_probe.json"

CONTROL = "walmart"  # completed normally in the scored run


def capture(subject: str) -> pathlib.Path:
    legacy = HERE / "artifacts" / f"subject_{subject}.bin"
    return legacy if legacy.exists() else SUBJECTS / f"{subject}.bin"


def entry_url(index: flowfile.ExchangeIndex) -> str | None:
    for group in index.by_url.values():
        for exchange in group:
            if exchange.status == 200 and "text/html" in (
                exchange.headers.get("content-type", "").lower()
            ):
                return exchange.url
    return None


async def walk(browser, subject: str, cap: int) -> dict:
    """One tab walk under the scored run's exact conditions."""
    index = flowfile.load_exchanges(capture(subject).read_bytes())
    url = entry_url(index)
    if url is None:
        return {"subject": subject, "cap": cap, "error": "no entry document"}

    router = replay.ReplayRouter(index)
    context = await browser.new_context(
        viewport={"width": 1920, "height": 1080},
        locale="en-US",
        timezone_id="UTC",
        reduced_motion="reduce",
        service_workers="block",
    )
    await router.attach(context)
    # The census, exactly as the scored run applies it. Without this every
    # marker is unnamed and no stop is recorded -- the defect in the earlier
    # standalone test.
    await context.add_init_script(
        f"""
        window.addEventListener('load', () => {{
            ({replay.NEUTRAL_CENSUS_JS})('{replay.CENSUS_ATTR}');
            for (const el of document.querySelectorAll('[{replay.CENSUS_ATTR}]')) {{
                el.setAttribute('data-probe', el.getAttribute('{replay.CENSUS_ATTR}'));
            }}
        }});
        """
    )
    page = await context.new_page()
    try:
        await page.goto(url, wait_until="load", timeout=60_000)
        await page.wait_for_timeout(3_000)
        focusable = await page.evaluate(
            """() => document.querySelectorAll(
                'a[href],button,input,select,textarea,[tabindex],[onclick]').length"""
        )
        order = await compute_tab_order(page, max_tabs=cap)
        return {
            "subject": subject,
            "cap": cap,
            "focusable": focusable,
            "stops": len(order.index),
            "presses": order.presses,
            "capped": order.capped,
        }
    except Exception as exc:
        return {"subject": subject, "cap": cap, "error": f"{type(exc).__name__}: {exc}"}
    finally:
        await context.close()


async def main() -> int:
    records = [json.loads(l) for l in SCORED.read_text().splitlines() if l.strip()]
    abstained = [r["subject"] for r in records if r.get("status") != "scored"]
    original = {r["subject"]: r for r in records}

    print(f"testing {len(abstained)} abstained subjects + 1 control\n")
    rows = []
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)

        # Control first: if this does not reproduce the run's behaviour, no
        # result below means anything.
        ctrl = await walk(browser, CONTROL, original[CONTROL]["tab_cap"])
        ctrl["role"] = "control"
        rows.append(ctrl)
        print(f"CONTROL {CONTROL:<16} cap={ctrl.get('cap'):<6} "
              f"stops={ctrl.get('stops')} capped={ctrl.get('capped')} "
              f"(run recorded capped={original[CONTROL]['tab_capped']})", flush=True)
        print()

        for subject in abstained:
            was = original[subject]
            big = max(2000, (was.get("focusable") or 0) * 20)
            row = await walk(browser, subject, big)
            row["role"] = "abstained"
            row["original_cap"] = was.get("tab_cap")
            row["original_stops"] = was.get("tab_stops")
            rows.append(row)
            print(
                f"{subject:<16} focusable={row.get('focusable'):<5} "
                f"cap {was.get('tab_cap')} -> {big:<6} "
                f"stops {was.get('tab_stops')} -> {row.get('stops')}  "
                f"capped={row.get('capped')}",
                flush=True,
            )
        await browser.close()

    tested = [r for r in rows if r.get("role") == "abstained" and "capped" in r]
    cleared = [r for r in tested if not r["capped"]]
    OUT.write_text(json.dumps(rows, indent=2) + "\n")

    print()
    print(
        json.dumps(
            {
                "control_reproduced_run": ctrl.get("capped") is False,
                "abstained_tested": len(tested),
                "cleared_by_a_bigger_cap": len(cleared),
                "cleared_subjects": [r["subject"] for r in cleared],
                "still_capped": [r["subject"] for r in tested if r["capped"]],
                "H-budget_falsified": len(cleared) == 0,
                "verdict": (
                    "budget was not the cause: every walk still caps at 10-20x"
                    if not cleared
                    else f"{len(cleared)}/{len(tested)} abstentions were a budget limit "
                    "and the scored run understated recall by that many subjects"
                ),
            },
            indent=1,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
