"""Complete issue identities, honest absence decisions, and report boundaries."""

from __future__ import annotations

import json
import sqlite3
from typing import Any

import pytest

from audit.web import issues
from audit.web.comparison import (
    HISTORY_LIMIT,
    ComparisonError,
    compare_reports,
    previous_scan_id,
    site_history,
)


def scan(
    conn: sqlite3.Connection,
    *,
    date: str = "2026-09-01 12:00:00",
    seed: str = "https://example.com/",
    status: str = "completed",
    config: dict[str, Any] | None = None,
) -> int:
    row = conn.execute(
        "INSERT INTO scans(seed_url,status,config_json,started_at,page_count,"
        "axe_pages_scanned,alfa_pages_scanned,keyboard_pages_probed,"
        "responsive_pages_probed,semantic_pages_analyzed) VALUES(?,?,?,?,1,1,1,1,1,1)",
        (
            seed,
            status,
            json.dumps(config if config is not None else {"method_coverage_version": 1}),
            date,
        ),
    )
    scan_id = int(row.lastrowid or 0)
    conn.execute(
        "INSERT INTO pages(scan_id,url_normalized,status_code,render_mode) VALUES(?,?,200,'js')",
        (scan_id, "https://example.com/"),
    )
    return scan_id


def finding(
    conn: sqlite3.Connection,
    scan_id: int,
    rule: str,
    *,
    pipeline: str = "axe",
    target: str = "#target",
    outcome: str | None = None,
    status: str = "new",
    revealed_by: str | None = None,
    evidence: str = "{}",
) -> int:
    page_id = conn.execute("SELECT id FROM pages WHERE scan_id = ?", (scan_id,)).fetchone()[0]
    row = conn.execute(
        "INSERT INTO page_a11y_findings(page_id,scan_id,rule_id,target_selector,target_hash,"
        "help,impact,pipeline,engine_outcome,status,revealed_by,engine_evidence_json) "
        "VALUES(?,?,?,?,?,?,'serious',?,?,?,?,?)",
        (
            page_id,
            scan_id,
            rule,
            target,
            f"{target}-{outcome}-{revealed_by}",
            rule,
            pipeline,
            outcome or "failed",
            status,
            revealed_by,
            evidence,
        ),
    )
    return int(row.lastrowid or 0)


def test_all_five_categories_and_no_mutations(tmp_db: sqlite3.Connection) -> None:
    old = scan(tmp_db)
    new = scan(tmp_db, date="2026-09-02 12:00:00")
    finding(tmp_db, old, "disappeared")
    finding(tmp_db, new, "appeared")
    for report in (old, new):
        finding(tmp_db, report, "unchanged")
        finding(tmp_db, report, "status", status="new" if report == old else "reviewing")
    finding(tmp_db, old, "focus-hidden", pipeline="focus")
    changes = tmp_db.total_changes
    result = compare_reports(tmp_db, new)
    assert result.counts == {
        "new": 1,
        "still_detected": 1,
        "changed": 1,
        "no_longer_detected": 1,
        "cannot_compare": 1,
    }
    assert tmp_db.total_changes == changes
    assert result.baseline and result.baseline.id == old
    row = next(row for row in result.rows if row.key == "axe:status")
    assert row.before and row.after
    assert row.before.statuses == {"new": 1}
    assert row.after.statuses == {"reviewing": 1}
    assert all(f"/scans/{old}/" in link.url for link in row.before.evidence)
    assert all(f"/scans/{new}/" in link.url for link in row.after.evidence)


