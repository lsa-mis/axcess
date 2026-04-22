"""Unit tests for cross-scan diff.

Seeds two scans into the tmp DB with the same schema the orchestrator
uses, synthesizes findings for each, then exercises
:func:`compute_diff` and :func:`materialize_history`.
"""

from __future__ import annotations

import sqlite3

import pytest

from audit.db import repo
from audit.synthesizer.diff import compute_diff, materialize_history
from audit.synthesizer.findings import synthesize_findings


@pytest.fixture
def seeded(tmp_db: sqlite3.Connection) -> tuple[int, int]:
    """Two scans against the same seed URL with a deliberate diff.

    Scan A: images ``X`` and ``Y`` both on page ``/home``.
    Scan B: image ``X`` still on ``/home`` (adequate alt now),
            image ``Y`` is gone,
            a new image ``Z`` appears on ``/home``.
    """
    seed = "http://example.com/"

    # --- Scan A ---------------------------------------------------------
    a = _new_scan(tmp_db, seed)
    page_a = repo.upsert_page(
        tmp_db,
        scan_id=a,
        url_normalized=f"{seed}home",
        status_code=200,
        title="home",
        render_mode="static",
        html_hash="0" * 64,
    )
    img_x = _seed_image(tmp_db, a, content_hash="x" * 64, mime="image/png")
    img_y = _seed_image(tmp_db, a, content_hash="y" * 64, mime="image/png")
    _occurrence(tmp_db, page_id=page_a, image_id=img_x, alt=None, position=0)
    _occurrence(tmp_db, page_id=page_a, image_id=img_y, alt=None, position=1)
    _analysis(tmp_db, image_id=img_x, ocr="BUY NOW", classification="essential")
    _analysis(tmp_db, image_id=img_y, ocr="GET ONE FREE", classification="informational")
    synthesize_findings(tmp_db, scan_id=a)
    tmp_db.execute("UPDATE scans SET status='completed' WHERE id=?", (a,))

    # --- Scan B ---------------------------------------------------------
    b = _new_scan(tmp_db, seed)
    page_b = repo.upsert_page(
        tmp_db,
        scan_id=b,
        url_normalized=f"{seed}home",
        status_code=200,
        title="home",
        render_mode="static",
        html_hash="1" * 64,
    )
    # X still present but now has adequate alt (re-add same image_id by content_hash).
    img_x_again = _seed_image(tmp_db, b, content_hash="x" * 64, mime="image/png")
    assert img_x_again == img_x  # content_hash is UNIQUE, so image row is reused.
    img_z = _seed_image(tmp_db, b, content_hash="z" * 64, mime="image/png")
    _occurrence(tmp_db, page_id=page_b, image_id=img_x_again, alt="Buy now", position=0)
    _occurrence(tmp_db, page_id=page_b, image_id=img_z, alt=None, position=1)
    _analysis(tmp_db, image_id=img_x_again, ocr="BUY NOW", classification="essential")
    _analysis(tmp_db, image_id=img_z, ocr="LEARN MORE", classification="informational")
    synthesize_findings(tmp_db, scan_id=b)
    tmp_db.execute("UPDATE scans SET status='completed' WHERE id=?", (b,))
    return a, b


def test_compute_diff_buckets_correctly(
    tmp_db: sqlite3.Connection, seeded: tuple[int, int]
) -> None:
    a, b = seeded
    diff = compute_diff(tmp_db, current_scan_id=b, compare_to_scan_id=a)

    new_hashes = {e.content_hash for e in diff.new}
    resolved_hashes = {e.content_hash for e in diff.resolved}
    still_open_hashes = {e.content_hash for e in diff.still_open}

    # Z appeared in B → new.
    assert "z" * 64 in new_hashes
    # Y disappeared → resolved.
    assert "y" * 64 in resolved_hashes
    # X is present in both. Alt is adequate now, but severity drops, not
    # resolved — it still gets a finding (info), so it lives in still_open.
    assert "x" * 64 in still_open_hashes


