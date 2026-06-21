"""Integration tests for the per-criterion semantic pipeline.

Two flavors:

* **Mocked** (default, fast): builds a real :class:`OllamaTextProvider`
  but stubs the HTTP layer with respx. Pins the end-to-end shape:
  config + criteria flag → analyzer registration → per-page LLM call
  → JSON parse → DB row with pipeline='semantic'.

* **Live** (gated on ``AUDIT_OLLAMA_LIVE=1``): hits a real local
  Ollama daemon to measure precision/recall against the hand-labeled
  fixture set in ``tests/fixtures/site/sc_2_4_4/``. This is the
  Phase 9.1 acceptance gate.
"""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

import httpx
import pytest
import respx
import yaml

from audit.analyzer.semantic.base import AnalysisContext
from audit.analyzer.semantic.ollama_text import OllamaTextProvider
from audit.analyzer.semantic.registry import build_analyzers
from audit.analyzer.semantic.runner import analyze_page
from audit.db import repo

BASE = "http://ollama-mock.local"
MODEL = "qwen2.5:7b-instruct"

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "site" / "sc_2_4_4"


def _ollama_envelope(payload: dict[str, object]) -> dict[str, str]:
    return {"response": json.dumps(payload)}


# --------------------------------------------------------------------
# Mocked end-to-end (default — runs in CI)
# --------------------------------------------------------------------


def _seed_scan_page(conn: sqlite3.Connection) -> tuple[int, int]:
    cur = conn.execute(
        "INSERT INTO scans (seed_url, status, config_json) VALUES ('http://x/', 'completed', '{}')"
    )
    scan_id = int(cur.lastrowid or 0)
    page_id = repo.upsert_page(
        conn,
        scan_id=scan_id,
        url_normalized="http://x/page",
        status_code=200,
        title="page",
        render_mode="static",
        html_hash="0" * 64,
    )
    return scan_id, page_id


@pytest.mark.asyncio
@respx.mock
async def test_end_to_end_one_criterion_one_finding(
    tmp_db: sqlite3.Connection,
) -> None:
    """Full happy path: registry → analyzer → runner → persistence."""
    respx.post(f"{BASE}/api/generate").mock(
        return_value=httpx.Response(
            200,
            json=_ollama_envelope(
                {
                    "violations": [
                        {
                            "index": 0,
                            "reason": "'click here' provides no purpose context.",
                            "recommendation": "Use the destination noun.",
                            "confidence": "high",
                        }
                    ]
                }
            ),
        )
    )
    scan_id, page_id = _seed_scan_page(tmp_db)

    async with httpx.AsyncClient() as client:
        provider = OllamaTextProvider(client, model=MODEL, base_url=BASE)
        analyzers = build_analyzers(["2.4.4"], provider)
        ctx = AnalysisContext(
            body=b'<p>Read: <a href="/foo">click here</a></p>',
            page_url="http://x/page",
        )
        findings = await analyze_page(ctx, analyzers)

    # Persist exactly like the orchestrator does.
    for f in findings:
        repo.upsert_semantic_finding(
            tmp_db,
            page_id=page_id,
            scan_id=scan_id,
            **f.to_repo_kwargs(),
        )

    # One row with the right shape ends up in page_a11y_findings.
    rows = tmp_db.execute(
        "SELECT pipeline, criterion_sc, impact, help, wcag_level "
        "FROM page_a11y_findings WHERE scan_id = ?",
        (scan_id,),
    ).fetchall()
    assert len(rows) == 1
    assert rows[0]["pipeline"] == "semantic"
    assert rows[0]["criterion_sc"] == "2.4.4"
    assert rows[0]["wcag_level"] == "A"
    assert rows[0]["impact"] == "serious"  # high confidence
    assert "click here" in rows[0]["help"]


@pytest.mark.asyncio
@respx.mock
async def test_end_to_end_re_run_is_idempotent(
    tmp_db: sqlite3.Connection,
) -> None:
    """Running the same pipeline twice on the same page produces ONE row."""
    respx.post(f"{BASE}/api/generate").mock(
        return_value=httpx.Response(
            200,
            json=_ollama_envelope(
                {"violations": [{"index": 0, "reason": "x", "confidence": "high"}]}
            ),
        )
    )
    scan_id, page_id = _seed_scan_page(tmp_db)

    async with httpx.AsyncClient() as client:
        provider = OllamaTextProvider(client, model=MODEL, base_url=BASE)
        analyzers = build_analyzers(["2.4.4"], provider)
        body = b'<a href="/foo">click here</a>'
        ctx = AnalysisContext(body=body, page_url="http://x/page")

        for _ in range(2):  # run twice
            findings = await analyze_page(ctx, analyzers)
            for f in findings:
                repo.upsert_semantic_finding(
                    tmp_db,
                    page_id=page_id,
                    scan_id=scan_id,
                    **f.to_repo_kwargs(),
                )

    count = tmp_db.execute(
        "SELECT COUNT(*) AS n FROM page_a11y_findings "
        "WHERE pipeline = 'semantic' AND criterion_sc = '2.4.4'",
    ).fetchone()["n"]
    assert count == 1  # second run upserted onto the same row


