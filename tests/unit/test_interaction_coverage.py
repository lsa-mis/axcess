"""Interaction selection, actual page coverage, and reached states stay distinct."""

import json
import sqlite3
from pathlib import Path

import pytest

from audit.db import repo
from audit.web.server import _methods_used, _scan_method_coverage


@pytest.mark.parametrize(
    ("selected", "version", "pages", "states", "status", "expected_state", "result"),
    [
        (False, 1, 0, 0, "completed", "not_selected", "Not selected"),
        (
            True,
            0,
            0,
            0,
            "completed",
            "coverage_unknown",
            "Coverage not recorded for this older scan",
        ),
        (True, 1, 0, 0, "completed", "not_run", "Selected, but no page checks were recorded"),
        (True, 1, 0, 0, "running", "waiting", "Selected; waiting to run"),
        (True, 1, 2, 0, "completed", "checked", "2 pages checked; 0 DOM states reached"),
        (True, 0, 2, 5, "completed", "checked", "2 pages checked; 5 DOM states reached"),
        (True, 1, 1, 1, "completed", "partial", "1 of 2 pages checked; 1 DOM state reached"),
        (True, 1, 1, 3, "running", "running", "1 page checked so far; 3 DOM states reached"),
    ],
)
def test_interaction_coverage_does_not_infer_work_from_selection(
    selected: bool,
    version: int,
    pages: int,
    states: int,
    status: str,
    expected_state: str,
    result: str,
) -> None:
    methods = _methods_used(
        {
            "status": status,
            "page_count": 2,
            "config_json": json.dumps(
                {
                    "interaction_checks_enabled": selected,
                    "interaction_coverage_version": version,
                }
            ),
            "interaction_pages_probed": pages,
            "interaction_states_total": states,
        },
        {"rendered_pages": 2, "analyzed_images": 0, "discovered_images": 0},
    )
    method = next(item for item in methods if item["key"] == "interaction")
    assert method["state"] == expected_state
    assert method["result"] == result


def methods(coverage: dict[str, int], **scan: object) -> dict[str, object]:
    """Build one interaction method row from explicit, recorded counts."""

    row = {
        "status": "completed",
        "page_count": 2,
        "config_json": json.dumps(
            {
                "interaction_checks_enabled": True,
                "interaction_coverage_version": 2,
                "interaction_safety_version": 1,
            }
        ),
        "interaction_pages_probed": 2,
        "interaction_states_total": 3,
        **scan,
    }
    result = _methods_used(
        row,
        {"rendered_pages": 2, "analyzed_images": 0, "discovered_images": 0, **coverage},
    )
    return next(item for item in result if item["key"] == "interaction")


def test_report_states_operated_controls_not_only_discovered_ones() -> None:
    method = methods(
        {
            "interaction_controls": 52,
            "interaction_operated": 37,
            "interaction_blocked": 6,
            "interaction_limited_pages": 1,
        }
    )
    assert method["result"] == (
        "2 pages checked; 3 DOM states reached; 37 of 52 controls operated; "
        "6 controls skipped as unsafe; exploration limits reached on 1 page"
    )
    assert "not necessarily operated" in method["caveat"]


def test_a_stuck_dialog_is_named_in_the_report_not_folded_into_limits() -> None:
    method = methods(
        {
            "interaction_controls": 12,
            "interaction_operated": 3,
            "interaction_dialogs_stuck": 1,
            "interaction_limited_pages": 1,
        }
    )
    assert "1 dialog would not close, stopping those pages early" in method["result"]
    assert "would not close" in method["caveat"] or "not close" in method["caveat"]


def test_a_page_swept_to_exhaustion_claims_no_limit_and_no_refusal() -> None:
    method = methods({"interaction_controls": 4, "interaction_operated": 4})
    assert method["result"] == "2 pages checked; 3 DOM states reached; 4 of 4 controls operated"


def test_a_scan_without_a_ledger_says_less_rather_than_claiming_zero() -> None:
    """An older report has no per-page rows; that is not "0 controls found"."""

    method = methods({})
    assert method["result"] == "2 pages checked; 3 DOM states reached"
    assert "controls" not in method["result"]


def test_interaction_ledger_is_scan_scoped_and_replaces_a_reprobed_page(
    tmp_db: sqlite3.Connection,
) -> None:
    scans = [
        int(
            tmp_db.execute(
                "INSERT INTO scans (seed_url, status, config_json) "
                "VALUES ('https://example.test/', 'completed', '{}')"
            ).lastrowid
        )
        for _ in range(2)
    ]
    page_id = repo.upsert_page(
        tmp_db,
        scan_id=scans[0],
        url_normalized="https://example.test/",
        status_code=200,
        title="Home",
        render_mode="js",
        html_hash=None,
    )
    ledger = {
        "controls_found": 9,
        "clicks_attempted": 5,
        "clicks_succeeded": 6,
        "controls_operated": 4,
        "states": 3,
        "blocked_controls": 2,
        "limits": ["clicks", "depth"],
        "dialogs_opened": 3,
        "dialogs_stuck": 1,
        "detail": 'Dialog "Filters" opened by "Refine" did not close (tried Escape).',
    }
    repo.record_interaction_run(tmp_db, scan_id=scans[0], page_id=page_id, **ledger)
    repo.record_interaction_run(
        tmp_db, scan_id=scans[0], page_id=page_id, **{**ledger, "controls_operated": 6}
    )
    with pytest.raises(ValueError, match="does not belong"):
        repo.record_interaction_run(tmp_db, scan_id=scans[1], page_id=page_id, **ledger)

    rows = tmp_db.execute(
        "SELECT clicks_succeeded, controls_operated, limits, dialogs_stuck, detail "
        "FROM scan_interaction_runs"
    ).fetchall()
    # Replays inflate the click count; the ratio the report shows must use
    # distinct controls, so both are stored and only one is the numerator.
    assert [tuple(row) for row in rows] == [
        (
            6,
            6,
            "clicks,depth",
            1,
            'Dialog "Filters" opened by "Refine" did not close (tried Escape).',
        ),
    ]
    assert _scan_method_coverage(tmp_db, scans[0])["interaction_dialogs_stuck"] == 1
    assert _scan_method_coverage(tmp_db, scans[0])["interaction_operated"] == 6
    assert _scan_method_coverage(tmp_db, scans[1])["interaction_operated"] == 0

    migration = Path(__file__).parents[2] / "src/audit/db/migrations/0026_interaction_runs"
    tmp_db.executescript(migration.with_suffix(".rollback.sql").read_text())
    tmp_db.executescript(migration.with_suffix(".sql").read_text())
    assert tmp_db.execute("SELECT COUNT(*) FROM scan_interaction_runs").fetchone()[0] == 0
