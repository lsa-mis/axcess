"""A/B/C: the shipped keyboard check against the upgraded Standard and Advanced.

Arms, each on a fresh context and page per corpus page:

* ``A current``: ``KeyboardProbe`` alone, what a scan runs today (SC 2.1.2).
* ``B standard``: ``KeyboardProbe`` then ``KeyboardOperabilityProbe()``.
* ``C advanced``: ``KeyboardProbe`` then ``KeyboardOperabilityProbe(advanced=True)``.

B and C include A's Tab walk, so their times are the whole keyboard check's
cost and are directly comparable to A's.

Element corpora (``fixtures``, ``edgecases``, ``gds``, ``ma11y``) are served
from disk through ``runner.serve`` with no socket. A lead is attributed to the
nearest ancestor carrying ``data-probe``; a lead with none is counted as an
unlabelled flag. KAFE subjects are replayed offline from their captures through
``tools.replay`` (default-deny, no origin contact) and scored per page:
positive iff the arm reported at least one finding.

Usage (from the repo root):
    uv run python experiments/tabbing/ab/run_ab.py --corpus fixtures --label dev1
    uv run python experiments/tabbing/ab/run_ab.py --corpus kafe --label heldout1
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import platform
import statistics
import sys
import time
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[3]
LITREP = REPO / "experiments" / "tabbing" / "literature-replication"
for extra in (REPO, REPO / "src", LITREP):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from playwright.async_api import async_playwright  # noqa: E402

from audit.analyzer.keyboard import KeyboardProbe  # noqa: E402
from audit.analyzer.keyboard.base import SC_2_1_1  # noqa: E402
from audit.analyzer.keyboard.operability import KeyboardOperabilityProbe  # noqa: E402
from experiments.tabbing.runner.bakeoff import CORPORA, load_truth  # noqa: E402
from experiments.tabbing.runner.serve import ContextFactory, page_url  # noqa: E402

OUT_DIR = Path(__file__).resolve().parent / "results"
ARMS = ("A current", "B1 standard-v1", "B standard", "C advanced")
ELEMENT_VIEWPORT = {"width": 1280, "height": 900}  # the bakeoff's desktop layout
PAGE_SETTLE_MS = 120  # the rule probes' wait after load
KAFE_SETTLE_MS = 3000  # kafe_matrix's wait after load
PAGE_TIMEOUT_S = 300
# --quiet: a sealed run writes its artifact without showing a single verdict.
QUIET = False


async def run_arm(page: Any, arm: str) -> dict[str, Any]:
    """Run one arm on a loaded page; return its flags and timings."""
    t0 = time.perf_counter()
    traps = await KeyboardProbe().run(page)
    t1 = time.perf_counter()
    record: dict[str, Any] = {
        "traps": [t.target_selector for t in traps],
        "walk_ms": round((t1 - t0) * 1000, 1),
        "operability_ms": 0.0,
        "leads": [],
    }
    if arm != "A current":
        probe = KeyboardOperabilityProbe(
            advanced=arm == "C advanced",
            extended=arm != "B1 standard-v1",
            annotate_attr="data-probe",
        )
        result = await probe.analyze(page)
        record["operability_ms"] = round(result.elapsed_ms, 1)
        record["considered"] = result.considered
        record["tested"] = result.tested
        record["limits"] = sorted(result.limits)
        record["drops"] = result.drops
        record["leads"] = [
            {
                "probe": lead.probe,
                "also_probe": lead.also_probe,
                "kind": lead.kind,
                "verdict": lead.verdict,
                "selector": lead.selector,
                "signals": list(lead.signals),
                "evidence": lead.evidence,
                "frame": bool(lead.frame_url),
            }
            for lead in result.leads
        ]
    record["total_ms"] = round(record["walk_ms"] + record["operability_ms"], 1)
    return record


def reported(record: dict[str, Any]) -> list[dict[str, Any]]:
    return [lead for lead in record["leads"] if lead["verdict"] != "dismissed"][:25]


# ---------------------------------------------------------------------------
# Element corpora.
# ---------------------------------------------------------------------------


async def run_elements(corpus: str, arms: tuple[str, ...]) -> dict[str, Any]:
    root, truth_name, description = CORPORA[corpus]
    pages, labels = load_truth(root, truth_name)
    out: dict[str, Any] = {"corpus": corpus, "description": description, "pages": {}}
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        factory = ContextFactory(browser, ELEMENT_VIEWPORT, root)
        for rel in sorted(pages):
            out["pages"][rel] = {}
            for arm in arms:
                context = await factory()
                try:
                    page = await context.new_page()
                    await page.goto(page_url(rel), wait_until="load")
                    await page.wait_for_timeout(PAGE_SETTLE_MS)
                    async with asyncio.timeout(PAGE_TIMEOUT_S):
                        out["pages"][rel][arm] = await run_arm(page, arm)
                except Exception as exc:
                    out["pages"][rel][arm] = {"error": f"{type(exc).__name__}: {exc}"[:300]}
                finally:
                    await context.close()
            print(
                f"  {rel}: "
                + ", ".join(
                    f"{arm.split()[0]}={len(reported(out['pages'][rel][arm])) if 'leads' in out['pages'][rel][arm] else 'ERR'}"
                    for arm in arms
                ),
                flush=True,
            )
        await browser.close()
    out["scores"] = {arm: score_elements(out, pages, labels, arm) for arm in arms}
    return out


def score_elements(
    out: dict[str, Any], pages: dict[str, list[str]], labels: dict[str, str], arm: str
) -> dict[str, Any]:
    tp = fp = fn = unlabelled = errors = 0
    walk: list[float] = []
    total: list[float] = []
    fps: list[str] = []
    fns: list[str] = []
    for rel, ids in pages.items():
        record = out["pages"][rel].get(arm, {})
        if "leads" not in record:
            errors += 1
            fn += sum(1 for pid in ids if labels[pid] == "violation")
            continue
        walk.append(record["walk_ms"])
        total.append(record["total_ms"])
        flagged: set[str] = set()
        for lead in reported(record):
            named = {p for p in (lead["probe"], lead.get("also_probe")) if p is not None}
            if not named:
                unlabelled += 1
            flagged |= named
        for pid in ids:
            positive = labels[pid] == "violation"
            if pid in flagged and positive:
                tp += 1
            elif pid in flagged:
                fp += 1
                fps.append(pid)
            elif positive:
                fn += 1
                fns.append(pid)
    return _summary(tp, fp, fn, total, walk, len(labels), errors) | {
        "unlabelled_flags": unlabelled,
        "fp_ids": sorted(fps),
        "fn_ids": sorted(fns),
    }


# ---------------------------------------------------------------------------
# KAFE, replayed.
# ---------------------------------------------------------------------------


def kafe_subjects(which: str = "scored") -> list[tuple[str, bool]]:
    """KAFE subjects with their ground truth.

    ``scored``: the 40 the literature matrix scored. ``sealed``: the 13 it
    abstained on (its candidate collector found nothing, or its Tab walk
    capped). This probe depends on neither, so they are a fresh test set:
    kept unseen while the detector was developed on the 40.
    """
    rows = [json.loads(line) for line in (LITREP / "derived" / "kafe_matrix.jsonl").open()]
    wanted = "scored" if which == "scored" else "abstain"
    return [(r["subject"], bool(r["y"])) for r in rows if r.get("status") == wanted]


async def run_kafe(
    arms: tuple[str, ...], only: list[str] | None, which: str = "scored"
) -> dict[str, Any]:
    from tools import flowfile, kafe_matrix, replay

    subjects = [s for s in kafe_subjects(which) if not only or s[0] in only]
    out: dict[str, Any] = {"corpus": "kafe", "set": which, "subjects": {}}
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        for subject, label in subjects:
            index = flowfile.load_exchanges(kafe_matrix.capture_path(subject).read_bytes())
            url = kafe_matrix.entry_url(index)
            router = replay.ReplayRouter(index)
            record: dict[str, Any] = {"y": label, "arms": {}}
            for arm in arms:
                context = await browser.new_context(
                    viewport=kafe_matrix.VIEWPORT,
                    locale="en-US",
                    timezone_id="UTC",
                    reduced_motion="reduce",
                    service_workers="block",
                )
                try:
                    await router.attach(context)
                    page = await context.new_page()
                    await page.goto(url, wait_until="load", timeout=60_000)
                    await page.wait_for_timeout(KAFE_SETTLE_MS)
                    async with asyncio.timeout(PAGE_TIMEOUT_S):
                        record["arms"][arm] = await run_arm(page, arm)
                except Exception as exc:
                    record["arms"][arm] = {"error": f"{type(exc).__name__}: {exc}"[:300]}
                finally:
                    await context.close()
            out["subjects"][subject] = record
            if not QUIET:
                print(
                    f"  {subject} y={label}: "
                    + ", ".join(
                        f"{arm.split()[0]}={_kafe_flags(record['arms'][arm])}" for arm in arms
                    ),
                    flush=True,
                )
        await browser.close()
    out["scores"] = {arm: score_kafe(out, arm) for arm in arms}
    return out


def _kafe_flags(record: dict[str, Any]) -> int | str:
    if "leads" not in record:
        return "ERR"
    return len(reported(record)) + len(record["traps"])


def score_kafe(out: dict[str, Any], arm: str) -> dict[str, Any]:
    tp = fp = fn = tn = errors = 0
    total: list[float] = []
    walk: list[float] = []
    for subject, record in out["subjects"].items():
        result = record["arms"].get(arm, {})
        if "leads" not in result:
            errors += 1
            continue
        total.append(result["total_ms"])
        walk.append(result["walk_ms"])
        flagged = bool(reported(result)) or bool(result["traps"])
        if flagged and record["y"]:
            tp += 1
        elif flagged:
            fp += 1
        elif record["y"]:
            fn += 1
        else:
            tn += 1
    positives = sum(1 for r in out["subjects"].values() if r["y"])
    return _summary(tp, fp, fn, total, walk, positives, errors) | {
        "tn": tn,
        "strict_recall": tp / positives if positives else None,
    }


def _summary(
    tp: int, fp: int, fn: int, total: list[float], walk: list[float], n: int, errors: int
) -> dict[str, Any]:
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    f1 = (
        2 * precision * recall / (precision + recall)
        if precision is not None and recall and precision + recall
        else None
    )
    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "errors": errors,
        "units": n,
        "page_ms_median": round(statistics.median(total), 1) if total else None,
        "page_ms_mean": round(statistics.fmean(total), 1) if total else None,
        "page_ms_max": round(max(total), 1) if total else None,
        "walk_ms_mean": round(statistics.fmean(walk), 1) if walk else None,
        "sum_ms": round(sum(total), 1),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", required=True, choices=[*CORPORA, "kafe"])
    parser.add_argument("--label", required=True)
    parser.add_argument("--arms", default="A,B1,B,C")
    parser.add_argument("--only", nargs="*", help="KAFE subjects to run (default: the 40)")
    parser.add_argument("--kafe-set", choices=["scored", "sealed"], default="scored")
    parser.add_argument("--quiet", action="store_true", help="write the artifact, print nothing")
    args = parser.parse_args()
    global QUIET
    QUIET = args.quiet
    arms = tuple(a for a in ARMS if a.split()[0] in args.arms.split(","))
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    name = "kafe-sealed" if args.corpus == "kafe" and args.kafe_set == "sealed" else args.corpus
    target = OUT_DIR / f"ab-{name}-{args.label}.json"
    if target.exists():
        raise SystemExit(f"{target} exists; results are never overwritten, pick a new --label")
    started = time.perf_counter()
    if args.corpus == "kafe":
        out = asyncio.run(run_kafe(arms, args.only, args.kafe_set))
    else:
        out = asyncio.run(run_elements(args.corpus, arms))
    out["provenance"] = {
        "label": args.label,
        "utc": datetime.now(UTC).isoformat(),
        "python": platform.python_version(),
        "playwright": version("playwright"),
        "elapsed_s": round(time.perf_counter() - started, 1),
        # Pins the detector these numbers describe.
        "operability_sha256": hashlib.sha256(
            (REPO / "src/audit/analyzer/keyboard/operability.py").read_bytes()
        ).hexdigest(),
    }
    target.write_text(json.dumps(out, indent=1, sort_keys=True) + "\n")
    if args.quiet:
        print(f"wrote {target}")
        return
    for arm in arms:
        s = out["scores"][arm]
        pct = lambda v: "—" if v is None else f"{v * 100:.1f}%"  # noqa: E731
        print(
            f"{arm:12s} TP {s['tp']:3d} FP {s['fp']:3d} FN {s['fn']:3d}  "
            f"P {pct(s['precision'])} R {pct(s['recall'])} F1 {pct(s['f1'])}  "
            f"page ms median {s['page_ms_median']} mean {s['page_ms_mean']} max {s['page_ms_max']}"
            + (f"  unlabelled {s['unlabelled_flags']}" if "unlabelled_flags" in s else "")
        )
    print(f"wrote {target}")


if __name__ == "__main__":
    _ = SC_2_1_1
    main()
