"""The "How sure" guardrail: what may be shown by default, and what may not.

The Issues page opens on the levels in ``labels.DEFAULT_REVIEW_LANES``
(Mostly sure and Measured). These tests pin which checks can reach those
levels, so a result a model judged can never be shown by default by accident.
"""

from __future__ import annotations

import sqlite3

import pytest

from audit import labels
from audit.analyzer.focus import base as focus_base
from audit.analyzer.keyboard import base as keyboard_base
from audit.analyzer.responsive import base as responsive_base
from audit.analyzer.visual import base as visual_base
from audit.db import repo
from audit.web import issues as issues_mod
from audit.web import sites

# One non-legacy failure summary per measured rule. The keyboard and motion
# rules read their summary to tell a measurement from an older heuristic.
_SUMMARY = {
    "keyboard-trap-stuck": "4 Tab attempts and 4 Shift+Tab attempts remained on the same element.",
    "visual-motion-no-pause": "Runtime playback measurement: currentTime advanced 0.34 seconds",
}


def _scan(conn: sqlite3.Connection) -> tuple[int, int]:
    cur = conn.execute(
        "INSERT INTO scans (seed_url, status, page_count, finding_count, config_json) "
        "VALUES ('http://example.com/', 'completed', 1, 0, '{}')"
    )
    scan_id = int(cur.lastrowid or 0)
    page_id = repo.upsert_page(
        conn,
        scan_id=scan_id,
        url_normalized="http://example.com/",
        status_code=200,
        title="Home",
        render_mode="js",
        html_hash="0" * 64,
    )
    return scan_id, page_id


def _finding(
    conn: sqlite3.Connection,
    scan_id: int,
    page_id: int,
    *,
    pipeline: str,
    rule_id: str,
    engine_outcome: str = "failed",
) -> None:
    conn.execute(
        """
        INSERT INTO page_a11y_findings
            (page_id, scan_id, pipeline, criterion_sc, rule_id, wcag_sc,
             wcag_scs, wcag_level, impact, help, help_url, target_selector,
             failure_summary, html_snippet, target_hash, status, engine_outcome)
        VALUES (?, ?, ?, '1.3.1', ?, '1.3.1', '1.3.1', 'A', 'serious', 'Help',
            'https://example.com/help', 'main', ?, '<main></main>', ?, 'new', ?)
        """,
        (
            page_id,
            scan_id,
            pipeline,
            rule_id,
            _SUMMARY.get(rule_id, "Observed on the page."),
            f"{pipeline}-{rule_id}-{engine_outcome}",
            engine_outcome,
        ),
    )


def test_default_view_is_every_level() -> None:
    # Every issue type is in the table when it opens (2026-11-13); the note
    # over it explains Not sure and For information.
    assert labels.DEFAULT_REVIEW_LANES == labels.REVIEW_LANES
    assert labels.REVIEW_LANES == ("likely_barrier", "measured", "expert_review", "informational")


def test_measured_rules_are_real_browser_rules_and_exclude_the_vision_model() -> None:
    """Every allowlisted rule is one a probe emits; the VLM rule is not one."""
    emitted = {
        ("keyboard", keyboard_base.RULE_STUCK),
        ("responsive", responsive_base.RULE_REFLOW),
        ("focus", focus_base.RULE_POSITIVE_TABINDEX),
        ("visual", visual_base.RULE_MOTION_NO_PAUSE),
        ("visual", visual_base.RULE_AUTOPLAY_AUDIO_NO_CONTROL),
    }
    assert emitted == issues_mod._MEASURED_RULES
    assert ("visual", visual_base.RULE_MEANINGFUL_SEQUENCE) not in issues_mod._MEASURED_RULES
    # Both reported problems that were not on a live page (2026-11-11).
    assert ("focus", focus_base.RULE_FOCUS_OBSCURED) not in issues_mod._MEASURED_RULES
    assert ("responsive", responsive_base.RULE_TEXT_CLIPPED) not in issues_mod._MEASURED_RULES
    # Uses the same cut-off-text detector, so it shared that flaw (2026-11-13).
    assert ("responsive", responsive_base.RULE_SPACING_CLIPPED) not in issues_mod._MEASURED_RULES
    # No pipeline that a model judges, and no rule engine, is ever listed.
    assert {pipeline for pipeline, _ in issues_mod._MEASURED_RULES} == {
        "keyboard",
        "responsive",
        "focus",
        "visual",
    }


