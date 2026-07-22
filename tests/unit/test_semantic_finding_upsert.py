"""Tests for ``repo.upsert_semantic_finding`` + the 0003 migration shape.

The contract being pinned:

* Existing axe rows default to ``pipeline='axe'`` after the migration —
  no UI/exports breakage on existing scans.
* New semantic rows write with ``pipeline='semantic'`` and the criterion
  is stored on the dedicated ``criterion_sc`` column.
* Re-upsert with the same ``(page_id, criterion_sc, target_hash)`` key
  updates the wording but does NOT create a new row.
* Different ``target_hash`` on the same page creates a new row.
* Human-set ``status`` survives an upsert (we never bump a triaged
  finding back to ``new``).
"""

from __future__ import annotations

import sqlite3

from audit.db import repo


def _seed_scan_page(conn: sqlite3.Connection) -> tuple[int, int]:
    cur = conn.execute(
        "INSERT INTO scans (seed_url, status, config_json) VALUES ('http://x/', 'completed', '{}')"
    )
    scan_id = int(cur.lastrowid or 0)
    page_id = repo.upsert_page(
        conn,
        scan_id=scan_id,
        url_normalized="http://x/",
        status_code=200,
        title="x",
        render_mode="js",
        html_hash="0" * 64,
    )
    return scan_id, page_id


def test_migration_adds_pipeline_column_with_default_axe(
    tmp_db: sqlite3.Connection,
) -> None:
    """Existing-shape axe insert is still legal; the column defaults
    to 'axe' without explicit value."""
    scan_id, page_id = _seed_scan_page(tmp_db)
    fid = repo.upsert_axe_violation(
        tmp_db,
        page_id=page_id,
        scan_id=scan_id,
        rule_id="color-contrast",
        wcag_sc="1.4.3",
        wcag_scs="1.4.3",
        wcag_level="AA",
        impact="serious",
        help="Elements must have sufficient color contrast",
        help_url="https://dequeuniversity.com/rules/axe/4.10/color-contrast",
        target_selector="p.muted",
        failure_summary="contrast 2.1:1",
        html_snippet='<p class="muted">x</p>',
        target_hash="h-axe",
    )
    row = tmp_db.execute(
        "SELECT pipeline, criterion_sc FROM page_a11y_findings WHERE id = ?",
        (fid,),
    ).fetchone()
    assert row["pipeline"] == "axe"
    assert row["criterion_sc"] is None


def test_upsert_semantic_finding_writes_pipeline_and_criterion(
    tmp_db: sqlite3.Connection,
) -> None:
    """Semantic upsert sets pipeline + criterion_sc + synthetic rule_id."""
    scan_id, page_id = _seed_scan_page(tmp_db)
    fid = repo.upsert_semantic_finding(
        tmp_db,
        page_id=page_id,
        scan_id=scan_id,
        criterion_sc="2.4.4",
        wcag_level="A",
        impact="serious",
        help="Link text 'click here' is not descriptive",
        target_selector="a.cta",
        failure_summary="Link reads 'click here' — gives no purpose context",
        html_snippet='<a href="/x" class="cta">click here</a>',
        target_hash="h-sem-1",
        wcag_scs="2.4.4",
        help_url=None,
    )
    row = tmp_db.execute(
        "SELECT pipeline, criterion_sc, rule_id, status FROM page_a11y_findings WHERE id = ?",
        (fid,),
    ).fetchone()
    assert row["pipeline"] == "semantic"
    assert row["criterion_sc"] == "2.4.4"
    # Synthetic rule_id participates in the existing UNIQUE constraint.
    assert row["rule_id"] == "semantic:2.4.4"
    # Status defaults match every other finding kind.
    assert row["status"] == "new"


def test_upsert_semantic_finding_is_idempotent_on_same_key(
    tmp_db: sqlite3.Connection,
) -> None:
    """Re-upsert returns the same id; help text DOES refresh."""
    scan_id, page_id = _seed_scan_page(tmp_db)
    first = repo.upsert_semantic_finding(
        tmp_db,
        page_id=page_id,
        scan_id=scan_id,
        criterion_sc="2.4.4",
        wcag_level="A",
        impact="serious",
        help="Original wording",
        target_selector="a.cta",
        failure_summary="",
        html_snippet="<a>click here</a>",
        target_hash="h-same",
    )
    second = repo.upsert_semantic_finding(
        tmp_db,
        page_id=page_id,
        scan_id=scan_id,
        criterion_sc="2.4.4",
        wcag_level="A",
        impact="serious",
        help="Refined wording from a newer model run",
        target_selector="a.cta",
        failure_summary="",
        html_snippet="<a>click here</a>",
        target_hash="h-same",
    )
    assert first == second
    row = tmp_db.execute("SELECT help FROM page_a11y_findings WHERE id = ?", (first,)).fetchone()
    assert "Refined wording" in row["help"]