@pytest.mark.parametrize(
    "pipeline,rule",
    [
        ("axe", "button-name"),
        ("alfa", "sia-r69"),
        ("keyboard", "keyboard-trap"),
        ("responsive", "responsive-reflow"),
        ("focus", "focus-hidden"),
        ("visual", "visual-contrast"),
        ("semantic", "semantic:1.3.1"),
    ],
)
def test_every_dom_pipeline_is_compared(
    tmp_db: sqlite3.Connection,
    pipeline: str,
    rule: str,
) -> None:
    old, new = scan(tmp_db), scan(tmp_db, date="2026-09-02 12:00:00")
    for report in (old, new):
        finding(
            tmp_db,
            report,
            rule,
            pipeline=pipeline,
            outcome="failed" if pipeline == "alfa" else None,
        )
    result = compare_reports(tmp_db, new)
    assert len(result.rows) == 1
    assert result.rows[0].pipeline == pipeline
    assert result.rows[0].category == "still_detected"


def test_alfa_outcome_transition_and_subgroup_links(tmp_db: sqlite3.Connection) -> None:
    old, new = scan(tmp_db), scan(tmp_db, date="2026-09-02 12:00:00")
    finding(tmp_db, old, "sia-r69", pipeline="alfa", outcome="cant_tell")
    finding(tmp_db, new, "sia-r69", pipeline="alfa", outcome="failed")
    result = compare_reports(tmp_db, new)
    assert len(result.rows) == 1
    row = result.rows[0]
    assert row.key == "alfa:sia-r69"
    assert row.category == "changed"
    assert row.before and row.after
    assert row.before.outcomes == {"cant_tell": 1}
    assert row.after.outcomes == {"failed": 1}
    assert row.before.issues[0].url.endswith("alfa:sia-r69:cant_tell")
    assert row.after.issues[0].url.endswith("alfa:sia-r69:failed")


def test_locations_beyond_three_samples_and_all_statuses(tmp_db: sqlite3.Connection) -> None:
    old, new = scan(tmp_db), scan(tmp_db, date="2026-09-02 12:00:00")
    for report in (old, new):
        for i in range(12):
            target = f"#target-{i}"
            if report == new and i == 11:
                target = "#replacement"
            finding(tmp_db, report, "button-name", target=target)
    result = compare_reports(tmp_db, new)
    row = result.rows[0]
    assert row.category == "changed"
    assert row.before and row.after
    assert row.before.occurrences == row.after.occurrences == 12
    assert len(row.after.evidence) == 10


def test_revealed_state_changes_are_not_ignored(tmp_db: sqlite3.Connection) -> None:
    old, new = scan(tmp_db), scan(tmp_db, date="2026-09-02 12:00:00")
    finding(tmp_db, old, "label", revealed_by="Open menu")
    finding(tmp_db, new, "label", revealed_by="Open dialog")
    assert compare_reports(tmp_db, new).rows[0].category == "changed"


@pytest.mark.parametrize(
    "change", ["counter", "settings", "page", "error", "interaction", "search"]
)
def test_absence_with_incomplete_coverage_is_not_resolution(
    tmp_db: sqlite3.Connection,
    change: str,
) -> None:
    old, new = scan(tmp_db), scan(tmp_db, date="2026-09-02 12:00:00")
    finding(tmp_db, old, "button-name")
    if change == "counter":
        tmp_db.execute("UPDATE scans SET axe_pages_scanned=0 WHERE id=?", (new,))
    elif change == "settings":
        tmp_db.execute("UPDATE scans SET config_json=? WHERE id=?", ('{"axe_level":"AAA"}', new))
    elif change == "page":
        tmp_db.execute(
            "UPDATE pages SET url_normalized='https://example.com/other' WHERE scan_id=?", (new,)
        )
    elif change == "error":
        tmp_db.execute("UPDATE scans SET error_count=1 WHERE id=?", (new,))
    elif change == "interaction":
        tmp_db.execute("UPDATE scans SET config_json=?", ('{"interaction_checks_enabled":true}',))
    elif change == "search":
        tmp_db.execute("UPDATE scans SET config_json=?", ('{"search":{"query":"widgets"}}',))
    result = compare_reports(tmp_db, new)
    assert result.rows[0].category == "cannot_compare"
    assert result.rows[0].limitations


