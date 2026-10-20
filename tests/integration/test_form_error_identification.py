"""Precision and recall of the form error check (WCAG SC 3.3.1) on labelled pages.

Runs ``ErrorIdentificationProbe`` on every case in ``form_error_cases.py``,
served over HTTP so the network guard intercepts submissions as it does on a
real site, and scores the outcomes with DETECTION_EFFICACY.md's definitions:

* the positive class is ``fail`` (the form detects an error but does not
  identify it and describe it in text);
* precision ``TP / (TP + FP)``, false-discovery rate ``FP / (TP + FP)``,
  recall ``TP / (TP + FN)``, false-positive rate ``FP / (FP + TN)``;
* ambiguous cases are reported, never scored.

Safety is checked first and is absolute: no form the check must skip may be
pressed. The order of the gates follows the check's own priorities: safety,
then precision, then recall.
"""

from __future__ import annotations

import http.server
import json
import socketserver
import threading
import time
from collections import Counter
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

from audit.analyzer.forms import ErrorIdentificationProbe

from .form_error_cases import CASES

try:
    # Written by someone who had not seen the detector (see that file).
    from .form_error_cases_independent import INDEPENDENT_CASES
except ImportError:  # pragma: no cover - the batch is optional
    INDEPENDENT_CASES = []

ALL_CASES = [*CASES, *INDEPENDENT_CASES]

pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="module")]

playwright = pytest.importorskip("playwright.async_api")


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        return


@contextmanager
def _serve(root: Path) -> Iterator[str]:
    handler = lambda *a, **kw: _QuietHandler(*a, directory=str(root), **kw)  # noqa: E731
    with socketserver.ThreadingTCPServer(("127.0.0.1", 0), handler) as httpd:
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            yield f"http://127.0.0.1:{httpd.server_address[1]}"
        finally:
            httpd.shutdown()
            thread.join(timeout=5)


def score(rows: list[dict[str, str]]) -> dict[str, object]:
    """Precision, recall and the rest, from (expected, predicted) rows."""
    scored = [r for r in rows if r["expected"] != "ambiguous"]
    tp = sum(r["expected"] == "fail" and r["predicted"] == "fail" for r in scored)
    fp = sum(r["expected"] != "fail" and r["predicted"] == "fail" for r in scored)
    fn = sum(r["expected"] == "fail" and r["predicted"] != "fail" for r in scored)
    tn = sum(r["expected"] != "fail" and r["predicted"] != "fail" for r in scored)

    def ratio(a: int, b: int) -> float | None:
        return a / b if b else None

    return {
        "cases": len(rows),
        "scored": len(scored),
        "positives": tp + fn,
        "negatives": fp + tn,
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
        "precision": ratio(tp, tp + fp),
        "false_discovery_rate": ratio(fp, tp + fp),
        "recall": ratio(tp, tp + fn),
        "false_positive_rate": ratio(fp, fp + tn),
        "outcome_accuracy": ratio(
            sum(r["expected"] == r["predicted"] for r in scored), len(scored)
        ),
        "confusion": dict(Counter(f"{r['expected']} -> {r['predicted']}" for r in rows)),
    }


async def test_precision_and_recall(browser, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    for case in ALL_CASES:
        (tmp_path / f"{case.id}.html").write_text(case.html(), encoding="utf-8")

    rows: list[dict[str, str]] = []
    unsafe: list[str] = []
    seconds: list[float] = []
    with _serve(tmp_path) as base:
        for case in ALL_CASES:
            context = await browser.new_context(service_workers="block")
            page = await context.new_page()
            try:
                await page.goto(f"{base}/{case.id}.html", wait_until="load")
                started = time.perf_counter()
                results = await ErrorIdentificationProbe().run(page)
                seconds.append(time.perf_counter() - started)
                predicted = results[0].outcome if results else "none"
                reason = results[0].reason if results else ""
                if case.expected == "skipped" and await page.evaluate("window.__clicked"):
                    unsafe.append(case.id)
            finally:
                await context.close()
            rows.append(
                {"id": case.id, "expected": case.expected, "predicted": predicted, "reason": reason}
            )

    report = score(rows)
    # By when each case was written: with the detector (design), to try to
    # break it and then fixed against (decoy), or after its last change and
    # never tuned against (blind, the honest estimate).
    batches = {"design": "fpncsa", "decoy": "d", "blind 1": "b", "blind 2": "h", "independent": "i"}
    report["by_batch"] = {
        name: {
            k: v
            for k, v in score([r for r in rows if r["id"][0] in prefixes]).items()
            if k != "confusion"
        }
        for name, prefixes in batches.items()
    }
    # Efficiency: the whole check on one page with one form, including the
    # skipped forms that are decided without a click.
    ordered = sorted(seconds)
    report["seconds_per_page"] = {
        "median": round(ordered[len(ordered) // 2], 2),
        "max": round(ordered[-1], 2),
    }
    report["rows"] = rows
    report["unsafe_submissions"] = unsafe
    (tmp_path / "form_error_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("\n" + json.dumps({k: v for k, v in report.items() if k != "rows"}, indent=2))
    for row in rows:
        mark = "  " if row["expected"] in (row["predicted"], "ambiguous") else "XX"
        print(
            f"{mark} {row['id']:<34} expected {row['expected']:<15} "
            f"got {row['predicted']:<15} {row['reason']}"
        )

    # Safety first, and absolute.
    assert not unsafe, f"forms that must be skipped were pressed: {unsafe}"
    # The corpus floors from DETECTION_EFFICACY.md: enough of each class that
    # the rates mean something.
    assert report["positives"] >= 20 and report["negatives"] >= 5
    # Precision before recall: the efficacy gate's false-discovery rate.
    fdr = report["false_discovery_rate"]
    assert fdr is not None and fdr < 0.05, f"false-discovery rate {fdr:.1%}"
