"""The document check's metric: precision and recall on real PDFs.

AGENTS.md ("Building a check: real pages first", steps 6 and 7). The
labelled set is ``document_check_labels.json``: real PDFs a real scan of
hr.umich.edu downloaded (2026-11-17), each with whether it has a problem
that stops or misleads a screen reader or keyboard user, and which checks
it should fail. Read the set's ``about`` before quoting a number: it is
small, mostly one publisher's forms, judged by an agent inspecting each
file's structure (not a person with a screen reader), and the four
structure checks were tuned on these same files.

Two scores:

``file``
    Any failed check against ``has_reader_problem``: does the report's
    "Mostly sure" mean what it says?
``<check>``
    Each check against the files whose ``expected_failed_checks`` name it,
    and the files of ``document_structure_labels.json`` judged on it
    (``judged_checks``), scored apart: ``<check> (publishers)`` for its
    real-world files and ``<check> (test-suite)`` for files written to show
    one fault each, which are not real-world accuracy. A file the check did
    not run on (``checks_run``) counts as not failed.

Each file is downloaded again (it visits outside sites, so it runs only on
request), its SHA-256 compared with the labelled one, and checked by
``pdf_check.check_pdf``::

    AXCESS_REAL_PAGES=1 uv run pytest tests/real_pages/test_document_check_real_files.py -s

A file that changed since it was labelled fails the run, to be relabelled,
not silently scored. Writes ``document_check_real_files.json`` under
``AXCESS_REAL_PAGES_OUT``.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
from pathlib import Path
from typing import Any

import httpx
import pytest

from audit.config import Settings
from audit.linked_files.pdf_check import ALL_CHECKS, check_pdf

pytestmark = pytest.mark.skipif(
    os.environ.get("AXCESS_REAL_PAGES") != "1",
    reason="visits outside sites; set AXCESS_REAL_PAGES=1 to run",
)

LABELS = Path(__file__).with_name("document_check_labels.json")
#: Files judged on some checks only (``judged_checks``): the table and
#: formula checks' set, from many publishers, with test-suite files.
STRUCTURE_LABELS = Path(__file__).with_name("document_structure_labels.json")
_OUT = Path(os.environ.get("AXCESS_REAL_PAGES_OUT", "build/real_pages"))
#: Seconds between downloads: one at a time, politely.
PAUSE_S = 1.0


def score(pairs: list[tuple[bool | None, bool]]) -> dict[str, Any]:
    """Precision and recall over ``(expected, predicted)``; None expected is skipped."""
    scored = [(e, p) for e, p in pairs if e is not None]
    tp = sum(e and p for e, p in scored)
    fp = sum(not e and p for e, p in scored)
    fn = sum(e and not p for e, p in scored)
    return {
        "scored": len(scored),
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "precision": tp / (tp + fp) if tp + fp else None,
        "recall": tp / (tp + fn) if tp + fn else None,
    }


def test_score_counts_only_decided_labels() -> None:
    pairs = [(True, True), (True, False), (False, True), (None, True)]
    assert score(pairs) == {
        "scored": 3,
        "tp": 1,
        "fp": 1,
        "fn": 1,
        "precision": 0.5,
        "recall": 0.5,
    }


async def _download(files: list[dict[str, Any]], folder: Path) -> dict[str, Path | str]:
    """Each labelled file's bytes on disk, or why not ("changed", an error)."""
    settings = Settings()
    out: dict[str, Path | str] = {}
    async with httpx.AsyncClient(
        headers={"User-Agent": settings.user_agent}, follow_redirects=True, timeout=30
    ) as client:
        for index, item in enumerate(files):
            if index:
                await asyncio.sleep(PAUSE_S)
            try:
                response = await client.get(item["url"])
                response.raise_for_status()
            except httpx.HTTPError as exc:
                out[item["sha256"]] = type(exc).__name__
                continue
            if hashlib.sha256(response.content).hexdigest() != item["sha256"]:
                out[item["sha256"]] = "changed"
                continue
            path = folder / f"{index}.pdf"
            path.write_bytes(response.content)
            out[item["sha256"]] = path
    return out


def test_real_files(tmp_path: Path) -> None:
    files = json.loads(LABELS.read_text())["files"]
    downloaded = asyncio.run(_download(files, tmp_path))
    rows = []
    for item in files:
        got = downloaded[item["sha256"]]
        if not isinstance(got, Path):
            rows.append({"url": item["url"], "error": got})
            continue
        result = check_pdf(got.read_bytes())
        rows.append(
            {
                "url": item["url"],
                "has_reader_problem": item["has_reader_problem"],
                "expected_failed_checks": item["expected_failed_checks"],
                "failed": list(result.failed),
                "checks_run": list(result.checks_run),
            }
        )
    checked = [r for r in rows if "failed" in r]
    scores = {"file": score([(r["has_reader_problem"], bool(r["failed"])) for r in checked])}
    for check in ALL_CHECKS:
        scores[check] = score(
            [
                (
                    None
                    if r["expected_failed_checks"] is None
                    else check in r["expected_failed_checks"],
                    check in r["failed"],
                )
                for r in checked
            ]
        )
    structure = json.loads(STRUCTURE_LABELS.read_text())["files"]
    (tmp_path / "structure").mkdir()
    got_structure = asyncio.run(_download(structure, tmp_path / "structure"))
    pairs: dict[str, list[tuple[bool | None, bool]]] = {}
    for item in structure:
        got = got_structure[item["sha256"]]
        if not isinstance(got, Path):
            rows.append({"url": item["url"], "error": got})
            continue
        failed = list(check_pdf(got.read_bytes()).failed)
        if {"table_cells_misplaced", "table_uneven_rows"} & set(failed):
            # Test-suite verdicts predate the split into two table checks.
            failed.append("table_rows_fault")
        for check, expected in item["judged_checks"].items():
            name = f"{check} ({'publishers' if item['kind'] == 'real-world' else 'test-suite'})"
            pairs.setdefault(name, []).append((expected, check in failed))
    for name, judged in pairs.items():
        scores[name] = score(judged)
    _OUT.mkdir(parents=True, exist_ok=True)
    (_OUT / "document_check_real_files.json").write_text(
        json.dumps({"scores": scores, "rows": rows}, indent=2)
    )
    for name, result in scores.items():
        print(name, result)
    missing = [r["url"] for r in rows if "error" in r]
    assert not missing, f"relabel or drop: {missing}"