def test_alfa_truncation_and_dropped_records_are_visible(tmp_db: sqlite3.Connection) -> None:
    old, new = scan(tmp_db), scan(tmp_db, date="2026-09-02 12:00:00")
    finding(
        tmp_db,
        old,
        "sia-r69",
        pipeline="alfa",
        outcome="cant_tell",
        evidence='{"diagnostic":{"message":"unsupported sizing"},"rest":',
    )
    tmp_db.execute("UPDATE scans SET alfa_cant_tell_total=40 WHERE id=?", (old,))
    result = compare_reports(tmp_db, new)
    assert result.rows[0].category == "cannot_compare"
    text = " ".join(result.rows[0].limitations)
    assert "incomplete" in text
    assert "1 of 40" in text


def test_predecessor_normalizes_seed_and_uses_time_not_id(tmp_db: sqlite3.Connection) -> None:
    old = scan(tmp_db, seed="HTTPS://EXAMPLE.COM:443")
    current = scan(tmp_db, date="2026-09-03 12:00:00")
    scan(tmp_db, date="2026-09-04 12:00:00")
    closer = scan(tmp_db, date="2026-09-02 12:00:00")
    scan(tmp_db, date="2026-09-02 18:00:00", status="failed")
    assert compare_reports(tmp_db, current).baseline.id == closer  # type: ignore[union-attr]
    assert compare_reports(tmp_db, closer).baseline.id == old  # type: ignore[union-attr]
    row = dict(tmp_db.execute("SELECT * FROM scans WHERE id=?", (old,)).fetchone())
    assert previous_scan_id(tmp_db, row) is None


def test_timestamp_ties_use_lower_id(tmp_db: sqlite3.Connection) -> None:
    old, new = scan(tmp_db), scan(tmp_db)
    assert compare_reports(tmp_db, new).baseline.id == old  # type: ignore[union-attr]
    with pytest.raises(ComparisonError, match="earlier"):
        compare_reports(tmp_db, old, compare_to=new)


@pytest.mark.parametrize(
    "kind,code",
    [
        ("same", 400),
        ("missing", 404),
        ("later", 400),
        ("unrelated", 400),
        ("running", 409),
        ("protected", 403),
    ],
)
def test_pair_guards(tmp_db: sqlite3.Connection, kind: str, code: int) -> None:
    old, current = scan(tmp_db), scan(tmp_db, date="2026-09-02 12:00:00")
    other = old
    if kind == "same":
        other = current
    elif kind == "missing":
        other = 9999
    elif kind == "later":
        other = scan(tmp_db, date="2026-09-03 12:00:00")
    elif kind == "unrelated":
        other = scan(tmp_db, seed="https://elsewhere.com/")
    elif kind == "running":
        other = scan(tmp_db, status="running")
    elif kind == "protected":
        # The service guard needs only ownership existence. A temporary view
        # avoids constructing unrelated encrypted transport metadata here.
        tmp_db.execute("ALTER TABLE protected_scans RENAME TO saved_protected_scans")
        tmp_db.execute("CREATE TABLE protected_scans(scan_id INTEGER)")
        tmp_db.execute("INSERT INTO protected_scans VALUES(?)", (old,))
    with pytest.raises(ComparisonError) as exc:
        compare_reports(tmp_db, current, compare_to=other)
    assert exc.value.status_code == code


def test_no_baseline_and_current_not_completed(tmp_db: sqlite3.Connection) -> None:
    first = scan(tmp_db)
    result = compare_reports(tmp_db, first)
    assert result.baseline is None and result.rows == [] and result.limitations
    tmp_db.execute("UPDATE scans SET status='running' WHERE id=?", (first,))
    with pytest.raises(ComparisonError, match="completed"):
        compare_reports(tmp_db, first)


