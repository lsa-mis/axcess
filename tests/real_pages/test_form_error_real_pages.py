"""The form error check's metric: precision and recall on real pages.

AGENTS.md ("Building a check: real pages first", steps 6 and 7): a check is
measured on a labelled set of real pages, not on pages we wrote. This runs a
scan the way the app does, with the public-website defaults (every other
browser check first, sending off), one page at a time, and scores each
labelled form (``form_error_pages.py``).

It visits outside sites, so it runs only on request:

    AXCESS_REAL_PAGES=1 uv run pytest tests/real_pages -s

or ``make real-pages``. It writes ``form_error_real_pages.json`` (and the
before and after screenshots of each labelled form) under
``AXCESS_REAL_PAGES_OUT``, default ``build/real_pages``. Live sites change:
a page that moved, broke or changed its form fails the run as "not found",
to be relabelled, not silently scored.
"""

from __future__ import annotations

import asyncio
import json
import math
import os
import re
import sqlite3
from collections import Counter
from pathlib import Path
from typing import Any

import pytest

from audit.analyzer.forms import probe as forms_probe
from audit.crawler.orchestrator import CrawlConfig, run_crawl

from .form_error_pages import PAGES, RealForm

pytestmark = pytest.mark.skipif(
    os.environ.get("AXCESS_REAL_PAGES") != "1",
    reason="visits outside sites; set AXCESS_REAL_PAGES=1 to run",
)

_OUT = Path(os.environ.get("AXCESS_REAL_PAGES_OUT", "build/real_pages"))


def _config(url: str, *, send: bool) -> CrawlConfig:
    """A public-website scan of one page, as New scan starts it by default."""
    return CrawlConfig(
        seed_url=url,
        max_pages=1,
        max_depth=1,
        js_eager=True,
        form_error_checks_enabled=True,
        form_send_empty_forms=send,
        vlm_enabled=False,
        semantic_enabled=False,
        ocr_enabled=False,
    )


def _upper_95(errors: int, n: int) -> float | None:
    """One-sided 95% upper bound on a rate seen ``errors`` times in ``n``
    (Clopper-Pearson for zero; Wilson otherwise)."""
    if n == 0:
        return None
    if errors == 0:
        return 1 - 0.05 ** (1 / n)
    z = 1.645
    p = errors / n
    centre = p + z * z / (2 * n)
    spread = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return min(1.0, (centre + spread) / (1 + z * z / n))


def score(rows: list[dict[str, Any]]) -> dict[str, Any]:
    scored = [r for r in rows if r["expected"] != "disputed" and r["predicted"] != "not found"]
    tp = sum(r["expected"] == "fail" and r["predicted"] == "fail" for r in scored)
    fp = sum(r["expected"] != "fail" and r["predicted"] == "fail" for r in scored)
    fn = sum(r["expected"] == "fail" and r["predicted"] != "fail" for r in scored)
    return {
        "forms": len(rows),
        "scored": len(scored),
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "precision": tp / (tp + fp) if tp + fp else None,
        "false_discovery_upper_95": _upper_95(fp, tp + fp),
        "recall": tp / (tp + fn) if tp + fn else None,
        "not_found": [r["id"] for r in rows if r["predicted"] == "not found"],
        "confusion": dict(Counter(f"{r['expected']} -> {r['predicted']}" for r in rows)),
    }


async def _scan(conn: sqlite3.Connection, url: str, send: bool, out: Path) -> list[Any]:
    """Scan one page; the form check's results for it, screenshots saved."""
    seen: list[Any] = []
    original = forms_probe.ErrorIdentificationProbe.run

    async def run(self: Any, page: Any, **kwargs: Any) -> list[Any]:
        results = await original(self, page, **kwargs)
        seen.extend(results)
        return results

    forms_probe.ErrorIdentificationProbe.run = run
    try:
        await run_crawl(conn, _config(url, send=send))
    finally:
        forms_probe.ErrorIdentificationProbe.run = original
    return seen


def _match(form: RealForm, results: list[Any]) -> Any | None:
    if form.selector:
        hits = [r for r in results if r.selector == form.selector and r.form == form.form]
        return hits[0] if hits else None
    # Without a locator the name is unique on the page.
    hits = [r for r in results if r.form == form.form]
    return hits[0] if len(hits) == 1 else None


def test_real_pages(tmp_db: sqlite3.Connection, tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.setenv("AUDIT_BLOB_DIR", str(tmp_path / "blobs"))
    _OUT.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    by_page: dict[tuple[str, bool], list[RealForm]] = {}
    for form in PAGES:
        by_page.setdefault((form.url, form.send), []).append(form)
    for (url, send), forms in by_page.items():
        results = asyncio.run(_scan(tmp_db, url, send, _OUT))
        for form in forms:
            result = _match(form, results)
            predicted = result.outcome if result else "not found"
            slug = re.sub(r"[^a-z0-9]+", "-", form.id.lower())
            if result is not None:
                for when, png in (("before", result.before_png), ("after", result.after_png)):
                    if png:
                        (_OUT / f"{slug}-{when}.png").write_bytes(png)
            rows.append(
                {
                    "id": form.id,
                    "url": url,
                    "form": form.form,
                    "expected": form.expected,
                    "predicted": predicted,
                    "reason": result.reason if result else "",
                    "basis": form.basis,
                }
            )
            print(f"{form.id:<34} expected {form.expected:<9} got {predicted}", flush=True)
    report = score(rows)
    report["rows"] = rows
    (_OUT / "form_error_real_pages.json").write_text(json.dumps(report, indent=2))
    print(json.dumps({k: v for k, v in report.items() if k != "rows"}, indent=2))
    assert not report["not_found"], f"relabel these, the live page changed: {report['not_found']}"
