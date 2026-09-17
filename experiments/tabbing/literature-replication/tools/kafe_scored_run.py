"""The scored run: frozen Axcess detectors on the 53 replayable KAFE subjects.

This is the experiment the whole line of work exists to perform. Every earlier
arm either measured something else (`tools/gds_run.py` reimplemented the
differential instead of importing it) or established preconditions. Here the
detectors are imported unmodified from `audit.analyzer.keyboard.kbdiff` and run
against captures of the original KAFE subjects.

Unbounded by explicit instruction: every candidate on every subject is probed,
however long it takes. Each subject is appended to the results file the moment
it finishes, so an interruption costs one subject rather than the run.

Design decisions that are load-bearing, each with its reason:

* **The tab cap is set per subject from its own focusable-element count.**
  Inheriting the 300 default silently turned two real GDS failures into
  `unknown` because that page has 306 focusable elements. craigslist has 1540.
  A capped walk is recorded and treated as an abstention, never as a negative.
* **Identity comes from the neutral census**, which assigns ids from tree
  position alone. The detectors address elements by `data-probe`; KAFE captures
  carry none. Supplying an identity is not changing what the detectors decide.
* **Page-level projection is page-positive iff >=1 element is reported**, which
  is the bridge KAFE's page x IAF unit requires. Element-level counts are kept
  separately and never mixed in.
* **Abstentions are not negatives.** A capped tab walk, a replay failure, a
  subject whose capture yields no entry document, or a page where every probe
  returned UNKNOWN all abstain. They are reported with their own denominators.

Usage:
    uv run --offline --no-sync python -u -m tools.kafe_scored_run
    uv run --offline --no-sync python -u -m tools.kafe_scored_run --limit 2
"""

from __future__ import annotations

import argparse
import asyncio
import json
import pathlib
import sys
import time

REPO = pathlib.Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO / "src"))

from playwright.async_api import async_playwright  # noqa: E402

from tools import flowfile, replay  # noqa: E402

from audit.analyzer.keyboard.kbdiff.candidates import collect_candidates  # noqa: E402
from audit.analyzer.keyboard.kbdiff.differential import (  # noqa: E402
    DifferentialRunner,
    TrialConfig,
)

HERE = pathlib.Path(__file__).resolve().parent.parent
SUBJECTS = HERE / "artifacts" / "subjects"
LEGACY = {
    "citiprogram": HERE / "artifacts" / "subject_citiprogram.bin",
    "craigslist": HERE / "artifacts" / "subject_craigslist.bin",
    "coronavirus": HERE / "artifacts" / "subject_coronavirus.bin",
}
CENSUS = HERE / "derived" / "kafe_corpus_census.json"
DENOM = HERE / "derived" / "kafe_denominator.json"
OUT = HERE / "derived" / "kafe_scored.jsonl"

VIEWPORT = {"width": 1920, "height": 1080}  # KAFE section 5.1
TAB_HEADROOM = 200  # cap = focusable count + this, so a complete walk is provable


def capture_path(subject: str) -> pathlib.Path:
    return LEGACY.get(subject) or (SUBJECTS / f"{subject}.bin")


def entry_url(index: flowfile.ExchangeIndex) -> str | None:
    """First HTML 200 in capture order: the document the browser should open."""
    for group in index.by_url.values():
        for exchange in group:
            if exchange.status == 200 and "text/html" in (
                exchange.headers.get("content-type", "").lower()
            ):
                return exchange.url
    return None