def test_filters_pagination_and_empty_page_metadata(tmp_db: sqlite3.Connection) -> None:
    old, new = scan(tmp_db), scan(tmp_db, date="2026-09-02 12:00:00")
    for i in range(55):
        finding(tmp_db, new, f"rule-{i}")
    finding(tmp_db, old, "keyboard-trap", pipeline="keyboard")
    first = compare_reports(tmp_db, new)
    assert first.total == 56 and len(first.rows) == 50
    second = compare_reports(tmp_db, new, page=2)
    assert len(second.rows) == 6
    filtered = compare_reports(tmp_db, new, pipeline="keyboard", category="cannot_compare")
    assert filtered.total == 1
    empty = compare_reports(tmp_db, new, page=100)
    assert empty.rows == [] and empty.counts == first.counts
    assert empty.pipeline_counts == {"axe": 55, "keyboard": 1}
    everything = compare_reports(tmp_db, new, page_size=500)
    assert len(everything.rows) == 56
    with pytest.raises(ComparisonError):
        compare_reports(tmp_db, new, page_size=501)


def test_image_occurrences_and_status_changes(tmp_db: sqlite3.Connection) -> None:
    from audit.db import repo

    old, new = scan(tmp_db), scan(tmp_db, date="2026-09-02 12:00:00")
    image_id = repo.upsert_image(
        tmp_db,
        content_hash="b" * 64,
        src_url="https://example.com/banner.png",
        mime="image/png",
        bytes_len=10,
        width=100,
        height=20,
        blob_path="unused.png",
        has_svg_text=False,
        scan_id=old,
    )
    repo.upsert_analysis(
        tmp_db,
        image_id=image_id,
        ocr_text="Welcome",
        ocr_confidence=99,
        vlm_classification="essential",
        vlm_rationale="Text",
        has_text=True,
        model_versions={"test": "v1"},
    )
    for report in (old, new):
        page_id = tmp_db.execute("SELECT id FROM pages WHERE scan_id=?", (report,)).fetchone()[0]
        for position in range(4):
            repo.upsert_page_image(
                tmp_db,
                page_id=page_id,
                image_id=image_id,
                alt_text=None,
                role=None,
                context_snippet=None,
                position=position,
            )
        repo.upsert_finding(
            tmp_db,
            image_id=image_id,
            scan_id=report,
            severity="major",
            priority_score=4,
            remediation_hint="Replace image text",
        )
    stable = compare_reports(tmp_db, new).rows[0]
    assert stable.pipeline == "image" and stable.category == "still_detected"
    assert stable.after and stable.after.occurrences == 4
    tmp_db.execute("UPDATE findings SET status='reviewing' WHERE scan_id=?", (new,))
    changed = compare_reports(tmp_db, new).rows[0]
    assert changed.category == "changed"
    assert changed.after and changed.after.statuses == {"reviewing": 4}
    assert changed.after.evidence[0].url.startswith("/findings/")


def test_alfa_stable_identity_separates_display_and_location(tmp_db: sqlite3.Connection) -> None:
    old, new = scan(tmp_db), scan(tmp_db, date="2026-09-02 12:00:00")
    for report, text in [(old, "Previous text"), (new, "Changed text")]:
        finding(
            tmp_db,
            report,
            "sia-r69",
            pipeline="alfa",
            outcome="failed",
            target=json.dumps({"type": "text", "data": text, "path": "/p[1]/text()"}),
            evidence='{"target_identity":"stable-location"}',
        )
    assert compare_reports(tmp_db, new).rows[0].category == "still_detected"
    tmp_db.execute(
        "UPDATE page_a11y_findings SET engine_evidence_json=? WHERE scan_id=?",
        ('{"target_identity":"another-location"}', new),
    )
    assert compare_reports(tmp_db, new).rows[0].category == "changed"


