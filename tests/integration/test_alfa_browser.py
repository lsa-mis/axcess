"""Exercise pinned Alfa and bundled axe against network-blocked browser fixtures."""

from __future__ import annotations

import asyncio
import json
import os
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest

from audit.analyzer.alfa import _parse_result, availability, chromium_executable_path
from audit.crawler.orchestrator import CrawlSummary, _persist_alfa

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_alfa_and_axe_browser_evidence(tmp_db: sqlite3.Connection) -> None:
    if not availability().available:
        pytest.skip("Pinned local Alfa dependencies are not installed")
    executable = await chromium_executable_path()
    if not executable or not Path(executable).exists():
        pytest.skip("An installed Chromium is required; no browser is downloaded")
    runner = Path(__file__).resolve().parents[2] / "src/audit/alfa_runner/fixture.mjs"
    process = await asyncio.create_subprocess_exec(
        "node",
        str(runner),
        env={"PATH": os.environ.get("PATH", ""), "ALFA_CHROMIUM_PATH": executable},
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), 90)
    except BaseException:
        if process.returncode is None:
            process.kill()
        await process.wait()
        raise
    assert process.returncode == 0, stderr.decode()[-2000:]
    fixtures = json.loads(stdout)
    assert fixtures["pass"]["outcome_counts"]["failed"] == 0
    assert fixtures["pass"]["findings"] == []
    assert fixtures["pass"]["axe"]["violations"] == []
    failed = fixtures["fail"]
    assert {f["rule_id"] for f in failed["findings"]} == {"sia-r69", "sia-r12"}
    assert {f["id"] for f in failed["axe"]["violations"]} == {"color-contrast", "button-name"}
    gradient = fixtures["gradient"]
    assert gradient["outcome_counts"]["cantTell"] == 1
    assert gradient["outcome_counts"]["failed"] == 0
    assert "background-size" in gradient["findings"][0]["failure_summary"]
    assert gradient["axe"]["incomplete"] == [{"id": "color-contrast", "count": 1}]
    for name in ("repeated", "shadow"):
        findings = fixtures[name]["findings"]
        assert len(findings) == 2
        assert len({f["target_identity"] for f in findings}) == 2
        assert all(json.loads(f["target_hint"])["data"] == "Same text" for f in findings)
    assert all("shadow-root()" in f["target_hint"] for f in fixtures["shadow"]["findings"])
    capped = fixtures["cap"]
    assert len(capped["findings"]) == 200
    assert capped["findings"][0]["outcome"] == "failed"
    assert capped["outcome_counts"]["failed"] == 1
    assert capped["outcome_counts"]["cantTell"] == 205
    assert capped["findings_truncated"] is True
    assert json.loads(fixtures["large"])["truncated"] is True
    for name in ("pass", "fail", "gradient", "repeated", "shadow", "cap"):
        for finding in fixtures[name]["findings"]:
            assert isinstance(json.loads(finding["evidence"]), dict)
            assert len(finding["evidence"].encode("utf-8")) <= 4000
    for result in fixtures["bounds"]:
        assert len(result.encode("utf-8")) <= 4000
        assert json.loads(result)["truncated"] is True
    # Persist the actual repeated-text results twice: separate locations survive,
    # and evaluating the same locations again deduplicates.
    scan_id = int(
        tmp_db.execute(
            "INSERT INTO scans (seed_url,status,config_json) VALUES ('https://example.test/','completed','{}')"
        ).lastrowid
    )
    page_id = int(
        tmp_db.execute(
            "INSERT INTO pages (scan_id,url_normalized,status_code,render_mode) VALUES (?, 'https://example.test/',200,'js')",
            (scan_id,),
        ).lastrowid
    )
    result = _parse_result(
        json.dumps(
            {
                "protocol_version": 1,
                "engine": "alfa",
                "url": "https://example.test/",
                "status": 200,
                **fixtures["repeated"],
            }
        ).encode()
    )
    summary = CrawlSummary(scan_id=scan_id, seed_url="https://example.test/")
    context = SimpleNamespace(conn=tmp_db, scan_id=scan_id, summary=summary)
    for _ in range(2):
        _persist_alfa(
            context,
            page_id=page_id,
            findings=result.findings,
            failed_total=result.failed_total,
            cant_tell_total=result.cant_tell_total,
        )
    assert (
        tmp_db.execute(
            "SELECT COUNT(*) FROM page_a11y_findings WHERE scan_id=?", (scan_id,)
        ).fetchone()[0]
        == 2
    )
