"""A sign-in scan's end, saved on the scan itself (server._finish_local_login_scan).

Since 2026-11-26 New scan opens a started sign-in scan's own progress page,
as a public scan's, instead of an in-between panel that held the reason a
sign-in scan failed only in memory. The reason is now the scan's own
``failure_reason``, which that page shows ("Why it failed") and which
outlives a restart of Axcess.
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from audit.db.schema import connect
from audit.web import server
from audit.web.server import create_app


def test_a_failed_sign_in_scan_keeps_its_reason(seeded_db: tuple[Path, Path, int]) -> None:
    db_path, blob_dir, scan_id = seeded_db
    reason = (
        "Signed in, but every page Axcess scanned (3) was a sign-in page, so the session "
        "did not carry into the scan."
    )
    server._finish_local_login_scan(db_path, scan_id, "failed", reason)
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT status, failure_reason, finished_at FROM scans WHERE id = ?", (scan_id,)
        ).fetchone()
    assert row[0] == "failed"
    assert row[1] == reason
    assert row[2] is not None
    scan = TestClient(create_app(db_path=db_path, blob_dir=blob_dir)).get(f"/api/scans/{scan_id}")
    assert scan.json()["failure_reason"] == reason


def test_no_reason_leaves_the_saved_one_alone(seeded_db: tuple[Path, Path, int]) -> None:
    db_path, _, scan_id = seeded_db
    with connect(db_path) as conn:
        conn.execute("UPDATE scans SET failure_reason = 'kept' WHERE id = ?", (scan_id,))
        conn.commit()
    server._finish_local_login_scan(db_path, scan_id, "interrupted")
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT status, failure_reason FROM scans WHERE id = ?", (scan_id,)
        ).fetchone()
    assert tuple(row) == ("interrupted", "kept")