def test_legacy_alfa_targets_have_identity_limitation(tmp_db: sqlite3.Connection) -> None:
    old, new = scan(tmp_db), scan(tmp_db, date="2026-09-02 12:00:00")
    finding(
        tmp_db,
        old,
        "sia-r69",
        pipeline="alfa",
        outcome="cant_tell",
        target='{"type":"text","data":"Repeated words"}',
    )
    row = compare_reports(tmp_db, new).rows[0]
    assert row.category == "cannot_compare"
    assert any("no DOM location" in item for item in row.limitations)


def test_complete_and_unknown_method_coverage_are_explicit(tmp_db: sqlite3.Connection) -> None:
    scan(tmp_db)
    new = scan(tmp_db, date="2026-09-02 12:00:00")
    result = compare_reports(tmp_db, new)
    coverage = {entry.pipeline: entry for entry in result.coverage}
    assert coverage["axe"].after.state == "complete"
    assert coverage["axe"].after.checked == 1
    assert coverage["focus"].after.state == "unknown"
    assert coverage["focus"].after.checked is None
    assert result.rows == []


def test_same_counts_with_statuses_swapped_between_targets_is_changed(
    tmp_db: sqlite3.Connection,
) -> None:
    old, new = scan(tmp_db), scan(tmp_db, date="2026-09-02 12:00:00")
    for report in (old, new):
        finding(
            tmp_db,
            report,
            "button-name",
            target="#first",
            status="new" if report == old else "reviewing",
        )
        finding(
            tmp_db,
            report,
            "button-name",
            target="#second",
            status="reviewing" if report == old else "new",
        )
    row = compare_reports(tmp_db, new).rows[0]
    assert row.before and row.after and row.before.statuses == row.after.statuses
    assert row.category == "changed"


def test_occurrence_multiplicity_is_preserved(tmp_db: sqlite3.Connection) -> None:
    old, new = scan(tmp_db), scan(tmp_db, date="2026-09-02 12:00:00")
    for report in (old, new):
        finding(tmp_db, report, "button-name")
    tmp_db.execute(
        "INSERT INTO page_a11y_findings(page_id,scan_id,rule_id,target_selector,target_hash,"
        "help,impact,pipeline) SELECT page_id,scan_id,rule_id,target_selector,'second-hash',"
        "help,impact,pipeline FROM page_a11y_findings WHERE scan_id=?",
        (new,),
    )
    row = compare_reports(tmp_db, new).rows[0]
    assert row.category == "changed"
    assert row.before and row.before.occurrences == 1
    assert row.after and row.after.occurrences == 2


def test_missing_interaction_table_reports_incomplete_coverage(
    tmp_db: sqlite3.Connection,
) -> None:
    config = {"method_coverage_version": 1, "interaction_checks_enabled": True}
    old = scan(tmp_db, config=config)
    new = scan(tmp_db, date="2026-09-02 12:00:00", config=config)
    finding(tmp_db, old, "button-name", revealed_by="Open menu")
    tmp_db.execute("DROP TABLE scan_interaction_runs")

    result = compare_reports(tmp_db, new)

    assert result.rows[0].category == "cannot_compare"
    assert any(
        "page states opened by clicking" in message for message in result.rows[0].limitations
    )
    coverage = next(pair for pair in result.coverage if pair.pipeline == "axe")
    assert coverage.before.state == "incomplete"
    assert coverage.after.state == "incomplete"


def test_unoperated_control_prevents_claiming_revealed_issue_disappeared(
    tmp_db: sqlite3.Connection,
) -> None:
    config = {"method_coverage_version": 1, "interaction_checks_enabled": True}
    old = scan(tmp_db, config=config)
    new = scan(tmp_db, date="2026-09-02 12:00:00", config=config)
    finding(tmp_db, old, "button-name", revealed_by="Open menu")
    for report, operated in [(old, 2), (new, 1)]:
        page_id = tmp_db.execute("SELECT id FROM pages WHERE scan_id=?", (report,)).fetchone()[0]
        tmp_db.execute(
            "INSERT INTO scan_interaction_runs "
            "(scan_id,page_id,controls_found,controls_operated) VALUES(?,?,2,?)",
            (report, page_id, operated),
        )
    result = compare_reports(tmp_db, new)
    assert result.rows[0].category == "cannot_compare"
    assert any(
        "page states opened by clicking" in message for message in result.rows[0].limitations
    )
    coverage = next(pair for pair in result.coverage if pair.pipeline == "axe")
    assert coverage.before.state == "complete"
    assert coverage.after.state == "incomplete"


