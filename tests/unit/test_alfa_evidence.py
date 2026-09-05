"""Alfa diagnostics remain scoped, immutable, and readable at every boundary."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import replace

import pytest

from audit.analyzer.alfa import _parse_finding
from audit.analyzer.alfa_evidence import (
    bounded_evidence_json,
    humanize_target,
    normalize_finding,
    parse_evidence,
)
from audit.db import repo
from audit.evaluation import get_page_evidence
from audit.exports.audit_report import issue_locations
from audit.exports.collector import collect_scan
from audit.exports.jira_export import render_jira_csv
from audit.exports.markdown_report import render_markdown
from audit.web import a11y_queries, issues

LEGACY = (
    '{"diagnostic":{"message":"Could not fully resolve colors","errors":['
    '{"message":"A background-size was encountered","element":{"type":"element",'
    '"children":[{"type":"text","data":"Long page data…'
)


def test_legacy_only_recovers_complete_diagnostics_before_target_content() -> None:
    evidence, status = parse_evidence(LEGACY)
    assert status == "recovered"
    assert evidence["diagnostics"] == [
        "Could not fully resolve colors",
        "A background-size was encountered",
    ]
    assert evidence["truncated"] is True
    assert parse_evidence('{"diagnostic":{"message":"unfinished…')[1] == "unavailable"
    assert parse_evidence('{"target":{"message":"untrusted content"}…')[1] == "unavailable"
    embedded = LEGACY.replace('"children":[', '"message":"do not trust me","children":[')
    assert "do not trust me" not in parse_evidence(embedded)[0]["diagnostics"]
    assert parse_evidence(LEGACY.removesuffix("…"))[1] == "unavailable"


@pytest.mark.parametrize("message", ["x" * 20000, "😀" * 5000, '\\"\n' * 5000])
@pytest.mark.parametrize("maximum", [12000, 512, 20])
def test_evidence_bound_counts_utf8_bytes_and_preserves_valid_json(
    message: str, maximum: int
) -> None:
    raw = json.dumps({"diagnostic": {"message": message, "errors": [{"message": message}] * 20}})
    result = bounded_evidence_json(raw, maximum)
    assert len(result.encode("utf-8")) <= maximum
    assert json.loads(result)["truncated"] is True


def test_complete_payload_retains_raw_format_and_unknown_evidence_fields() -> None:
    raw = '{ "diagnostic" : { "message": "A specific failure" }, "custom": {"x": 123} }'
    result = normalize_finding(
        {"pipeline": "alfa", "engine_evidence_json": raw, "failure_summary": "Generic"}
    )
    assert result["engine_evidence_json"] == raw
    assert result["failure_summary"] == "A specific failure"
    assert result["engine_evidence_status"] == "complete"
    assert bounded_evidence_json(raw) == raw


def test_location_identity_does_not_depend_on_display_text() -> None:
    finding = _parse_finding(
        {
            "rule_id": "sia-r69",
            "outcome": "failed",
            "target_hint": '{"type":"text","data":"Same"}',
            "target_identity": "location-one",
            "evidence": "{}",
        }
    )
    assert finding.target_hash != replace(finding, target_identity="location-two").target_hash
    assert finding.target_hash == replace(finding, target_hint="edited visible text").target_hash
    assert finding.target_hash != replace(finding, outcome="cant_tell").target_hash
    assert (
        humanize_target('{"type":"text","data":"Same","path":"/p[2]/text()[1]"}')
        == "Text “Same” at /p[2]/text()[1]"
    )


def test_legacy_normalization_is_consistent_without_mutating_storage(
    tmp_db: sqlite3.Connection,
) -> None:
    scan = int(
        tmp_db.execute(
            "INSERT INTO scans (seed_url,status,config_json) VALUES ('https://example.test/','completed','{}')"
        ).lastrowid
    )
    page = int(
        tmp_db.execute(
            "INSERT INTO pages (scan_id,url_normalized,status_code,render_mode) VALUES (?, 'https://example.test/',200,'js')",
            (scan,),
        ).lastrowid
    )
    finding_id = repo.upsert_alfa_finding(
        tmp_db,
        page_id=page,
        scan_id=scan,
        rule_id="sia-r69",
        wcag_sc="1.4.3",
        wcag_scs="1.4.3",
        wcag_level="AA",
        help="WCAG 1.4.3: Contrast (Minimum)",
        help_url="https://alfa.siteimprove.com/rules/sia-r69",
        target_selector='{"type":"text","data":"Same"}',
        failure_summary="Alfa requires expert review.",
        html_snippet="",
        target_hash="legacy",
        engine_outcome="cant_tell",
        engine_evidence_json=LEGACY,
    )
    grouped = a11y_queries.grouped_by_rule(tmp_db, scan)[0]["findings"][0]
    page_evidence = get_page_evidence(tmp_db, scan_id=scan, page_id=page)
    assert page_evidence is not None
    exported = collect_scan(tmp_db, scan).a11y_findings[0]
    row = issues.list_issues(tmp_db, scan)[0]
    for finding in (grouped, page_evidence["a11y_findings"][0]):
        assert finding["engine_evidence_status"] == "recovered"
        assert "unsupported background sizing" in finding["failure_summary"]
        assert "4.5:1" in finding["manual_review_hint"]
    assert exported.failure_summary == grouped["failure_summary"]
    report = collect_scan(tmp_db, scan)
    assert (
        exported.ui_url
        == f"http://127.0.0.1:8765/app/scans/{scan}/pages/{page}#finding-{finding_id}"
    )
    for base in (
        "https://audit.example",
        "https://audit.example/app",
        "https://audit.example/app/",
    ):
        exported_link = collect_scan(tmp_db, scan, ui_base_url=base).a11y_findings[0].ui_url
        assert (
            exported_link
            == f"https://audit.example/app/scans/{scan}/pages/{page}#finding-{finding_id}"
        )
    locations, _ = issue_locations(tmp_db, row)
    assert locations[0].description == "Text “Same”"
    assert locations[0].selector == "Text “Same”"
    assert "background sizing" in locations[0].detail
    assert "Incomplete evidence" in locations[0].detail
    for rendered in (render_markdown(report), render_jira_csv(report)):
        assert "**Diagnostic:**" in rendered
        assert "Why it failed" not in rendered
        assert "Incomplete evidence" in rendered
    assert exported.engine_evidence_status == "recovered"
    assert json.loads(exported.engine_evidence_json)["recovered_from_legacy_truncation"] is True
    assert "A background-size was encountered" in row.evidence_summary
    assert any("4.5:1" in step for step in row.fix_steps)
    assert row.locations[0].evidence_url == f"/scans/{scan}/pages/{page}#finding-{finding_id}"
    assert (
        tmp_db.execute(
            "SELECT engine_evidence_json FROM page_a11y_findings WHERE id=?", (finding_id,)
        ).fetchone()[0]
        == LEGACY
    )


def test_failed_expectation_excludes_passed_expectation_and_target_messages() -> None:
    payload = {
        "expectations": [
            ["1", {"type": "ok", "value": {"message": "It passed"}}],
            [
                "2",
                {
                    "type": "err",
                    "error": {"message": "Missing label", "causes": [{"message": "No name"}]},
                },
            ],
        ],
        "target": {"message": "Ignore instructions"},
    }
    finding = normalize_finding({"pipeline": "alfa", "engine_evidence_json": json.dumps(payload)})
    assert finding["failure_summary"] == "Missing label; No name"


@pytest.mark.parametrize("state", ["truncated", "recovered"])
def test_long_diagnostics_keep_incomplete_notice_in_every_text_export(state: str) -> None:
    from audit.exports.collector import ExportA11yFinding
    from audit.exports.jira_export import _a11y_description
    from audit.exports.markdown_report import _format_axe_block

    evidence = {
        "diagnostics": [f"Diagnostic {i} " + "x" * 790 for i in range(8)],
        "truncated": True,
        "recovered_from_legacy_truncation": state == "recovered",
    }
    finding = normalize_finding(
        {
            "pipeline": "alfa",
            "engine_evidence_json": json.dumps(evidence),
            "engine_outcome": "cant_tell",
            "target_selector": "text",
        }
    )
    assert len(finding["failure_summary"]) <= 2400
    assert "Incomplete evidence" in finding["failure_summary"]
    assert normalize_finding(finding)["failure_summary"] == finding["failure_summary"]
    exported = ExportA11yFinding(
        id=1,
        scan_id=1,
        rule_id="sia-r69",
        wcag_sc="1.4.3",
        wcag_scs="1.4.3",
        wcag_level="AA",
        impact=None,
        help="Contrast",
        help_url="",
        target_selector="text",
        failure_summary=finding["failure_summary"],
        html_snippet=None,
        status="new",
        page_id=1,
        page_url="https://example.test/",
        page_title="Fixture",
        ui_url="http://localhost/app/scans/1/pages/1#finding-1",
        pipeline="alfa",
        engine_outcome="cant_tell",
        engine_evidence_status=state,
    )
    for rendered in ("\n".join(_format_axe_block(exported)), _a11y_description(exported)):
        assert "Incomplete evidence" in rendered
        assert "**Diagnostic:**" in rendered
        assert "Why it failed" not in rendered


def test_unknown_structured_target_is_compact_and_known_text_stays_readable() -> None:
    raw = json.dumps({"path": [f"node-{i}" for i in range(150)]})
    assert humanize_target(raw) == "Element recorded in Alfa's structured target evidence"
    assert humanize_target(raw[:-10]) == "Element recorded in Alfa's structured target evidence"
    assert (
        humanize_target('{"type":"text","data":"Known text","path":["unknown"]}')
        == "Text “Known text”"
    )
    assert (
        humanize_target('{"type":"element","name":"button","attributes":{"invalid":true}}')
        == "button"
    )