def test_diff_counts_property(tmp_db: sqlite3.Connection, seeded: tuple[int, int]) -> None:
    a, b = seeded
    diff = compute_diff(tmp_db, current_scan_id=b, compare_to_scan_id=a)
    counts = diff.counts
    assert counts["new"] >= 1
    assert counts["resolved"] >= 1
    assert counts["new"] == len(diff.new)


def test_status_change_bucket_triggers(tmp_db: sqlite3.Connection, seeded: tuple[int, int]) -> None:
    a, b = seeded
    # Reviewer marks the X finding in scan B as in_progress.
    tmp_db.execute(
        """
        UPDATE findings SET status='in_progress'
         WHERE scan_id = ? AND image_id = (SELECT id FROM images WHERE content_hash=?)
        """,
        (b, "x" * 64),
    )
    diff = compute_diff(tmp_db, current_scan_id=b, compare_to_scan_id=a)
    changed_hashes = {e.content_hash for e in diff.status_changed}
    assert "x" * 64 in changed_hashes
    # And it should no longer be in still_open because status differs between scans.
    still_open_hashes = {e.content_hash for e in diff.still_open}
    assert "x" * 64 not in still_open_hashes


def test_materialize_history_is_idempotent(
    tmp_db: sqlite3.Connection, seeded: tuple[int, int]
) -> None:
    a, b = seeded
    first = materialize_history(tmp_db, current_scan_id=b, compare_to_scan_id=a)
    second = materialize_history(tmp_db, current_scan_id=b, compare_to_scan_id=a)

    assert first["first_seen"] >= 1
    assert first["resolved"] >= 1
    assert second == {"first_seen": 0, "resolved": 0}
    rows = tmp_db.execute(
        "SELECT change_type, COUNT(*) AS n FROM finding_history "
        "WHERE scan_id = ? GROUP BY change_type",
        (b,),
    ).fetchall()
    by_type = {r["change_type"]: int(r["n"]) for r in rows}
    assert by_type.get("first_seen", 0) >= 1
    assert by_type.get("resolved", 0) >= 1


def test_synthesize_with_compare_to_writes_history(
    tmp_db: sqlite3.Connection, seeded: tuple[int, int]
) -> None:
    a, b = seeded
    # Clear history so we can re-run synth with compare_to.
    tmp_db.execute("DELETE FROM finding_history WHERE scan_id = ?", (b,))
    result = synthesize_findings(tmp_db, scan_id=b, compare_to=a)
    assert result.first_seen >= 1
    assert result.resolved >= 1


# --------------------------- seeding helpers --------------------------- #


def _new_scan(conn: sqlite3.Connection, seed: str) -> int:
    cur = conn.execute(
        "INSERT INTO scans (seed_url, status, config_json) VALUES (?, 'running', '{}')",
        (seed,),
    )
    return int(cur.lastrowid or 0)


def _seed_image(conn: sqlite3.Connection, scan_id: int, *, content_hash: str, mime: str) -> int:
    return repo.upsert_image(
        conn,
        content_hash=content_hash,
        src_url=f"http://example.com/{content_hash}.png",
        mime=mime,
        bytes_len=100,
        width=10,
        height=10,
        blob_path=f"{content_hash[:2]}/{content_hash}.png",
        has_svg_text=False,
        scan_id=scan_id,
    )


def _occurrence(
    conn: sqlite3.Connection,
    *,
    page_id: int,
    image_id: int,
    alt: str | None,
    position: int,
) -> None:
    repo.upsert_page_image(
        conn,
        page_id=page_id,
        image_id=image_id,
        alt_text=alt,
        role=None,
        context_snippet=None,
        position=position,
        above_fold=False,
    )


def _analysis(
    conn: sqlite3.Connection,
    *,
    image_id: int,
    ocr: str,
    classification: str,
) -> None:
    repo.upsert_analysis(
        conn,
        image_id=image_id,
        ocr_text=ocr,
        ocr_confidence=90.0,
        vlm_classification=classification,
        vlm_rationale="seeded",
        has_text=True,
        model_versions={"ocr": "stub", "vlm": "stub:1", "prompt": "v1-stub"},
    )