@pytest.mark.parametrize("pipeline", ["keyboard", "responsive"])
def test_probe_attempt_counters_do_not_prove_successful_absence_checks(
    tmp_db: sqlite3.Connection,
    pipeline: str,
) -> None:
    old = scan(tmp_db)
    new = scan(tmp_db, date="2026-09-02 12:00:00")
    finding(tmp_db, old, f"{pipeline}-disappeared", pipeline=pipeline)
    finding(tmp_db, new, f"{pipeline}-appeared", pipeline=pipeline)
    for report in (old, new):
        finding(tmp_db, report, f"{pipeline}-stable", pipeline=pipeline)
        finding(
            tmp_db,
            report,
            f"{pipeline}-status",
            pipeline=pipeline,
            status="new" if report == old else "reviewing",
        )
    result = compare_reports(tmp_db, new)
    categories = {row.key: row.category for row in result.rows}
    assert categories[f"{pipeline}:{pipeline}-disappeared"] == "cannot_compare"
    assert categories[f"{pipeline}:{pipeline}-appeared"] == "cannot_compare"
    assert categories[f"{pipeline}:{pipeline}-stable"] == "still_detected"
    assert categories[f"{pipeline}:{pipeline}-status"] == "changed"
    coverage = next(pair for pair in result.coverage if pair.pipeline == pipeline)
    assert coverage.before.checked == coverage.after.checked == 1
    assert coverage.before.total == coverage.after.total == 1
    assert coverage.before.state == coverage.after.state == "unknown"
    assert any("per-check errors and probe limits" in item for item in result.limitations)


@pytest.mark.parametrize(("new_version", "changed"), [("2.2", False), ("2.1", True)])
def test_wcag_version_compares_what_each_scan_ran(
    tmp_db: sqlite3.Connection, new_version: str, changed: bool
) -> None:
    """A report stored before the version setting ran WCAG 2.2.

    Comparing it with a new 2.2 report is a like-for-like comparison and
    must not claim the settings changed just because the old row lacks the
    key. A new 2.1 report really did run a different rule set.
    """
    old = scan(tmp_db)
    new = scan(
        tmp_db,
        date="2026-09-02 12:00:00",
        config={"method_coverage_version": 1, "wcag_version": new_version},
    )
    finding(tmp_db, old, "button-name")
    finding(tmp_db, new, "button-name")
    limitations = " ".join(compare_reports(tmp_db, new).rows[0].limitations)
    assert ("wcag_version" in limitations) is changed
    if not changed:
        assert "Scan settings changed" not in limitations


def _second_page(conn: sqlite3.Connection, scan_id: int) -> int:
    return int(
        conn.execute(
            "INSERT INTO pages(scan_id,url_normalized,status_code,render_mode) "
            "VALUES(?,?,200,'js')",
            (scan_id, "https://example.com/about"),
        ).lastrowid
        or 0
    )


