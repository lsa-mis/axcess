"""Unit tests for the keyboard-probe dataclasses + the repo helper.

The probe itself is dynamic and tested with real Playwright in the
integration suite. This module pins the *contract* between the probe
and the rest of the system: the KeyboardTrap shape, the dedupe hash,
and the to_repo_kwargs() round-trip via upsert_keyboard_finding.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from audit.analyzer.keyboard.base import (
    HELP_URL,
    LEVEL,
    RULE_IFRAME,
    RULE_NO_ESCAPE,
    RULE_STUCK,
    SC,
    KeyboardTrap,
)
from audit.db import repo
from audit.db.schema import connect

_MIGRATIONS = Path(__file__).resolve().parents[2] / "src" / "audit" / "db" / "migrations"


@pytest.fixture
def tmp_conn(tmp_path: Path) -> sqlite3.Connection:
    """A temp DB with every forward migration applied."""
    db = tmp_path / "k.db"
    conn = connect(db)
    for path in sorted(_MIGRATIONS.glob("*.sql")):
        if path.name.endswith(".rollback.sql"):
            continue
        conn.executescript(path.read_text())
    return conn


@pytest.fixture
def tmp_scan_and_page(tmp_conn: sqlite3.Connection) -> tuple[sqlite3.Connection, int, int]:
    cur = tmp_conn.execute(
        "INSERT INTO scans (seed_url, status, config_json) "
        "VALUES ('http://x/', 'completed', '{}')"
    )
    scan_id = int(cur.lastrowid or 0)
    page_id = repo.upsert_page(
        tmp_conn,
        scan_id=scan_id,
        url_normalized="http://x/page",
        status_code=200,
        title="page",
        render_mode="js",
        html_hash="0" * 64,
    )
    return tmp_conn, scan_id, page_id


# --------------------------------------------------------------------
# Constants — pin the SC + rule-id surface.
# --------------------------------------------------------------------


def test_constants_pin_wcag_sc() -> None:
    """SC / level / help URL must not drift silently."""
    assert SC == "2.1.2"
    assert LEVEL == "A"
    assert HELP_URL.endswith("/no-keyboard-trap.html")


def test_rule_ids_are_distinct() -> None:
    """Each rule id is unique — the audit-report YAML keys on them."""
    ids = {RULE_STUCK, RULE_NO_ESCAPE, RULE_IFRAME}
    assert len(ids) == 3


# --------------------------------------------------------------------
# KeyboardTrap dataclass contract.
# --------------------------------------------------------------------


def test_trap_carries_sc_and_level_by_default() -> None:
    """Every trap reports SC 2.1.2 Level A without callers passing them."""
    t = KeyboardTrap(
        rule_id=RULE_STUCK,
        impact="critical",
        target_selector="button#x",
        failure_summary="stuck",
        html_snippet="<button>x</button>",
    )
    assert t.criterion_sc == "2.1.2"
    assert t.wcag_level == "A"
    assert "keyboard" in t.help.lower()


def test_target_hash_is_stable_per_selector() -> None:
    """The dedupe key changes when the (rule, selector, snippet) changes."""
    a = KeyboardTrap(
        rule_id=RULE_STUCK,
        impact="critical",
        target_selector="button#a",
        failure_summary="stuck",
        html_snippet="<button>a</button>",
    )
    b = KeyboardTrap(
        rule_id=RULE_STUCK,
        impact="critical",
        target_selector="button#b",  # different selector
        failure_summary="stuck",
        html_snippet="<button>b</button>",
    )
    c = KeyboardTrap(
        rule_id=RULE_NO_ESCAPE,  # different rule
        impact="critical",
        target_selector="button#a",
        failure_summary="stuck",
        html_snippet="<button>a</button>",
    )
    assert a.target_hash != b.target_hash, "different selector → different hash"
    assert a.target_hash != c.target_hash, "different rule → different hash"
    # Same inputs → same hash (idempotent for re-scans).
    a2 = KeyboardTrap(
        rule_id=RULE_STUCK,
        impact="critical",
        target_selector="button#a",
        failure_summary="stuck",  # failure_summary not part of hash
        html_snippet="<button>a</button>",
    )
    assert a.target_hash == a2.target_hash


def test_to_repo_kwargs_keys_match_upsert_signature() -> None:
    """The kwargs the dataclass emits must exactly satisfy the repo helper."""
    import inspect

    t = KeyboardTrap(
        rule_id=RULE_STUCK,
        impact="critical",
        target_selector="x",
        failure_summary="y",
        html_snippet="<x/>",
    )
    kwargs = t.to_repo_kwargs()
    sig = inspect.signature(repo.upsert_keyboard_finding)
    # Every kwarg the dataclass produces must be acceptable to the helper.
    # The helper also takes page_id + scan_id (which the caller passes
    # separately) and has the `pipeline` param with a default — both
    # accounted for.
    helper_params = set(sig.parameters)
    extras = set(kwargs) - helper_params
    assert not extras, f"to_repo_kwargs emits unknown kwargs: {extras}"
    # And every required arg of the helper must be present in kwargs,
    # except the two passed positionally (conn + page_id + scan_id).
    required = {
        name
        for name, p in sig.parameters.items()
        if p.default is inspect.Parameter.empty
        and p.kind in (inspect.Parameter.KEYWORD_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
        and name not in ("conn", "page_id", "scan_id")
    }
    missing = required - set(kwargs)
    assert not missing, f"to_repo_kwargs missing required helper args: {missing}"


# --------------------------------------------------------------------
# upsert_keyboard_finding — round-trip through the real DB.
# --------------------------------------------------------------------


def test_upsert_keyboard_finding_inserts_with_pipeline_tag(
    tmp_scan_and_page: tuple[sqlite3.Connection, int, int],
) -> None:
    """A new keyboard finding lands with pipeline='keyboard' and criterion_sc='2.1.2'."""
    conn, scan_id, page_id = tmp_scan_and_page
    t = KeyboardTrap(
        rule_id=RULE_STUCK,
        impact="critical",
        target_selector="button#trap",
        failure_summary="Focus stuck after 4 Tabs.",
        html_snippet="<button id='trap'>x</button>",
    )
    fid = repo.upsert_keyboard_finding(
        conn, page_id=page_id, scan_id=scan_id, **t.to_repo_kwargs()
    )
    assert fid > 0
    row = conn.execute(
        "SELECT pipeline, criterion_sc, wcag_sc, wcag_level, impact, rule_id, status "
        "FROM page_a11y_findings WHERE id = ?",
        (fid,),
    ).fetchone()
    assert row is not None
    assert row["pipeline"] == "keyboard"
    assert row["criterion_sc"] == "2.1.2"
    assert row["wcag_sc"] == "2.1.2"
    assert row["wcag_level"] == "A"
    assert row["impact"] == "critical"
    assert row["rule_id"] == RULE_STUCK
    # Brand-new findings default to 'new' so they show up in the
    # Issues view's filter chips.
    assert row["status"] == "new"


def test_upsert_keyboard_finding_is_idempotent(
    tmp_scan_and_page: tuple[sqlite3.Connection, int, int],
) -> None:
    """Re-running a probe on the same page updates, doesn't duplicate."""
    conn, scan_id, page_id = tmp_scan_and_page
    t = KeyboardTrap(
        rule_id=RULE_NO_ESCAPE,
        impact="critical",
        target_selector="[role='dialog']",
        failure_summary="Escape did not release focus.",
        html_snippet="<div role='dialog'>...</div>",
    )
    a = repo.upsert_keyboard_finding(
        conn, page_id=page_id, scan_id=scan_id, **t.to_repo_kwargs()
    )
    b = repo.upsert_keyboard_finding(
        conn, page_id=page_id, scan_id=scan_id, **t.to_repo_kwargs()
    )
    assert a == b, "second upsert should hit the same row id"
    count = conn.execute(
        "SELECT COUNT(*) AS n FROM page_a11y_findings WHERE page_id = ?",
        (page_id,),
    ).fetchone()["n"]
    assert count == 1