@pytest.mark.asyncio
@respx.mock
async def test_end_to_end_human_status_survives_rerun(
    tmp_db: sqlite3.Connection,
) -> None:
    """A finding triaged ``accepted_risk`` doesn't revert to ``new``
    on the next scan, even though the analyzer rediscovered it."""
    respx.post(f"{BASE}/api/generate").mock(
        return_value=httpx.Response(
            200,
            json=_ollama_envelope(
                {"violations": [{"index": 0, "reason": "x", "confidence": "high"}]}
            ),
        )
    )
    scan_id, page_id = _seed_scan_page(tmp_db)

    async with httpx.AsyncClient() as client:
        provider = OllamaTextProvider(client, model=MODEL, base_url=BASE)
        analyzers = build_analyzers(["2.4.4"], provider)
        ctx = AnalysisContext(
            body=b'<a href="/foo">click here</a>',
            page_url="http://x/page",
        )
        # First run, triage the finding.
        findings = await analyze_page(ctx, analyzers)
        for f in findings:
            repo.upsert_semantic_finding(
                tmp_db, page_id=page_id, scan_id=scan_id, **f.to_repo_kwargs()
            )
        tmp_db.execute(
            "UPDATE page_a11y_findings SET status = 'accepted_risk' WHERE pipeline = 'semantic'"
        )

        # Second run — analyzer rediscovers, upsert preserves status.
        findings = await analyze_page(ctx, analyzers)
        for f in findings:
            repo.upsert_semantic_finding(
                tmp_db, page_id=page_id, scan_id=scan_id, **f.to_repo_kwargs()
            )

    status = tmp_db.execute(
        "SELECT status FROM page_a11y_findings WHERE pipeline = 'semantic'"
    ).fetchone()["status"]
    assert status == "accepted_risk"


# --------------------------------------------------------------------
# Live calibration (gated)
# --------------------------------------------------------------------


@pytest.mark.skipif(
    os.environ.get("AUDIT_OLLAMA_LIVE") != "1",
    reason="set AUDIT_OLLAMA_LIVE=1 to exercise a real Ollama daemon",
)
@pytest.mark.asyncio
async def test_live_calibration_against_labeled_fixtures() -> None:
    """Precision/recall measurement against the hand-labeled fixture set.

    This is the Phase 9.1 acceptance gate. Per the plan, we expect:
      * precision >= 85%   (few false positives)
      * recall >= 75%      (most real violations caught)

    The fixture set is small (~16 labeled link instances across 7
    pages); these thresholds are calibration targets, not statistical
    proofs. Phase 9.4 expands the labeled set to 50+ examples per
    criterion.

    Run with:
      AUDIT_OLLAMA_LIVE=1 uv run pytest tests/integration/test_semantic_pipeline.py -k live
    """
    labels = yaml.safe_load((FIXTURE_DIR / "labels.yaml").read_text())

    true_pos = 0
    false_pos = 0
    false_neg = 0
    per_file: list[tuple[str, int, int, int]] = []

    base_url = os.environ.get("AUDIT_OLLAMA_BASE", "http://localhost:11434")
    async with httpx.AsyncClient() as client:
        provider = OllamaTextProvider(client, model=MODEL, base_url=base_url, max_attempts=2)
        analyzers = build_analyzers(["2.4.4"], provider)

        for name, spec in labels.items():
            body = (FIXTURE_DIR / spec["file"]).read_bytes()
            expected = set(spec["violations"])
            ctx = AnalysisContext(body=body, page_url=f"file://{spec['file']}")
            findings = await analyze_page(ctx, analyzers)
            # Map findings back to indices via target_selector ord=N.
            detected: set[int] = set()
            for f in findings:
                # selector format from extractor: "a[ord=N]" / "a#id" /
                # "a.class[ord=N]"; pull the ord= value when present.
                import re

                m = re.search(r"ord=(\d+)", f.target_selector)
                if m:
                    detected.add(int(m.group(1)))
            tp = len(expected & detected)
            fp = len(detected - expected)
            fn = len(expected - detected)
            true_pos += tp
            false_pos += fp
            false_neg += fn
            per_file.append((name, tp, fp, fn))

    precision = true_pos / max(1, true_pos + false_pos)
    recall = true_pos / max(1, true_pos + false_neg)

    # Print per-file breakdown for debugging when this fails.
    print("\nLive calibration breakdown (TP / FP / FN per fixture):")
    for name, tp, fp, fn in per_file:
        print(f"  {name:<32}  TP={tp}  FP={fp}  FN={fn}")
    print(f"\nOverall  precision={precision:.2%}  recall={recall:.2%}")

    # Phase 9.1 acceptance targets per PLAN.md.
    assert precision >= 0.85, (
        f"precision {precision:.2%} below 85% target — too many false positives. Tune the prompt."
    )
    assert recall >= 0.75, (
        f"recall {recall:.2%} below 75% target — "
        f"too many false negatives. Tune the prompt or extractor."
    )