def test_changes_are_presence_in_each_report(tmp_db: sqlite3.Connection) -> None:
    """New, resolved and remaining say only where a group was found.

    The stricter category stays on the row: a group that went away while a
    method's coverage was unknown is "resolved" by presence and still
    "cannot_compare" by the evidence.
    """
    old, new = scan(tmp_db), scan(tmp_db, date="2026-09-02 12:00:00")
    finding(tmp_db, old, "gone")
    finding(tmp_db, new, "arrived")
    finding(tmp_db, old, "focus-hidden", pipeline="focus")
    for report in (old, new):
        finding(tmp_db, report, "kept")
    result = compare_reports(tmp_db, new)
    assert result.changes == {"new": 1, "resolved": 2, "remaining": 1}
    rows = {row.key: row for row in result.rows}
    assert rows["axe:arrived"].change == "new"
    assert rows["axe:gone"].change == "resolved"
    assert rows["axe:kept"].change == "remaining"
    assert rows["focus:focus-hidden"].change == "resolved"
    assert rows["focus:focus-hidden"].category == "cannot_compare"
    # Filters narrow the rows, never the change counts.
    assert compare_reports(tmp_db, new, category="new").changes == result.changes


def test_display_counts_match_the_issues_table(tmp_db: sqlite3.Connection) -> None:
    """An element repeated on a second page counts once, as on the Issues page.

    Location matching still sees both findings (``occurrences``), so a repeat
    that disappears is still a change.
    """
    old, new = scan(tmp_db), scan(tmp_db, date="2026-09-02 12:00:00")
    finding(tmp_db, old, "button-name")
    finding(tmp_db, new, "button-name")
    page = _second_page(tmp_db, new)
    tmp_db.execute(
        "INSERT INTO page_a11y_findings(page_id,scan_id,rule_id,target_selector,target_hash,"
        "help,impact,pipeline) SELECT ?,scan_id,rule_id,target_selector,target_hash,"
        "help,impact,pipeline FROM page_a11y_findings WHERE scan_id=?",
        (page, new),
    )
    result = compare_reports(tmp_db, new)
    row = result.rows[0]
    assert row.after and row.after.occurrences == 2
    assert row.after.issue_occurrences == 1
    assert result.after_totals.model_dump() == {"groups": 1, "occurrences": 1}
    assert result.before_totals and result.before_totals.model_dump() == {
        "groups": 1,
        "occurrences": 1,
    }


def test_rows_carry_wcag_criterion_and_level(tmp_db: sqlite3.Connection) -> None:
    """The criterion and level come from the Issues projection, unchanged."""
    old, new = scan(tmp_db), scan(tmp_db, date="2026-09-02 12:00:00")
    finding(tmp_db, old, "image-alt")
    finding(tmp_db, new, "image-alt")
    row = compare_reports(tmp_db, new).rows[0]
    issue = issues.list_issues(tmp_db, new)[0]
    assert row.wcag_sc == issue.wcag_sc == "1.1.1"
    assert row.wcag_name == issue.wcag_name
    assert row.conformance == issue.conformance == "A"


def test_settings_changed_names_only_the_settings(tmp_db: sqlite3.Connection) -> None:
    old = scan(tmp_db, config={"method_coverage_version": 1, "max_pages": 10})
    new = scan(
        tmp_db,
        date="2026-09-02 12:00:00",
        config={"method_coverage_version": 1, "max_pages": 20, "db_path": "/elsewhere"},
    )
    result = compare_reports(tmp_db, new, compare_to=old)
    assert result.settings_changed == ["max_pages"]
    assert "20" not in " ".join(result.settings_changed)


def test_no_baseline_still_reports_this_reports_totals(tmp_db: sqlite3.Connection) -> None:
    first = scan(tmp_db)
    finding(tmp_db, first, "button-name")
    result = compare_reports(tmp_db, first)
    assert result.baseline is None and result.before_totals is None
    assert result.after_totals.model_dump() == {"groups": 1, "occurrences": 1}
    assert result.changes == {"new": 0, "resolved": 0, "remaining": 0}