async def score_subject(browser, subject: str, label: bool | None) -> dict:
    """Replay one subject, run the frozen detectors on every candidate."""
    started = time.perf_counter()
    record: dict = {
        "subject": subject,
        "y": label,
        "started": time.strftime("%H:%M:%S"),
    }

    path = capture_path(subject)
    if not path.exists():
        return {**record, "status": "abstain", "reason": "capture file missing"}

    try:
        index = flowfile.load_exchanges(path.read_bytes())
    except Exception as exc:
        return {**record, "status": "abstain", "reason": f"unparseable: {exc}"}

    url = entry_url(index)
    if url is None:
        return {**record, "status": "abstain", "reason": "no HTML entry document"}
    record["entry"] = url

    router = replay.ReplayRouter(index)

    async def make_context():
        # One router across the run keeps repeated requests in capture order,
        # which is what `resolve` documents. Every context re-applies the
        # census on load, because a fresh trial context starts with a clean DOM
        # and `data-probe` would otherwise be absent when the probe resolves.
        context = await browser.new_context(
            viewport=VIEWPORT,
            locale="en-US",
            timezone_id="UTC",
            reduced_motion="reduce",
            service_workers="block",
        )
        await router.attach(context)
        await context.add_init_script(
            f"""
            window.addEventListener('load', () => {{
                ({replay.NEUTRAL_CENSUS_JS})('{replay.CENSUS_ATTR}');
                for (const el of document.querySelectorAll('[{replay.CENSUS_ATTR}]')) {{
                    el.setAttribute('data-probe',
                                    el.getAttribute('{replay.CENSUS_ATTR}'));
                }}
            }});
            """
        )
        return context

    # Census + candidate discovery happen once, in their own context.
    try:
        context = await make_context()
        page = await context.new_page()
        await page.goto(url, wait_until="load", timeout=60_000)
        await page.wait_for_timeout(3_000)  # settle, as in the feasibility runs
        tagged = await page.evaluate(replay.NEUTRAL_CENSUS_JS, replay.CENSUS_ATTR)
        # The detectors address elements by `data-probe`; mirror the census id
        # onto it so identity is still position-derived and label-independent.
        await page.evaluate(
            """(attr) => {
                for (const el of document.querySelectorAll('[' + attr + ']')) {
                    el.setAttribute('data-probe', el.getAttribute(attr));
                }
            }""",
            replay.CENSUS_ATTR,
        )
        focusable = await page.evaluate(
            """() => document.querySelectorAll(
                'a[href],button,input,select,textarea,[tabindex],[onclick]').length"""
        )
        candidates = await collect_candidates(page)
        await context.close()
    except Exception as exc:
        return {
            **record,
            "status": "abstain",
            "reason": f"replay failed: {type(exc).__name__}: {exc}",
            "elapsed_s": round(time.perf_counter() - started, 1),
        }

    probe_ids = sorted({c.probe_id for c in candidates if c.probe_id})
    record.update(
        {
            "census_tagged": tagged,
            "focusable": focusable,
            "candidates": len(candidates),
            "addressable_candidates": len(probe_ids),
            "served": router.served,
            "denied": router.denied,
            "functionally_degraded": router.is_functionally_degraded(),
        }
    )

    # The cap is derived, not inherited. A walk that still caps is an
    # abstention: absence of a probe from a capped order is a budget limit,
    # not a finding.
    cap = focusable + TAB_HEADROOM
    config = TrialConfig(url=url, viewport="1920x1080", max_tabs=cap)
    runner = DifferentialRunner(make_context, config)

    try:
        order = await runner.tab_order()
    except Exception as exc:
        return {
            **record,
            "status": "abstain",
            "reason": f"tab order failed: {type(exc).__name__}: {exc}",
            "tab_cap": cap,
            "elapsed_s": round(time.perf_counter() - started, 1),
        }

    record["tab_cap"] = cap
    record["tab_stops"] = len(order.index)
    record["tab_capped"] = order.capped

    if order.capped:
        return {
            **record,
            "status": "abstain",
            "reason": f"tab walk capped at {cap} with {focusable} focusable elements",
            "elapsed_s": round(time.perf_counter() - started, 1),
        }

    verdicts: dict[str, int] = {}
    reported: list[str] = []
    per_probe_ms: list[float] = []
    errors = 0

    for probe_id in probe_ids:
        t0 = time.perf_counter()
        try:
            outcome = await runner.run_probe(probe_id, subject, order)
            verdict = str(outcome.verdict)
        except Exception:
            errors += 1
            verdict = "error"
        per_probe_ms.append((time.perf_counter() - t0) * 1000)
        verdicts[verdict] = verdicts.get(verdict, 0) + 1
        if "violation" in verdict:
            reported.append(probe_id)

    per_probe_ms.sort()
    n = len(per_probe_ms)
    record.update(
        {
            "status": "scored",
            "verdicts": verdicts,
            "probe_errors": errors,
            "reported_elements": len(reported),
            "reported_ids": reported[:50],
            "yhat": 1 if reported else 0,
            "ms_median": round(per_probe_ms[n // 2], 1) if n else None,
            "ms_min": round(per_probe_ms[0], 1) if n else None,
            "ms_max": round(per_probe_ms[-1], 1) if n else None,
            "ms_total": round(sum(per_probe_ms), 1),
            "elapsed_s": round(time.perf_counter() - started, 1),
        }
    )
    return record


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0, help="smoke-test N subjects")
    parser.add_argument("--only", default="", help="comma-separated subject names")
    args = parser.parse_args()

    census = {r["subject"]: r for r in json.loads(CENSUS.read_text())}
    denom = json.loads(DENOM.read_text())
    labels = {
        s["subject"]: s["y"]
        for s in denom["subjects"]
        if s.get("status") == "replayable"
    }

    todo = [s for s in sorted(labels) if census.get(s, {}).get("entry")]
    if args.only:
        wanted = {x.strip() for x in args.only.split(",")}
        todo = [s for s in todo if s in wanted]
    elif args.limit:
        pos = [s for s in todo if labels[s]][: args.limit]
        neg = [s for s in todo if not labels[s]][: args.limit]
        todo = pos + neg

    done = set()
    if OUT.exists():
        for line in OUT.read_text().splitlines():
            if line.strip():
                done.add(json.loads(line)["subject"])
    todo = [s for s in todo if s not in done]

    print(f"{len(todo)} subjects to score ({len(done)} already in {OUT.name})")
    print(f"unbounded: every candidate on every subject is probed", flush=True)

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        for i, subject in enumerate(todo, 1):
            record = await score_subject(browser, subject, labels.get(subject))
            with OUT.open("a") as handle:
                handle.write(json.dumps(record) + "\n")
            status = record.get("status")
            if status == "scored":
                print(
                    f"[{i}/{len(todo)}] {subject:<20} y={record['y']} "
                    f"yhat={record['yhat']} "
                    f"probes={record['addressable_candidates']} "
                    f"reported={record['reported_elements']} "
                    f"median={record['ms_median']}ms "
                    f"({record['elapsed_s']}s)",
                    flush=True,
                )
            else:
                print(
                    f"[{i}/{len(todo)}] {subject:<20} ABSTAIN: {record.get('reason')}",
                    flush=True,
                )
        await browser.close()

    print("done")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
