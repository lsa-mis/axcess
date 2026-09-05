"""Contracts for the optional Siteimprove Alfa scan engine.

These tests deliberately never launch Node/Chromium. The bridge has its own
bounded JSON protocol; testing its parser and persisted evidence shape keeps
the normal Python suite deterministic while a manual runner smoke test covers
the pinned Node packages.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
import tempfile
from types import SimpleNamespace

import pytest

from audit.analyzer import alfa
from audit.analyzer.alfa import AlfaAnalyzer, AlfaError, AlfaFinding, _parse_result
from audit.crawler.orchestrator import CrawlSummary, _persist_alfa
from audit.db import repo
from audit.exports.audit_report import build_audit_cards, render_audit_report
from audit.exports.collector import collect_scan
from audit.exports.jira_export import render_jira_csv
from audit.exports.markdown_report import render_markdown
from audit.web import a11y_queries, issues


class _FakeAlfaStdin:
    def __init__(self) -> None:
        self.content = bytearray()
        self.closed = False

    def write(self, content: bytes) -> None:
        self.content.extend(content)

    async def drain(self) -> None:
        return None

    def close(self) -> None:
        self.closed = True

    async def wait_closed(self) -> None:
        return None


class _FakeAlfaProcess:
    """Small process double that proves pipe limits terminate the child."""

    def __init__(
        self,
        *,
        stdout: bytes = b"",
        stderr: bytes = b"",
        returncode: int | None = 0,
        eof: bool = True,
    ) -> None:
        self.stdin = _FakeAlfaStdin()
        self.stdout = asyncio.StreamReader()
        self.stderr = asyncio.StreamReader()
        if stdout:
            self.stdout.feed_data(stdout)
        if stderr:
            self.stderr.feed_data(stderr)
        if eof:
            self.stdout.feed_eof()
            self.stderr.feed_eof()
        self.returncode = returncode
        self.killed = False
        self._finished = asyncio.Event()
        if returncode is not None:
            self._finished.set()

    async def wait(self) -> int:
        await self._finished.wait()
        assert self.returncode is not None
        return self.returncode

    def kill(self) -> None:
        self.killed = True
        self.returncode = -9
        self.stdout.feed_eof()
        self.stderr.feed_eof()
        self._finished.set()


def _stub_alfa_runner(monkeypatch: pytest.MonkeyPatch, process: _FakeAlfaProcess) -> None:
    async def create_process(*_args: object, **_kwargs: object) -> _FakeAlfaProcess:
        return process

    monkeypatch.setattr(alfa, "availability", lambda: alfa.AlfaAvailability(True))
    monkeypatch.setattr(alfa.asyncio, "create_subprocess_exec", create_process)


def _seed_scan_and_page(conn: sqlite3.Connection) -> tuple[int, int]:
    scan_id = int(
        conn.execute(
            "INSERT INTO scans (seed_url, status, config_json) VALUES (?, 'completed', ?)",
            ("https://example.test/", '{"alfa_enabled": true}'),
        ).lastrowid
    )
    page_id = int(
        conn.execute(
            "INSERT INTO pages (scan_id, url_normalized, status_code, render_mode) "
            "VALUES (?, ?, 200, 'js')",
            (scan_id, "https://example.test/"),
        ).lastrowid
    )
    return scan_id, page_id


def test_alfa_protocol_preserves_failed_and_cant_tell_evidence() -> None:
    payload = {
        "protocol_version": 1,
        "engine": "alfa",
        "url": "https://example.test/",
        "status": 200,
        "outcome_counts": {"failed": 1, "cantTell": 1},
        "findings": [
            {
                "rule_id": "sia-r2",
                "rule_uri": "https://alfa.siteimprove.com/rules/sia-r2",
                "outcome": "failed",
                "mode": "automatic",
                "wcag_sc": "1.1.1",
                "wcag_scs": ["1.1.1"],
                "wcag_level": "A",
                "help": "WCAG 1.1.1: Non-text Content",
                "failure_summary": "The image does not have an accessible name.",
                "target_hint": "<img src='logo.png'>",
                "evidence": '{"target":"img"}',
            },
            {
                "rule_id": "sia-r55",
                "rule_uri": "https://alfa.siteimprove.com/rules/sia-r55",
                "outcome": "cantTell",
                "mode": "semiAuto",
                "wcag_sc": "1.3.1",
                "wcag_scs": ["1.3.1"],
                "wcag_level": "A",
                "help": "WCAG 1.3.1: Info and Relationships",
                "failure_summary": "Expert answer required.",
                "target_hint": "<table>",
                "evidence": '{"question":"layout table?"}',
            },
        ],
    }

    result = _parse_result(json.dumps(payload).encode())

    assert result.failed_total == 1
    assert result.cant_tell_total == 1
    assert [finding.outcome for finding in result.findings] == ["failed", "cant_tell"]
    assert result.findings[1].impact is None


def test_alfa_protocol_rejects_unrecognized_outcomes() -> None:
    payload = {
        "protocol_version": 1,
        "engine": "alfa",
        "outcome_counts": {},
        "findings": [{"rule_id": "sia-r1", "outcome": "passed"}],
    }

    with pytest.raises(AlfaError, match="non-actionable"):
        _parse_result(json.dumps(payload).encode())


@pytest.mark.asyncio
async def test_protected_alfa_hides_runner_stderr_and_closes_its_input(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    process = _FakeAlfaProcess(stderr=b"target-controlled secret from stderr", returncode=2)
    _stub_alfa_runner(monkeypatch, process)

    analyzer = AlfaAnalyzer(user_agent="test-agent")
    with pytest.raises(AlfaError) as raised:
        await analyzer.run(
            "https://protected.example.test/account",
            level="AA",
            storage_state={"cookies": [{"name": "session", "value": "secret"}]},
            allowed_origins=("https://protected.example.test",),
            target_origins=("https://protected.example.test",),
            egress_proxy="http://127.0.0.1:9999",
        )

    assert str(raised.value) == "The protected Alfa engine could not complete this page."
    assert "secret" not in str(raised.value)
    assert process.stdin.closed


@pytest.mark.asyncio
async def test_alfa_runner_receives_only_bounded_runtime_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = {
        "protocol_version": 1,
        "engine": "alfa",
        "url": "https://example.test/",
        "status": 200,
        "outcome_counts": {"failed": 0, "cantTell": 0},
        "findings": [],
    }
    process = _FakeAlfaProcess(stdout=json.dumps(payload).encode())
    captured_env: dict[str, str] = {}

    async def create_process(*_args: object, **kwargs: object) -> _FakeAlfaProcess:
        captured_env.update(kwargs["env"])
        return process

    monkeypatch.setattr(alfa, "availability", lambda: alfa.AlfaAvailability(True))
    monkeypatch.setattr(alfa, "_node_executable", lambda: "/safe/node")
    monkeypatch.setattr(alfa.asyncio, "create_subprocess_exec", create_process)
    monkeypatch.setenv("APPLICATION_SECRET", "must-not-leak")

    await AlfaAnalyzer(user_agent="test-agent").run("https://example.test/", level="AA")

    assert captured_env["TEMP"] == tempfile.gettempdir()
    assert captured_env["TMP"] == tempfile.gettempdir()
    assert captured_env["TMPDIR"] == tempfile.gettempdir()
    assert "APPLICATION_SECRET" not in captured_env


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("stdout", "stderr"),
    [
        (b"x" * (alfa._MAX_STDOUT_BYTES + 1), b""),
        (b"", b"x" * (alfa._MAX_STDERR_BYTES + 1)),
    ],
)
async def test_alfa_runner_output_limits_kill_the_child(
    monkeypatch: pytest.MonkeyPatch,
    stdout: bytes,
    stderr: bytes,
) -> None:
    process = _FakeAlfaProcess(stdout=stdout, stderr=stderr, returncode=None)
    _stub_alfa_runner(monkeypatch, process)

    with pytest.raises(AlfaError, match="more output"):
        await AlfaAnalyzer(user_agent="test-agent").run("https://example.test/", level="AA")

    assert process.killed


@pytest.mark.asyncio
async def test_alfa_runner_timeout_kills_and_drains_the_child(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    process = _FakeAlfaProcess(returncode=None, eof=False)
    _stub_alfa_runner(monkeypatch, process)

    with pytest.raises(AlfaError, match="timed out"):
        await AlfaAnalyzer(user_agent="test-agent", timeout_s=0.01).run(
            "https://example.test/", level="AA"
        )

    assert process.killed


def test_alfa_findings_are_source_separated_and_keep_outcome(tmp_db: sqlite3.Connection) -> None:
    scan_id, page_id = _seed_scan_and_page(tmp_db)
    repo.upsert_alfa_finding(
        tmp_db,
        page_id=page_id,
        scan_id=scan_id,
        rule_id="sia-r2",
        wcag_sc="1.1.1",
        wcag_scs="1.1.1",
        wcag_level="A",
        help="WCAG 1.1.1: Non-text Content",
        help_url="https://alfa.siteimprove.com/rules/sia-r2",
        target_selector="<img src='logo.png'>",
        failure_summary="The image does not have an accessible name.",
        html_snippet="<img src='logo.png'>",
        target_hash="alfa-img",
        engine_outcome="cant_tell",
        engine_evidence_json='{"question":"decorative?"}',
    )
    # Same rule name in another engine is intentionally a separate group.
    repo.upsert_axe_violation(
        tmp_db,
        page_id=page_id,
        scan_id=scan_id,
        rule_id="sia-r2",
        wcag_sc="1.1.1",
        wcag_scs="1.1.1",
        wcag_level="A",
        impact="serious",
        help="Unrelated axe evidence",
        help_url="https://deque.example/rule",
        target_selector="img",
        failure_summary="axe evidence",
        html_snippet="<img>",
        target_hash="axe-img",
    )
    repo.increment_scan_alfa_counters(tmp_db, scan_id=scan_id, pages_delta=1, cant_tell_delta=1)

    stored = tmp_db.execute(
        "SELECT pipeline, engine_outcome, engine_evidence_json FROM page_a11y_findings "
        "WHERE target_hash = 'alfa-img'"
    ).fetchone()
    assert tuple(stored) == ("alfa", "cant_tell", '{"question":"decorative?"}')
    scan = tmp_db.execute(
        "SELECT alfa_pages_scanned, alfa_failed_total, alfa_cant_tell_total "
        "FROM scans WHERE id = ?",
        (scan_id,),
    ).fetchone()
    assert tuple(scan) == (1, 0, 1)

    rows = issues.list_issues(tmp_db, scan_id)
    assert {(row.pipeline, row.issue_key) for row in rows} == {
        ("alfa", "alfa:sia-r2:cant_tell"),
        ("axe", "axe:sia-r2"),
    }
    alfa_row = next(row for row in rows if row.pipeline == "alfa")
    assert alfa_row.title == "Non-text Content, expert decision needed (Alfa sia-r2)"
    assert alfa_row.description is not None and "cantTell" in alfa_row.description
    assert alfa_row.why_matters is not None
    assert "not a failure" in alfa_row.why_matters
    assert "human decision" in alfa_row.why_matters
    # Pre-subgroup links remain valid when one Alfa outcome is unambiguous.
    alfa_detail = issues.get_issue_detail(tmp_db, scan_id, "alfa:sia-r2")
    assert alfa_detail is not None
    assert alfa_detail.pages[0].occurrence_count == 1
    assert alfa_detail.verify_manual is not None


def test_mixed_alfa_rule_outcomes_are_isolated_end_to_end(
    tmp_db: sqlite3.Connection,
) -> None:
    """cantTell can never inherit a failed outcome's lane, ids, pages, or export card."""

    scan_id, failed_page_id = _seed_scan_and_page(tmp_db)
    cant_tell_page_id = int(
        tmp_db.execute(
            "INSERT INTO pages (scan_id, url_normalized, status_code, render_mode) "
            "VALUES (?, ?, 200, 'js')",
            (scan_id, "https://example.test/review"),
        ).lastrowid
    )
    common = {
        "scan_id": scan_id,
        "rule_id": "sia-r-mixed",
        "wcag_sc": "1.1.1",
        "wcag_scs": "1.1.1",
        "wcag_level": "A",
        "help": "WCAG 1.1.1: Non-text Content",
        "help_url": "https://alfa.siteimprove.com/rules/sia-r-mixed",
        "html_snippet": "<img>",
        "engine_evidence_json": "{}",
    }
    failed_id = repo.upsert_alfa_finding(
        tmp_db,
        page_id=failed_page_id,
        target_selector="img.failed",
        failure_summary="Alternative is missing.",
        target_hash="mixed-failed",
        engine_outcome="failed",
        **common,
    )
    cant_tell_id = repo.upsert_alfa_finding(
        tmp_db,
        page_id=cant_tell_page_id,
        target_selector="img.ambiguous",
        failure_summary="Expert must determine whether this image is decorative.",
        target_hash="mixed-cant-tell",
        engine_outcome="cant_tell",
        **common,
    )
    tmp_db.execute(
        "UPDATE page_a11y_findings SET status = 'reviewing' WHERE id = ?",
        (cant_tell_id,),
    )

    groups = [
        group
        for group in a11y_queries.grouped_by_rule(tmp_db, scan_id)
        if group["pipeline"] == "alfa" and group["rule_id"] == "sia-r-mixed"
    ]
    assert [group["outcome_group"] for group in groups] == ["failed", "cant_tell"]
    failed_group, cant_tell_group = groups
    assert failed_group["engine_outcomes"] == {"failed": 1, "cant_tell": 0}
    assert cant_tell_group["engine_outcomes"] == {"failed": 0, "cant_tell": 1}
    assert [finding["id"] for finding in failed_group["findings"]] == [failed_id]
    assert [finding["id"] for finding in cant_tell_group["findings"]] == [cant_tell_id]

    alfa_rows = {
        row.issue_key: row for row in issues.list_issues(tmp_db, scan_id) if row.pipeline == "alfa"
    }
    assert set(alfa_rows) == {
        "alfa:sia-r-mixed:failed",
        "alfa:sia-r-mixed:cant_tell",
    }
    failed_row = alfa_rows["alfa:sia-r-mixed:failed"]
    review_row = alfa_rows["alfa:sia-r-mixed:cant_tell"]
    assert (failed_row.review_lane, failed_row.evidence_confidence) == (
        "likely_barrier",
        "high",
    )
    assert failed_row.high_confidence_occurrence_count == 1
    assert failed_row.finding_ids == (failed_id,)
    assert (review_row.review_lane, review_row.evidence_confidence) == (
        "expert_review",
        "medium",
    )
    assert review_row.high_confidence_occurrence_count == 0
    assert review_row.finding_ids == (cant_tell_id,)

    failed_detail = issues.get_issue_detail(tmp_db, scan_id, "alfa:sia-r-mixed:failed")
    review_detail = issues.get_issue_detail(tmp_db, scan_id, "alfa:sia-r-mixed:cant_tell")
    assert failed_detail is not None and review_detail is not None
    assert [page.page_url for page in failed_detail.pages] == ["https://example.test/"]
    assert [page.page_url for page in review_detail.pages] == ["https://example.test/review"]
    assert failed_detail.pages[0].status_summary == {"new": 1}
    assert review_detail.pages[0].status_summary == {"reviewing": 1}
    # A legacy aggregate key is unsafe and intentionally ambiguous here.
    assert issues.get_issue_detail(tmp_db, scan_id, "alfa:sia-r-mixed") is None

    scan = collect_scan(tmp_db, scan_id, ui_base_url="http://127.0.0.1:8765")
    cards, _dropped, review_leads = build_audit_cards(tmp_db, scan)
    assert len([card for card in cards if card.pipeline == "alfa"]) == 1
    assert len([row for row in review_leads if row.pipeline == "alfa"]) == 1
    assert next(row for row in review_leads if row.pipeline == "alfa").finding_ids == (
        cant_tell_id,
    )


