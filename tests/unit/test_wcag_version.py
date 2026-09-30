"""Choosing WCAG 2.1 or 2.2 per scan.

New scans default to 2.1, the current U-M standard. A scan stored before the
setting existed has no ``wcag_version`` in its config and ran the 2.2 rule
set, so it must keep reading, resuming, and reporting as 2.2.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field

import httpx
import pytest

from audit.analyzer.alfa import AlfaAvailability, AlfaResult
from audit.analyzer.axe import tags_for_level
from audit.crawler import orchestrator
from audit.crawler.orchestrator import CrawlConfig, _ensure_scan, config_json_for_scan, run_crawl
from audit.db import queue, repo
from audit.wcag_version import stored_wcag_version
from audit.web import issues as issues_mod

SEED = "https://wcag.example.test/"


# --------------------------------------------------------------------------
# axe tag packs
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("level", "version", "expected"),
    [
        ("A", "2.1", ["best-practice", "wcag21a", "wcag2a"]),
        ("AA", "2.1", ["best-practice", "wcag21a", "wcag21aa", "wcag2a", "wcag2aa"]),
        (
            "AAA",
            "2.1",
            ["best-practice", "wcag21a", "wcag21aa", "wcag2a", "wcag2aa", "wcag2aaa"],
        ),
        ("A", "2.2", ["best-practice", "wcag21a", "wcag22a", "wcag2a"]),
        (
            "AA",
            "2.2",
            [
                "best-practice",
                "wcag21a",
                "wcag21aa",
                "wcag22a",
                "wcag22aa",
                "wcag2a",
                "wcag2aa",
            ],
        ),
        (
            "AAA",
            "2.2",
            [
                "best-practice",
                "wcag21a",
                "wcag21aa",
                "wcag22a",
                "wcag22aa",
                "wcag2a",
                "wcag2aa",
                "wcag2aaa",
            ],
        ),
    ],
)
def test_tags_for_level_follow_the_version(level: str, version: str, expected: list[str]) -> None:
    assert tags_for_level(level, version) == expected  # type: ignore[arg-type]


def test_wcag21_tag_packs_never_include_wcag22_rules() -> None:
    for level in ("A", "AA", "AAA"):
        assert not [tag for tag in tags_for_level(level, "2.1") if tag.startswith("wcag22")]  # type: ignore[arg-type]


def test_tags_for_level_without_a_version_keeps_the_22_pack() -> None:
    """An unthreaded caller runs what every caller ran before the setting."""
    assert tags_for_level("AA") == tags_for_level("AA", "2.2")


# --------------------------------------------------------------------------
# Stored config: default, round trip, and "missing means 2.2"
# --------------------------------------------------------------------------


def test_new_config_defaults_to_21_and_round_trips() -> None:
    default = json.loads(config_json_for_scan(CrawlConfig(seed_url=SEED)))
    assert default["wcag_version"] == "2.1"
    assert stored_wcag_version(default) == "2.1"
    chosen = config_json_for_scan(CrawlConfig(seed_url=SEED, wcag_version="2.2"))
    assert json.loads(chosen)["wcag_version"] == "2.2"
    assert stored_wcag_version(chosen) == "2.2"


@pytest.mark.parametrize(
    "stored",
    ['{"axe_level": "AA"}', "{}", "", None, "not json", '{"wcag_version": "3.0"}', "[]"],
)
def test_a_config_without_a_usable_version_reads_as_22(stored: str | None) -> None:
    assert stored_wcag_version(stored) == "2.2"


def test_crawl_config_rejects_an_unknown_version() -> None:
    with pytest.raises(ValueError, match="wcag_version"):
        CrawlConfig(seed_url=SEED, wcag_version="3.0")  # type: ignore[arg-type]


# --------------------------------------------------------------------------
# Resume: a scan keeps the version it started with
# --------------------------------------------------------------------------


def _interrupted_scan(conn: sqlite3.Connection, config_json: str) -> int:
    cur = conn.execute(
        "INSERT INTO scans (seed_url, status, config_json) VALUES (?, 'interrupted', ?)",
        (SEED, config_json),
    )
    scan_id = int(cur.lastrowid or 0)
    queue.enqueue(
        conn,
        "fetch",
        {"scan_id": scan_id, "url": SEED, "depth": 0},
        dedupe_key=f"{scan_id}:{SEED}",
    )
    return scan_id


def _stored_version(conn: sqlite3.Connection, scan_id: int) -> str:
    row = conn.execute("SELECT config_json FROM scans WHERE id = ?", (scan_id,)).fetchone()
    return str(json.loads(row["config_json"])["wcag_version"])


def test_resuming_an_old_scan_keeps_22(tmp_db: sqlite3.Connection) -> None:
    old = _interrupted_scan(tmp_db, '{"axe_level": "AA"}')
    assert _ensure_scan(tmp_db, SEED, CrawlConfig(seed_url=SEED)) == old
    assert _stored_version(tmp_db, old) == "2.2"


def test_resuming_a_21_scan_with_a_22_request_keeps_21(tmp_db: sqlite3.Connection) -> None:
    started = _interrupted_scan(tmp_db, '{"wcag_version": "2.1"}')
    config = CrawlConfig(seed_url=SEED, wcag_version="2.2")
    assert _ensure_scan(tmp_db, SEED, config) == started
    assert _stored_version(tmp_db, started) == "2.1"


def test_a_new_scan_row_records_the_requested_version(tmp_db: sqlite3.Connection) -> None:
    scan_id = _ensure_scan(tmp_db, SEED, CrawlConfig(seed_url=SEED, wcag_version="2.2"))
    assert _stored_version(tmp_db, scan_id) == "2.2"


def test_an_owned_old_row_keeps_22(tmp_db: sqlite3.Connection) -> None:
    cur = tmp_db.execute(
        "INSERT INTO scans (seed_url, status, config_json) VALUES (?, 'interrupted', '{}')",
        (SEED,),
    )
    scan_id = int(cur.lastrowid or 0)
    _ensure_scan(tmp_db, SEED, CrawlConfig(seed_url=SEED, scan_id=scan_id))
    assert _stored_version(tmp_db, scan_id) == "2.2"


@dataclass
class _RecordingAlfa:
    versions: list[str] = field(default_factory=list)

    async def run(self, url: str, *, level: str, version: str) -> AlfaResult:
        self.versions.append(version)
        return AlfaResult(
            url=url,
            status=200,
            findings=(),
            failed_total=0,
            cant_tell_total=0,
            truncated=False,
        )


def _site(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/robots.txt":
        return httpx.Response(404)
    return httpx.Response(
        200,
        headers={"content-type": "text/html; charset=utf-8"},
        text="<!doctype html><html lang=en><title>t</title><main>Hello</main></html>",
    )


def _static_alfa_config(**overrides: object) -> CrawlConfig:
    return CrawlConfig(
        seed_url=SEED,
        max_pages=1,
        rps=100.0,
        workers=1,
        js_enabled=False,
        js_eager=False,
        axe_enabled=False,
        alfa_enabled=True,
        ocr_enabled=False,
        vlm_enabled=False,
        semantic_enabled=False,
        keyboard_probe_enabled=False,
        responsive_checks_enabled=False,
        focus_checks_enabled=False,
        visual_checks_enabled=False,
        interaction_checks_enabled=False,
        synthesize_enabled=False,
        image_extraction_enabled=False,
        **overrides,  # type: ignore[arg-type]
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("existing_config", "requested", "expected"),
    [
        (None, "2.1", "2.1"),
        (None, "2.2", "2.2"),
        # An interrupted scan from before the setting resumes on 2.2 rules
        # even though a new request defaults to 2.1.
        ('{"axe_level": "AA"}', "2.1", "2.2"),
    ],
)
async def test_the_engines_run_the_scan_version(
    tmp_db: sqlite3.Connection,
    monkeypatch: pytest.MonkeyPatch,
    existing_config: str | None,
    requested: str,
    expected: str,
) -> None:
    monkeypatch.setattr(orchestrator, "alfa_availability", lambda: AlfaAvailability(True))
    if existing_config is not None:
        _interrupted_scan(tmp_db, existing_config)
    alfa = _RecordingAlfa()
    async with httpx.AsyncClient(transport=httpx.MockTransport(_site)) as client:
        summary = await run_crawl(
            tmp_db,
            _static_alfa_config(wcag_version=requested),
            http_client=client,
            alfa_analyzer=alfa,
        )
    assert alfa.versions and set(alfa.versions) == {expected}
    assert _stored_version(tmp_db, summary.scan_id) == expected


# --------------------------------------------------------------------------
# Issue projection: SC 2.4.11 is best practice under 2.1
# --------------------------------------------------------------------------


def _scan_with_focus_findings(conn: sqlite3.Connection, config_json: str) -> int:
    cur = conn.execute(
        "INSERT INTO scans (seed_url, status, page_count, finding_count, config_json) "
        "VALUES (?, 'completed', 1, 0, ?)",
        (SEED, config_json),
    )
    scan_id = int(cur.lastrowid or 0)
    page_id = repo.upsert_page(
        conn,
        scan_id=scan_id,
        url_normalized=SEED,
        status_code=200,
        title="Home",
        render_mode="js",
        html_hash="0" * 64,
    )
    for rule_id, sc, level in (
        ("focus-not-obscured", "2.4.11", "AA"),
        ("focus-order-positive-tabindex", "2.4.3", "A"),
    ):
        repo.upsert_focus_finding(
            conn,
            page_id=page_id,
            scan_id=scan_id,
            rule_id=rule_id,
            wcag_sc=sc,
            wcag_scs=sc,
            wcag_level=level,
            impact="serious",
            help=f"{rule_id} help",
            help_url="https://www.w3.org/WAI/WCAG22/Understanding/",
            target_selector=f"#{rule_id}",
            failure_summary="Observed.",
            html_snippet=f'<a id="{rule_id}">x</a>',
            target_hash=f"hash-{rule_id}",
            criterion_sc=sc,
        )
    return scan_id


def _focus_rows(conn: sqlite3.Connection, scan_id: int) -> dict[str, issues_mod.IssueRow]:
    return {
        row.wcag_sc or "": row
        for row in issues_mod.list_issues(conn, scan_id)
        if row.pipeline == "focus"
    }


def test_under_21_the_focus_obscured_issue_is_best_practice(tmp_db: sqlite3.Connection) -> None:
    scan_id = _scan_with_focus_findings(tmp_db, '{"wcag_version": "2.1"}')
    rows = _focus_rows(tmp_db, scan_id)
    obscured = rows["2.4.11"]
    assert obscured.conformance == "BP"
    assert obscured.wcag_sc == "2.4.11"
    assert "WCAG 2.2 criterion" in obscured.evidence_summary
    assert obscured.description and "not require it" in obscured.description
    # 2.4.3 exists in 2.1; the same pipeline's other rule is untouched.
    assert rows["2.4.3"].conformance == "A"
    assert "WCAG 2.2 criterion" not in rows["2.4.3"].evidence_summary

    detail = issues_mod.get_issue_detail(tmp_db, scan_id, obscured.issue_key)
    assert detail is not None
    assert detail.description and "WCAG 2.2 criterion" in detail.description
    # The stored finding is not rewritten; only the projection changes.
    stored = tmp_db.execute(
        "SELECT wcag_level FROM page_a11y_findings WHERE scan_id = ? AND wcag_sc = '2.4.11'",
        (scan_id,),
    ).fetchone()
    assert stored["wcag_level"] == "AA"


@pytest.mark.parametrize("config_json", ['{"wcag_version": "2.2"}', "{}"])
def test_under_22_or_an_old_scan_the_focus_issue_is_unchanged(
    tmp_db: sqlite3.Connection, config_json: str
) -> None:
    scan_id = _scan_with_focus_findings(tmp_db, config_json)
    obscured = _focus_rows(tmp_db, scan_id)["2.4.11"]
    assert obscured.conformance == "AA"
    assert "WCAG 2.2 criterion" not in obscured.evidence_summary
    assert "WCAG 2.2 criterion" not in (obscured.description or "")
    detail = issues_mod.get_issue_detail(tmp_db, scan_id, obscured.issue_key)
    assert detail is not None
    assert "WCAG 2.2 criterion" not in (detail.description or "")