def test_site_history_is_one_sites_completed_public_reports(tmp_db: sqlite3.Connection) -> None:
    """Oldest first, in the order a baseline is chosen, with comparison totals."""
    later = scan(tmp_db, date="2026-09-03 12:00:00")
    earlier = scan(tmp_db, seed="https://EXAMPLE.com:443", date="2026-09-01 12:00:00")
    scan(tmp_db, seed="https://elsewhere.com/", date="2026-09-02 12:00:00")
    scan(tmp_db, status="running", date="2026-09-02 13:00:00")
    hidden = scan(tmp_db, date="2026-09-02 14:00:00")
    tmp_db.execute("ALTER TABLE protected_scans RENAME TO saved_protected_scans")
    tmp_db.execute("CREATE TABLE protected_scans(scan_id INTEGER)")
    tmp_db.execute("INSERT INTO protected_scans VALUES(?)", (hidden,))
    finding(tmp_db, later, "button-name")
    finding(tmp_db, later, "image-alt", target="#logo")
    history = site_history(tmp_db, later)
    assert [point.id for point in history.scans] == [earlier, later]
    assert history.total == 2
    assert (history.scans[-1].groups, history.scans[-1].occurrences) == (2, 2)
    assert (history.scans[0].groups, history.scans[0].occurrences) == (0, 0)
    comparison = compare_reports(tmp_db, later)
    assert comparison.baseline and comparison.baseline.id == earlier
    assert comparison.after_totals.groups == history.scans[-1].groups
    with pytest.raises(ComparisonError) as exc:
        site_history(tmp_db, hidden)
    assert exc.value.status_code == 403
    with pytest.raises(ComparisonError) as exc:
        site_history(tmp_db, 9999)
    assert exc.value.status_code == 404


def test_site_history_keeps_the_most_recent_reports(tmp_db: sqlite3.Connection) -> None:
    ids = [scan(tmp_db, date=f"2026-08-{day:02d} 12:00:00") for day in range(1, 26)]
    history = site_history(tmp_db, ids[0])
    assert history.total == 25
    assert [point.id for point in history.scans] == ids[-HISTORY_LIMIT:]


def test_notes_say_each_limit_once_with_differences_first(tmp_db: sqlite3.Connection) -> None:
    old, new = scan(tmp_db), scan(tmp_db, date="2026-09-02 12:00:00")
    tmp_db.execute("UPDATE pages SET final_url='https://example.com/home'")
    tmp_db.execute("UPDATE scans SET error_count=1 WHERE id=?", (new,))
    tmp_db.execute("UPDATE scans SET axe_pages_scanned=0")
    tmp_db.execute(
        "UPDATE pages SET url_normalized='https://example.com/other' WHERE scan_id=?", (new,)
    )
    notes = compare_reports(tmp_db, new).notes
    assert [(note.scans, note.differs) for note in notes] == [
        ([], True),
        ([new], True),
        ([old, new], False),
    ]
    assert notes[0].text == (
        f"The scans checked different pages: 1 page only in scan {old}, 1 page only in scan {new}."
    )
    assert notes[1].text.startswith("Errors were recorded")
    assert notes[2].text.startswith("Some pages redirected")
    # The method coverage table states these, and the scan is in ``scans``.
    assert not any(
        "checked 0 of" in note.text or "not recorded." in note.text or "Report #" in note.text
        for note in notes
    )


def test_a_groups_evidence_limit_is_noted_for_the_scan_that_stored_it(
    tmp_db: sqlite3.Connection,
) -> None:
    old, new = scan(tmp_db), scan(tmp_db, date="2026-09-02 12:00:00")
    broken = '{"diagnostic":{"message":"unsupported sizing"},"rest":'
    finding(tmp_db, old, "sia-r69", pipeline="alfa", outcome="cant_tell", evidence=broken)
    limit = "Stored Alfa evidence is incomplete or unavailable."
    notes = compare_reports(tmp_db, new).notes
    assert [(note.text, note.scans, note.differs) for note in notes] == [(limit, [old], True)]
    finding(tmp_db, new, "sia-r69", pipeline="alfa", outcome="cant_tell", evidence=broken)
    notes = compare_reports(tmp_db, new).notes
    assert [(note.text, note.scans, note.differs) for note in notes] == [(limit, [old, new], False)]
