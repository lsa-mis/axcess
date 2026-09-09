"""Unit tests for the error-identification probe (SC 3.3.1).

The probe's browser step is exercised in the integration suite with real
Playwright. This module pins the parts that don't need a browser: the
``classify`` decision boundary (fed synthetic per-control signal dicts), the
``ErrorIdentificationFinding`` contract, and the ``to_repo_kwargs()``
round-trip through ``upsert_error_id_finding`` (which also proves migration
0028 admits ``pipeline='error_id'``).
"""

from __future__ import annotations

import inspect
import sqlite3
from pathlib import Path

import pytest

from audit.analyzer.error_id import classify
from audit.analyzer.error_id.base import (
    HELP_URL,
    LEVEL,
    RULE_NOT_ASSOCIATED,
    RULE_NOT_IDENTIFIED,
    SC,
    ErrorIdentificationFinding,
)
from audit.db import repo
from audit.db.schema import connect

_MIGRATIONS = Path(__file__).resolve().parents[2] / "src" / "audit" / "db" / "migrations"


@pytest.fixture
def tmp_conn(tmp_path: Path) -> sqlite3.Connection:
    db = tmp_path / "e.db"
    conn = connect(db)
    for path in sorted(_MIGRATIONS.glob("*.sql")):
        if path.name.endswith(".rollback.sql"):
            continue
        conn.executescript(path.read_text())
    return conn


@pytest.fixture
def tmp_scan_and_page(tmp_conn: sqlite3.Connection) -> tuple[sqlite3.Connection, int, int]:
    cur = tmp_conn.execute(
        "INSERT INTO scans (seed_url, status, config_json) VALUES ('http://x/', 'completed', '{}')"
    )
    scan_id = int(cur.lastrowid or 0)
    page_id = repo.upsert_page(
        tmp_conn,
        scan_id=scan_id,
        url_normalized="http://x/form",
        status_code=200,
        title="form",
        render_mode="js",
        html_hash="0" * 64,
    )
    return tmp_conn, scan_id, page_id


# --------------------------------------------------------------------
# Constants + dataclass contract.
# --------------------------------------------------------------------


def test_constants_pin_wcag_sc() -> None:
    assert SC == "3.3.1"
    assert LEVEL == "A"
    assert HELP_URL.endswith("/error-identification.html")


def test_finding_defaults_and_hash() -> None:
    f = ErrorIdentificationFinding(
        rule_id=RULE_NOT_IDENTIFIED,
        target_selector='input[name="email"]',
        failure_summary="no error text",
        html_snippet="<input name=email required>",
        help="add a message",
    )
    assert f.criterion_sc == "3.3.1"
    assert f.wcag_level == "A"
    assert f.impact == "serious"
    # hash changes with selector, stable for identical inputs
    g = ErrorIdentificationFinding(
        rule_id=RULE_NOT_IDENTIFIED,
        target_selector='input[name="phone"]',
        failure_summary="no error text",
        html_snippet="<input name=email required>",
        help="add a message",
    )
    assert f.target_hash != g.target_hash


def test_to_repo_kwargs_matches_upsert_signature() -> None:
    f = ErrorIdentificationFinding(
        rule_id=RULE_NOT_IDENTIFIED,
        target_selector="x",
        failure_summary="y",
        html_snippet="<x/>",
        help="z",
    )
    kwargs = f.to_repo_kwargs()
    assert kwargs["pipeline"] == "error_id"
    sig = inspect.signature(repo.upsert_error_id_finding)
    extras = set(kwargs) - set(sig.parameters)
    assert not extras, f"unknown kwargs: {extras}"


# --------------------------------------------------------------------
# classify() — the decision boundary.
# --------------------------------------------------------------------


def _sig(**kw: object) -> dict:
    base = {
        "selector": "input#a",
        "html": "<input id=a>",
        "noValidate": False,
        "ariaInvalid": False,
        "describedText": "",
        "nearbyErrorText": "",
    }
    base.update(kw)
    return base


def test_associated_error_is_not_flagged() -> None:
    # aria-describedby text present → identified AND associated → conforming.
    out = classify([_sig(describedText="Enter a valid email address")])
    assert out == []


def test_aria_invalid_plus_nearby_text_is_not_flagged() -> None:
    out = classify([_sig(ariaInvalid=True, nearbyErrorText="Required")])
    assert out == []


def test_novalidate_with_no_error_text_is_not_identified() -> None:
    out = classify([_sig(noValidate=True)])
    assert len(out) == 1
    assert out[0].rule_id == RULE_NOT_IDENTIFIED


def test_visible_but_unassociated_error_is_not_associated() -> None:
    # A visible message with no aria linkage → association failure.
    out = classify([_sig(nearbyErrorText="This field is required")])
    assert len(out) == 1
    assert out[0].rule_id == RULE_NOT_ASSOCIATED


def test_native_validation_without_custom_text_is_not_flagged() -> None:
    # Not novalidate, no visible custom error: the browser's own accessible
    # validation is presumed to handle it — conservative, no finding.
    out = classify([_sig(noValidate=False)])
    assert out == []


def test_duplicate_selectors_collapse() -> None:
    out = classify([_sig(noValidate=True), _sig(noValidate=True)])
    assert len(out) == 1


def test_non_dict_items_ignored() -> None:
    assert classify(["nonsense", None, 42]) == []  # type: ignore[list-item]


# --------------------------------------------------------------------
# Round-trip through the real DB (exercises migration 0028).
# --------------------------------------------------------------------


def test_upsert_error_id_finding_tags_pipeline(
    tmp_scan_and_page: tuple[sqlite3.Connection, int, int],
) -> None:
    conn, scan_id, page_id = tmp_scan_and_page
    f = ErrorIdentificationFinding(
        rule_id=RULE_NOT_ASSOCIATED,
        target_selector='input[name="email"]',
        failure_summary="Visible error not tied to field.",
        help="associate it",
        html_snippet='<input name="email">',
    )
    fid = repo.upsert_error_id_finding(conn, page_id=page_id, scan_id=scan_id, **f.to_repo_kwargs())
    assert fid > 0
    row = conn.execute(
        "SELECT pipeline, criterion_sc, wcag_sc, wcag_level, status FROM page_a11y_findings "
        "WHERE id = ?",
        (fid,),
    ).fetchone()
    assert row["pipeline"] == "error_id"
    assert row["criterion_sc"] == "3.3.1"
    assert row["wcag_level"] == "A"
    assert row["status"] == "new"


def test_upsert_error_id_finding_is_idempotent(
    tmp_scan_and_page: tuple[sqlite3.Connection, int, int],
) -> None:
    conn, scan_id, page_id = tmp_scan_and_page
    f = ErrorIdentificationFinding(
        rule_id=RULE_NOT_IDENTIFIED,
        target_selector="input#pw",
        failure_summary="No error text.",
        help="add one",
        html_snippet="<input id=pw>",
    )
    a = repo.upsert_error_id_finding(conn, page_id=page_id, scan_id=scan_id, **f.to_repo_kwargs())
    b = repo.upsert_error_id_finding(conn, page_id=page_id, scan_id=scan_id, **f.to_repo_kwargs())
    assert a == b
    n = conn.execute(
        "SELECT COUNT(*) AS n FROM page_a11y_findings WHERE page_id = ?", (page_id,)
    ).fetchone()["n"]
    assert n == 1