def test_alfa_only_exports_keep_review_outcomes_distinct(tmp_db: sqlite3.Connection) -> None:
    scan_id, page_id = _seed_scan_and_page(tmp_db)
    repo.upsert_alfa_finding(
        tmp_db,
        page_id=page_id,
        scan_id=scan_id,
        rule_id="sia-r55",
        wcag_sc="1.3.1",
        wcag_scs="1.3.1",
        wcag_level="A",
        help="WCAG 1.3.1: Info and Relationships",
        help_url="https://alfa.siteimprove.com/rules/sia-r55",
        target_selector="table",
        failure_summary="Expert answer required.",
        html_snippet="<table>",
        target_hash="alfa-table",
        engine_outcome="cant_tell",
        engine_evidence_json='{"question":"layout table?"}',
    )
    repo.increment_scan_alfa_counters(tmp_db, scan_id=scan_id, pages_delta=1, cant_tell_delta=1)

    scan = collect_scan(tmp_db, scan_id, ui_base_url="http://127.0.0.1:8765")
    markdown = render_markdown(scan)
    assert "## WCAG DOM-engine findings" in markdown
    assert "**Source:** Siteimprove Alfa" in markdown
    assert "Needs expert review (Alfa cantTell)" in markdown

    structured_report = render_audit_report(scan, conn=tmp_db)
    assert "Alfa ACT evidence is a review lead" in structured_report

    jira = render_jira_csv(scan)
    assert "alfa-sia-r55" in jira
    assert "not a conformance failure" in jira