def test_upsert_keyboard_finding_preserves_human_status(
    tmp_scan_and_page: tuple[sqlite3.Connection, int, int],
) -> None:
    """A triager who marked a trap accepted_risk shouldn't be bumped back to new."""
    conn, scan_id, page_id = tmp_scan_and_page
    t = KeyboardTrap(
        rule_id=RULE_IFRAME,
        impact="serious",
        target_selector="iframe",
        failure_summary="Untitled iframe.",
        html_snippet="<iframe src='x'/>",
    )
    fid = repo.upsert_keyboard_finding(
        conn, page_id=page_id, scan_id=scan_id, **t.to_repo_kwargs()
    )
    conn.execute(
        "UPDATE page_a11y_findings SET status = 'accepted_risk' WHERE id = ?",
        (fid,),
    )
    # Re-upsert with refreshed metadata
    t_refreshed = KeyboardTrap(
        rule_id=RULE_IFRAME,
        impact="serious",
        target_selector="iframe",
        failure_summary="Untitled iframe (refined wording).",  # changed
        html_snippet="<iframe src='x'/>",
    )
    repo.upsert_keyboard_finding(
        conn, page_id=page_id, scan_id=scan_id, **t_refreshed.to_repo_kwargs()
    )
    row = conn.execute(
        "SELECT status, failure_summary FROM page_a11y_findings WHERE id = ?",
        (fid,),
    ).fetchone()
    # Human's status decision survives; the system-owned wording updates.
    assert row["status"] == "accepted_risk"
    assert "refined" in row["failure_summary"]
