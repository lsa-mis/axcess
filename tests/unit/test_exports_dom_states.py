"""A click-revealed barrier must stay reproducible in every export.

The failure this guards against is quiet and expensive: a finding that only
exists after a control is operated gets exported as though the page load
showed it, the assignee looks at the page, sees nothing, and closes the ticket
as "cannot reproduce". Each assertion below is one export surface where the
revealing control has to survive.
"""

from __future__ import annotations

import json
import sqlite3

import pytest

from audit.db import repo
from audit.exports import interaction_coverage
from audit.exports.collector import collect_scan
from audit.exports.csv_export import CSV_COLUMNS, render_csv
from audit.exports.jira_export import render_jira_csv
from audit.exports.json_export import to_payload

REVEALED_BY = "Open account menu"


@pytest.fixture
def scan_with_click_revealed_finding(tmp_db: sqlite3.Connection) -> int:
    """A scan whose only barrier is behind a click, plus its ledger row."""
    scan_id = int(
        tmp_db.execute(
            "INSERT INTO scans (seed_url, status, page_count, config_json, "
            "interaction_pages_probed, interaction_states_total) "
            "VALUES ('https://example.test/', 'completed', 1, ?, 1, 4)",
            (
                json.dumps(
                    {
                        "interaction_checks_enabled": True,
                        "interaction_coverage_version": 2,
                    }
                ),
            ),
        ).lastrowid
    )
    page_id = repo.upsert_page(
        tmp_db,
        scan_id=scan_id,
        url_normalized="https://example.test/",
        status_code=200,
        title="Home",
        render_mode="js",
        html_hash=None,
    )
    tmp_db.execute(
        "INSERT INTO page_a11y_findings (scan_id, page_id, rule_id, wcag_sc, wcag_level, "
        "impact, help, help_url, target_selector, target_hash, failure_summary, "
        "html_snippet, status, "
        "pipeline, engine_outcome, revealed_by) "
        "VALUES (?, ?, 'color-contrast', '1.4.3', 'AA', 'serious', "
        "'Elements must have sufficient colour contrast', 'https://example.test/rule', "
        "'.menu .item', 'hash-menu-item', 'Contrast 3.1:1', "
        "'<a class=\"item\">Profile</a>', 'new', "
        "'axe', 'failed', ?)",
        (scan_id, page_id, REVEALED_BY),
    )
    repo.record_interaction_run(
        tmp_db,
        scan_id=scan_id,
        page_id=page_id,
        controls_found=10,
        clicks_attempted=6,
        clicks_succeeded=6,
        controls_operated=6,
        states=4,
        blocked_controls=2,
        limits=["clicks"],
        dialogs_opened=1,
        dialogs_stuck=0,
        detail="",
    )
    tmp_db.commit()
    return scan_id


def test_csv_keeps_the_revealing_control(
    tmp_db: sqlite3.Connection, scan_with_click_revealed_finding: int
) -> None:
    scan = collect_scan(tmp_db, scan_with_click_revealed_finding)
    body = render_csv(scan)
    assert "revealed_by" in CSV_COLUMNS
    assert REVEALED_BY in body
    # Every row must still be the width of the header, or the column shifts
    # and a reader silently gets the wrong value under the wrong heading.
    for line in body.splitlines():
        assert line.count(",") >= len(CSV_COLUMNS) - 1


def test_json_exposes_revealed_by_under_a_bumped_schema(
    tmp_db: sqlite3.Connection, scan_with_click_revealed_finding: int
) -> None:
    payload = to_payload(collect_scan(tmp_db, scan_with_click_revealed_finding))
    assert payload["schema_version"] >= 4
    assert payload["a11y_findings"][0]["revealed_by"] == REVEALED_BY


def test_jira_ticket_tells_the_assignee_what_to_click(
    tmp_db: sqlite3.Connection, scan_with_click_revealed_finding: int
) -> None:
    body = render_jira_csv(collect_scan(tmp_db, scan_with_click_revealed_finding))
    assert "**To reproduce:**" in body
    assert REVEALED_BY in body


def test_load_state_findings_say_load_the_page_not_nothing(
    tmp_db: sqlite3.Connection, scan_with_click_revealed_finding: int
) -> None:
    """An empty reproduction step would read as "no steps needed" either way."""
    assert interaction_coverage.reproduction_step(None) == "Load the page."
    assert REVEALED_BY in interaction_coverage.reproduction_step(REVEALED_BY)