@pytest.mark.parametrize(("pipeline", "rule_id"), sorted(issues_mod._MEASURED_RULES))
def test_each_measured_rule_lands_in_measured(
    tmp_db: sqlite3.Connection, pipeline: str, rule_id: str
) -> None:
    scan_id, page_id = _scan(tmp_db)
    _finding(tmp_db, scan_id, page_id, pipeline=pipeline, rule_id=rule_id)

    (row,) = issues_mod.list_issues(tmp_db, scan_id)
    assert row.review_lane == "measured"
    assert row.evidence_confidence == "medium"
    # Never counted with the rule-check failures.
    assert row.high_confidence_occurrence_count == 0


@pytest.mark.parametrize(
    ("pipeline", "rule_id", "engine_outcome"),
    [
        ("semantic", "semantic:2.4.4", "failed"),
        ("visual", "visual-meaningful-sequence", "failed"),
        ("protected_image", "protected-image-of-text", "failed"),
        ("alfa", "sia-r1", "cant_tell"),
        # Browser rules taken back out after a live check found them false.
        ("focus", "focus-not-obscured", "failed"),
        ("responsive", "responsive-text-clipped", "failed"),
        # Shares the cut-off-text detector with the rule above.
        ("responsive", "responsive-text-spacing-clipped", "failed"),
        # A browser rule nobody has listed stays a lead until someone does.
        ("responsive", "responsive-some-new-rule", "failed"),
        ("focus", "focus-some-new-rule", "failed"),
    ],
)
def test_model_judged_and_unlisted_results_are_not_sure(
    tmp_db: sqlite3.Connection, pipeline: str, rule_id: str, engine_outcome: str
) -> None:
    scan_id, page_id = _scan(tmp_db)
    _finding(
        tmp_db, scan_id, page_id, pipeline=pipeline, rule_id=rule_id, engine_outcome=engine_outcome
    )

    (row,) = issues_mod.list_issues(tmp_db, scan_id)
    assert row.review_lane == "expert_review"


def test_legacy_keyboard_record_is_not_raised_to_measured(tmp_db: sqlite3.Connection) -> None:
    scan_id, page_id = _scan(tmp_db)
    _finding(tmp_db, scan_id, page_id, pipeline="keyboard", rule_id="keyboard-trap-iframe")

    (row,) = issues_mod.list_issues(tmp_db, scan_id)
    assert row.review_lane == "informational"


def test_default_view_counts_and_report_counts_agree(tmp_db: sqlite3.Connection) -> None:
    scan_id, page_id = _scan(tmp_db)
    _finding(tmp_db, scan_id, page_id, pipeline="axe", rule_id="image-alt")
    _finding(tmp_db, scan_id, page_id, pipeline="responsive", rule_id="responsive-reflow-overflow")
    _finding(tmp_db, scan_id, page_id, pipeline="semantic", rule_id="semantic:2.4.4")
    _finding(tmp_db, scan_id, page_id, pipeline="visual", rule_id="visual-meaningful-sequence")

    rows = issues_mod.list_issues(tmp_db, scan_id)
    assert issues_mod.review_lane_breakdown(rows) == {
        "likely_barrier": 1,
        "measured": 1,
        "expert_review": 2,
        "informational": 0,
    }
    counts = issues_mod.default_view_counts(rows)
    assert counts == {
        "issue_types": 4,
        "occurrences": 4,
        "hidden_issue_types": 0,
        "hidden_occurrences": 0,
    }
    # The default sort keeps the levels in order.
    assert [row.review_lane for row in rows] == [
        "likely_barrier",
        "measured",
        "expert_review",
        "expert_review",
    ]
    # Asking for one level still works, and asking for none returns all.
    measured = issues_mod.list_issues(tmp_db, scan_id, review_lane="measured")
    assert [row.review_lane for row in measured] == ["measured"]

    report = sites.report_counts(tmp_db, scan_id)
    assert (report.issue_count, report.occurrence_count) == (4, 4)
    assert (report.shown_issue_count, report.shown_occurrence_count) == (4, 4)