def test_alfa_counters_keep_full_runner_outcome_counts_when_evidence_is_capped(
    tmp_db: sqlite3.Connection,
) -> None:
    scan_id, page_id = _seed_scan_and_page(tmp_db)
    finding = AlfaFinding(
        rule_id="sia-r2",
        rule_uri="https://alfa.siteimprove.com/rules/sia-r2",
        outcome="failed",
        mode="automatic",
        wcag_sc="1.1.1",
        wcag_scs="1.1.1",
        wcag_level="A",
        help="WCAG 1.1.1: Non-text Content",
        failure_summary="The image does not have an accessible name.",
        target_hint="img",
        evidence_json="{}",
    )
    summary = CrawlSummary(scan_id=scan_id, seed_url="https://example.test/")
    ctx = SimpleNamespace(conn=tmp_db, scan_id=scan_id, summary=summary)

    _persist_alfa(
        ctx,
        page_id=page_id,
        findings=(finding,),
        failed_total=201,
        cant_tell_total=3,
    )

    counters = tmp_db.execute(
        "SELECT alfa_pages_scanned, alfa_failed_total, alfa_cant_tell_total "
        "FROM scans WHERE id = ?",
        (scan_id,),
    ).fetchone()
    assert tuple(counters) == (1, 201, 3)
    assert summary.alfa_failed_total == 201
    assert summary.alfa_cant_tell_total == 3