def test_coverage_projection_reports_operated_against_found(
    tmp_db: sqlite3.Connection, scan_with_click_revealed_finding: int
) -> None:
    cov = interaction_coverage.load(tmp_db, scan_with_click_revealed_finding)
    assert cov.enabled and cov.ledger_recorded
    assert (cov.controls_operated, cov.controls_found) == (6, 10)
    assert cov.findings_revealed == 1
    assert cov.states_total == 4
    # The page hit a bound, so it must appear in the "not fully checked" list
    # rather than being counted as swept.
    assert [p.page_url for p in cov.limited_pages] == ["https://example.test/"]
    assert "click limit" in cov.limited_pages[0].limit_text
    assert "not yet compared across scans" in " ".join(cov.caveats)


def test_a_disabled_probe_is_not_reported_as_a_clean_sweep(
    tmp_db: sqlite3.Connection,
) -> None:
    """ "Off" and "ran, found nothing" must never render the same."""
    scan_id = int(
        tmp_db.execute(
            "INSERT INTO scans (seed_url, status, config_json) VALUES "
            "('https://example.test/', 'completed', ?)",
            (json.dumps({"interaction_checks_enabled": False}),),
        ).lastrowid
    )
    tmp_db.commit()
    cov = interaction_coverage.load(tmp_db, scan_id)
    assert not cov.enabled
    assert "turned off" in cov.status_line
    assert cov.coverage_ratio is None


def test_a_scan_without_a_ledger_does_not_claim_zero_controls(
    tmp_db: sqlite3.Connection,
) -> None:
    """An older scan has no per-page rows; that is unknown, not "nothing to click"."""
    scan_id = int(
        tmp_db.execute(
            "INSERT INTO scans (seed_url, status, config_json, interaction_pages_probed, "
            "interaction_states_total) VALUES ('https://example.test/', 'completed', ?, 3, 7)",
            (json.dumps({"interaction_checks_enabled": True}),),
        ).lastrowid
    )
    tmp_db.commit()
    cov = interaction_coverage.load(tmp_db, scan_id)
    assert not cov.ledger_recorded
    assert cov.coverage_ratio is None
    assert "not recorded" in cov.status_line


def test_a_ledger_missing_newer_columns_degrades_instead_of_crashing(
    tmp_db: sqlite3.Connection,
) -> None:
    """Real scans exist that record coverage_version 2 but predate four columns.

    They were written before the ledger grew ``controls_operated`` and the
    dialog counters, so the version number alone is not a safe gate. An export
    must not raise on them, and must not default the missing numerator to 0 —
    "0 of 10 operated" is a false coverage claim where "not recorded" is true.
    """
    tmp_db.execute("DROP TABLE scan_interaction_runs")
    tmp_db.execute(
        "CREATE TABLE scan_interaction_runs ("
        " scan_id INTEGER NOT NULL, page_id INTEGER NOT NULL,"
        " controls_found INTEGER NOT NULL DEFAULT 0,"
        " clicks_attempted INTEGER NOT NULL DEFAULT 0,"
        " clicks_succeeded INTEGER NOT NULL DEFAULT 0,"
        " states INTEGER NOT NULL DEFAULT 0,"
        " blocked_controls INTEGER NOT NULL DEFAULT 0,"
        " limits TEXT NOT NULL DEFAULT '',"
        " PRIMARY KEY (scan_id, page_id))"
    )
    scan_id = int(
        tmp_db.execute(
            "INSERT INTO scans (seed_url, status, config_json, interaction_pages_probed, "
            "interaction_states_total) VALUES ('https://example.test/', 'completed', ?, 45, 108)",
            (json.dumps({"interaction_checks_enabled": True, "interaction_coverage_version": 2}),),
        ).lastrowid
    )
    tmp_db.commit()

    cov = interaction_coverage.load(tmp_db, scan_id)

    assert cov.enabled
    assert not cov.ledger_recorded
    assert cov.states_total == 108
    assert cov.coverage_ratio is None
    assert "not recorded" in cov.status_line
    assert "0 of" not in cov.status_line