def test_upsert_semantic_finding_different_target_creates_new_row(
    tmp_db: sqlite3.Connection,
) -> None:
    """Different target_hash → second row, not an upsert."""
    scan_id, page_id = _seed_scan_page(tmp_db)
    a = repo.upsert_semantic_finding(
        tmp_db,
        page_id=page_id,
        scan_id=scan_id,
        criterion_sc="2.4.4",
        wcag_level="A",
        impact="serious",
        help="link A",
        target_selector="a.one",
        failure_summary="",
        html_snippet="<a>one</a>",
        target_hash="h-a",
    )
    b = repo.upsert_semantic_finding(
        tmp_db,
        page_id=page_id,
        scan_id=scan_id,
        criterion_sc="2.4.4",
        wcag_level="A",
        impact="serious",
        help="link B",
        target_selector="a.two",
        failure_summary="",
        html_snippet="<a>two</a>",
        target_hash="h-b",
    )
    assert a != b
    n = tmp_db.execute(
        "SELECT COUNT(*) AS n FROM page_a11y_findings "
        "WHERE pipeline = 'semantic' AND criterion_sc = '2.4.4'"
    ).fetchone()["n"]
    assert n == 2


def test_upsert_semantic_finding_preserves_human_status_on_conflict(
    tmp_db: sqlite3.Connection,
) -> None:
    """Triager set status=accepted_risk; re-running the analyzer must
    NOT bump it back to 'new'. Same contract as the axe upsert."""
    scan_id, page_id = _seed_scan_page(tmp_db)
    fid = repo.upsert_semantic_finding(
        tmp_db,
        page_id=page_id,
        scan_id=scan_id,
        criterion_sc="2.4.4",
        wcag_level="A",
        impact="serious",
        help="x",
        target_selector="a",
        failure_summary="",
        html_snippet="<a>x</a>",
        target_hash="h-status",
    )
    # Operator triages.
    tmp_db.execute(
        "UPDATE page_a11y_findings SET status = 'accepted_risk' WHERE id = ?",
        (fid,),
    )
    # Re-run analyzer with the same key.
    repo.upsert_semantic_finding(
        tmp_db,
        page_id=page_id,
        scan_id=scan_id,
        criterion_sc="2.4.4",
        wcag_level="A",
        impact="serious",
        help="x (rerun)",
        target_selector="a",
        failure_summary="",
        html_snippet="<a>x</a>",
        target_hash="h-status",
    )
    row = tmp_db.execute("SELECT status FROM page_a11y_findings WHERE id = ?", (fid,)).fetchone()
    assert row["status"] == "accepted_risk"


def test_pipeline_filter_query(tmp_db: sqlite3.Connection) -> None:
    """The (scan_id, pipeline) index supports the filter the Issues
    view will use."""
    scan_id, page_id = _seed_scan_page(tmp_db)
    repo.upsert_axe_violation(
        tmp_db,
        page_id=page_id,
        scan_id=scan_id,
        rule_id="color-contrast",
        wcag_sc="1.4.3",
        wcag_scs="1.4.3",
        wcag_level="AA",
        impact="serious",
        help="x",
        help_url="",
        target_selector="p",
        failure_summary="",
        html_snippet="<p>x</p>",
        target_hash="h-1",
    )
    repo.upsert_semantic_finding(
        tmp_db,
        page_id=page_id,
        scan_id=scan_id,
        criterion_sc="2.4.4",
        wcag_level="A",
        impact="serious",
        help="x",
        target_selector="a",
        failure_summary="",
        html_snippet="<a>x</a>",
        target_hash="h-2",
    )
    axe_count = tmp_db.execute(
        "SELECT COUNT(*) AS n FROM page_a11y_findings WHERE scan_id = ? AND pipeline = 'axe'",
        (scan_id,),
    ).fetchone()["n"]
    semantic_count = tmp_db.execute(
        "SELECT COUNT(*) AS n FROM page_a11y_findings WHERE scan_id = ? AND pipeline = 'semantic'",
        (scan_id,),
    ).fetchone()["n"]
    assert axe_count == 1
    assert semantic_count == 1


def test_upsert_axe_violation_round_trips_screenshot_hash(
    tmp_db: sqlite3.Connection,
) -> None:
    """The 0008 ``screenshot_hash`` column persists and is readable back."""
    scan_id, page_id = _seed_scan_page(tmp_db)
    fid = repo.upsert_axe_violation(
        tmp_db,
        page_id=page_id,
        scan_id=scan_id,
        rule_id="color-contrast",
        wcag_sc="1.4.3",
        wcag_scs="1.4.3",
        wcag_level="AA",
        impact="serious",
        help="x",
        help_url="",
        target_selector="p",
        failure_summary="",
        html_snippet="<p>x</p>",
        target_hash="h-shot",
        screenshot_hash="abc123",
    )
    row = tmp_db.execute(
        "SELECT screenshot_hash FROM page_a11y_findings WHERE id = ?",
        (fid,),
    ).fetchone()
    assert row["screenshot_hash"] == "abc123"


def test_upsert_keyboard_finding_round_trips_screenshot_hash(
    tmp_db: sqlite3.Connection,
) -> None:
    """The shared keyboard/responsive/focus/visual upsert threads the hash too."""
    scan_id, page_id = _seed_scan_page(tmp_db)
    fid = repo.upsert_keyboard_finding(
        tmp_db,
        page_id=page_id,
        scan_id=scan_id,
        rule_id="keyboard-trap-stuck",
        wcag_sc="2.1.2",
        wcag_scs="2.1.2",
        wcag_level="A",
        impact="serious",
        help="x",
        help_url="",
        target_selector="button",
        failure_summary="",
        html_snippet="<button>x</button>",
        target_hash="h-kbd",
        criterion_sc="2.1.2",
        screenshot_hash="def456",
    )
    row = tmp_db.execute(
        "SELECT screenshot_hash FROM page_a11y_findings WHERE id = ?",
        (fid,),
    ).fetchone()
    assert row["screenshot_hash"] == "def456"
