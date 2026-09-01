"""Typed upsert helpers for the core entity tables.

Every write here is idempotent against the natural key of the row so the
orchestrator can re-process a page on resume without producing duplicates.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Literal

from audit.protected.redaction import redact_text


def upsert_page(
    conn: sqlite3.Connection,
    *,
    scan_id: int,
    url_normalized: str,
    status_code: int | None,
    title: str | None,
    render_mode: str,
    html_hash: str | None,
    final_url: str | None = None,
) -> int:
    """Insert (or update) a page row. Returns its id.

    ``final_url`` is where the request actually landed, and is set only when
    a redirect moved it: ``url_normalized`` alone cannot distinguish a page
    that was scanned from one that merely redirected somewhere else.
    """
    cur = conn.execute(
        """
        INSERT INTO pages (
            scan_id, url_normalized, status_code, title, render_mode,
            html_hash, final_url
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(scan_id, url_normalized) DO UPDATE SET
            status_code = excluded.status_code,
            title = excluded.title,
            render_mode = excluded.render_mode,
            html_hash = excluded.html_hash,
            final_url = excluded.final_url,
            fetched_at = CURRENT_TIMESTAMP
        RETURNING id
        """,
        (scan_id, url_normalized, status_code, title, render_mode, html_hash, final_url),
    )
    row = cur.fetchone()
    return int(row["id"])


def upsert_image(
    conn: sqlite3.Connection,
    *,
    content_hash: str,
    src_url: str,
    mime: str | None,
    bytes_len: int | None,
    width: int | None,
    height: int | None,
    blob_path: str | None,
    has_svg_text: bool,
    scan_id: int,
) -> int:
    """Insert (or update) an image row keyed on content_hash. Returns its id.

    On conflict, non-NULL incoming values win for the blob location and
    dimensions so we can later fill gaps from better data (e.g. if the same
    hash was first recorded from an SVG text find with no blob, and then
    re-downloaded as a file).
    """
    conn.execute(
        """
        INSERT INTO images (
            content_hash, src_url_canonical, mime, bytes, width, height,
            blob_path, has_svg_text, first_seen_scan_id
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(content_hash) DO UPDATE SET
            blob_path = COALESCE(excluded.blob_path, images.blob_path),
            mime = COALESCE(excluded.mime, images.mime),
            bytes = COALESCE(excluded.bytes, images.bytes),
            width = COALESCE(excluded.width, images.width),
            height = COALESCE(excluded.height, images.height),
            has_svg_text = MAX(images.has_svg_text, excluded.has_svg_text)
        """,
        (
            content_hash,
            src_url,
            mime,
            bytes_len,
            width,
            height,
            blob_path,
            1 if has_svg_text else 0,
            scan_id,
        ),
    )
    row = conn.execute("SELECT id FROM images WHERE content_hash = ?", (content_hash,)).fetchone()
    return int(row["id"])


def upsert_analysis(
    conn: sqlite3.Connection,
    *,
    image_id: int,
    ocr_text: str | None = None,
    ocr_confidence: float | None = None,
    vlm_classification: str | None = None,
    vlm_rationale: str | None = None,
    has_text: bool = False,
    model_versions: dict[str, str],
) -> int:
    """Record an analysis for ``image_id``, keyed on ``(image_id, model_versions_json)``.

    The model-versions JSON is canonical (sorted keys, no whitespace) so re-runs
    with the same engine version dedupe onto the same row. Fields are merged on
    conflict with ``COALESCE`` so an OCR-only row can later be upgraded in place
    with a VLM classification.
    """
    model_json = json.dumps(model_versions, sort_keys=True, separators=(",", ":"))
    conn.execute(
        """
        INSERT INTO analyses (
            image_id, ocr_text, ocr_confidence,
            vlm_classification, vlm_rationale,
            has_text, model_versions_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(image_id, model_versions_json) DO UPDATE SET
            ocr_text = COALESCE(excluded.ocr_text, analyses.ocr_text),
            ocr_confidence = COALESCE(excluded.ocr_confidence, analyses.ocr_confidence),
            vlm_classification = COALESCE(excluded.vlm_classification, analyses.vlm_classification),
            vlm_rationale = COALESCE(excluded.vlm_rationale, analyses.vlm_rationale),
            has_text = MAX(excluded.has_text, analyses.has_text),
            analyzed_at = CURRENT_TIMESTAMP
        """,
        (
            image_id,
            ocr_text,
            ocr_confidence,
            vlm_classification,
            vlm_rationale,
            1 if has_text else 0,
            model_json,
        ),
    )
    row = conn.execute(
        "SELECT id FROM analyses WHERE image_id = ? AND model_versions_json = ?",
        (image_id, model_json),
    ).fetchone()
    return int(row["id"])


def upsert_finding(
    conn: sqlite3.Connection,
    *,
    image_id: int,
    scan_id: int,
    severity: str,
    priority_score: float,
    remediation_hint: str | None,
    wcag_criterion: str = "1.4.5",
) -> int:
    """Idempotent upsert on ``(image_id, scan_id)``. Returns the finding id.

    Preserves human-set status/notes on repeat runs: only the system-owned
    fields (severity, priority_score, remediation_hint, wcag_criterion) are
    refreshed on conflict.
    """
    conn.execute(
        """
        INSERT INTO findings (
            image_id, scan_id, severity, wcag_criterion, priority_score, remediation_hint
        )
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(image_id, scan_id) DO UPDATE SET
            severity = excluded.severity,
            priority_score = excluded.priority_score,
            remediation_hint = excluded.remediation_hint,
            wcag_criterion = excluded.wcag_criterion,
            updated_at = CURRENT_TIMESTAMP
        """,
        (image_id, scan_id, severity, wcag_criterion, priority_score, remediation_hint),
    )
    row = conn.execute(
        "SELECT id FROM findings WHERE image_id = ? AND scan_id = ?",
        (image_id, scan_id),
    ).fetchone()
    return int(row["id"])


_VALID_STATUSES = frozenset(
    {
        "new",
        "reviewing",
        "in_progress",
        "remediated",
        "accepted_risk",
        "false_positive",
    }
)
_DECISIVE_STATUSES = frozenset({"in_progress", "remediated", "accepted_risk", "false_positive"})
_VALID_HISTORY_ACTORS = frozenset({"system", "user"})
MAX_STATUS_RATIONALE_LENGTH = 2000


def normalize_status_rationale(status: str, rationale: str | None) -> str | None:
    """Validate, bound, and redact a human status-decision rationale.

    A confirmed barrier or terminal disposition needs a defensible reason.
    Non-decisive workflow transitions remain backward-compatible and may omit
    it. Common bearer,
    cookie, token, and identifier shapes are redacted before persistence; API
    responses never return the stored note.
    """

    if status not in _VALID_STATUSES:
        raise ValueError(f"Unknown status: {status!r}")
    if rationale is not None and not isinstance(rationale, str):
        raise ValueError("rationale must be text")
    normalized = rationale.strip() if rationale is not None else ""
    if len(normalized) > MAX_STATUS_RATIONALE_LENGTH:
        raise ValueError(f"rationale must be at most {MAX_STATUS_RATIONALE_LENGTH} characters")
    safe = redact_text(normalized) if normalized else ""
    if len(safe) > MAX_STATUS_RATIONALE_LENGTH:
        safe = safe[:MAX_STATUS_RATIONALE_LENGTH].rstrip()
    if status in _DECISIVE_STATUSES and not safe:
        raise ValueError(
            "A rationale is required for confirmed barriers, remediated, accepted risk, "
            "and false positive decisions."
        )
    return safe or None


def _validate_history_actor(actor: str) -> None:
    if actor not in _VALID_HISTORY_ACTORS:
        raise ValueError("Unknown history actor")


@contextmanager
def _status_transaction(conn: sqlite3.Connection) -> Iterator[None]:
    """Make each status update and its history rows one atomic operation."""

    if conn.in_transaction:
        yield
        return
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield
    except Exception:
        conn.execute("ROLLBACK")
        raise
    else:
        conn.execute("COMMIT")


def bulk_set_findings_status(
    conn: sqlite3.Connection,
    *,
    finding_ids: list[int],
    status: str,
    actor: str = "user",
    rationale: str | None = None,
) -> int:
    """Update many ``findings`` rows to the same status in one transaction.

    Returns the number of rows actually changed. The same status enum
    validation as the single-finding endpoint is applied here so a typo
    can't write garbage into the DB.

    Each affected row also gets a ``finding_history`` row written with
    ``change_type='status_change'`` and the recorded actor — that's the
    durable audit trail. We capture the *previous* status per row so a
    later diff or rollback can reason about transitions correctly even
    when many rows had different starting states.
    """
    note = normalize_status_rationale(status, rationale)
    _validate_history_actor(actor)
    if not finding_ids:
        return 0
    # Pull current status for each id so finding_history is accurate
    # (the bulk UPDATE later loses the prior value).
    placeholders = ",".join("?" for _ in finding_ids)
    select_sql = (
        "SELECT id, scan_id, status FROM findings "  # noqa: S608 — placeholders only
        f"WHERE id IN ({placeholders}) AND status <> ?"
    )
    with _status_transaction(conn):
        rows = conn.execute(select_sql, (*finding_ids, status)).fetchall()
        if not rows:
            return 0
        history = [
            (
                int(row["id"]),
                int(row["scan_id"]),
                str(row["status"]),
                status,
                actor,
                note,
            )
            for row in rows
        ]
        conn.executemany(
            """
            INSERT INTO finding_history
                (finding_id, scan_id, change_type, from_status, to_status, actor, note)
            VALUES (?, ?, 'status_change', ?, ?, ?, ?)
            """,
            history,
        )
        changed_ids = [int(row["id"]) for row in rows]
        changed_placeholders = ",".join("?" for _ in changed_ids)
        cur = conn.execute(
            f"""
            UPDATE findings
               SET status = ?, updated_at = CURRENT_TIMESTAMP
             WHERE id IN ({changed_placeholders})
            """,  # noqa: S608 — fixed-shape IN list
            (status, *changed_ids),
        )
        return int(cur.rowcount or 0)


def bulk_set_a11y_findings_status(
    conn: sqlite3.Connection,
    *,
    finding_ids: list[int],
    status: str,
    actor: str = "user",
    rationale: str | None = None,
) -> int:
    """Update many ``page_a11y_findings`` rows to the same status.

    Mirrors :func:`bulk_set_findings_status` for every page-scoped detection
    pipeline and writes one ``a11y_finding_history`` row per changed finding.
    The status enum is validated; empty input is a no-op.
    """
    note = normalize_status_rationale(status, rationale)
    _validate_history_actor(actor)
    if not finding_ids:
        return 0
    placeholders = ",".join("?" for _ in finding_ids)
    select_sql = (
        "SELECT id, scan_id, status FROM page_a11y_findings "  # noqa: S608 — placeholders only
        f"WHERE id IN ({placeholders}) AND status <> ?"
    )
    with _status_transaction(conn):
        rows = conn.execute(select_sql, (*finding_ids, status)).fetchall()
        if not rows:
            return 0
        history = [
            (
                int(row["id"]),
                int(row["scan_id"]),
                str(row["status"]),
                status,
                actor,
                note,
            )
            for row in rows
        ]
        conn.executemany(
            """
            INSERT INTO a11y_finding_history
                (finding_id, scan_id, change_type, from_status, to_status, actor, note)
            VALUES (?, ?, 'status_change', ?, ?, ?, ?)
            """,
            history,
        )
        changed_ids = [int(row["id"]) for row in rows]
        changed_placeholders = ",".join("?" for _ in changed_ids)
        cur = conn.execute(
            f"""
            UPDATE page_a11y_findings
               SET status = ?, updated_at = CURRENT_TIMESTAMP
             WHERE id IN ({changed_placeholders})
            """,  # noqa: S608 — fixed-shape IN list
            (status, *changed_ids),
        )
        return int(cur.rowcount or 0)


def upsert_axe_violation(
    conn: sqlite3.Connection,
    *,
    page_id: int,
    scan_id: int,
    rule_id: str,
    wcag_sc: str | None,
    wcag_scs: str | None,
    wcag_level: str | None,
    impact: str | None,
    help: str,
    help_url: str,
    target_selector: str,
    failure_summary: str,
    html_snippet: str,
    target_hash: str,
    screenshot_hash: str | None = None,
    revealed_by: str | None = None,
) -> int:
    """Idempotent upsert on ``(page_id, rule_id, target_hash)``.

    Re-running a crawl against the same site updates rule metadata and
    snippet text (axe may have refined its wording between runs) but
    preserves the human-set ``status`` workflow column — so a triager
    who marked something ``accepted_risk`` doesn't get bumped back to
    ``new`` on the next scan.
    """
    conn.execute(
        """
        INSERT INTO page_a11y_findings (
            page_id, scan_id, rule_id, wcag_sc, wcag_scs, wcag_level,
            impact, help, help_url, target_selector, failure_summary,
            html_snippet, target_hash, screenshot_hash, revealed_by
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(page_id, rule_id, target_hash) DO UPDATE SET
            scan_id = excluded.scan_id,
            wcag_sc = excluded.wcag_sc,
            wcag_scs = excluded.wcag_scs,
            wcag_level = excluded.wcag_level,
            impact = excluded.impact,
            help = excluded.help,
            help_url = excluded.help_url,
            target_selector = excluded.target_selector,
            failure_summary = excluded.failure_summary,
            html_snippet = excluded.html_snippet,
            screenshot_hash = excluded.screenshot_hash,
            -- revealed_by is deliberately NOT updated. The load-state
            -- pass runs first, so a finding visible without any
            -- interaction keeps its NULL and is never relabelled as
            -- click-only by a later state that merely still shows it.
            updated_at = CURRENT_TIMESTAMP
        """,
        (
            page_id,
            scan_id,
            rule_id,
            wcag_sc,
            wcag_scs,
            wcag_level,
            impact,
            help,
            help_url,
            target_selector,
            failure_summary,
            html_snippet,
            target_hash,
            screenshot_hash,
            revealed_by,
        ),
    )
    row = conn.execute(
        "SELECT id FROM page_a11y_findings WHERE page_id = ? AND rule_id = ? AND target_hash = ?",
        (page_id, rule_id, target_hash),
    ).fetchone()
    return int(row["id"])


def upsert_keyboard_finding(
    conn: sqlite3.Connection,
    *,
    page_id: int,
    scan_id: int,
    rule_id: str,
    wcag_sc: str | None,
    wcag_scs: str | None,
    wcag_level: str | None,
    impact: str | None,
    help: str,
    help_url: str,
    target_selector: str,
    failure_summary: str,
    html_snippet: str,
    target_hash: str,
    criterion_sc: str,
    pipeline: str = "keyboard",
    screenshot_hash: str | None = None,
) -> int:
    """Idempotent upsert for a keyboard-trap probe finding.

    Same shape as :func:`upsert_axe_violation` — the row format is
    identical — but the natural key carries the ``pipeline='keyboard'``
    discriminator so the UI's Issues view can tag the row's source.
    Mirrors :func:`upsert_semantic_finding`'s design pattern; we use a
    dedicated function (rather than overloading the axe helper) so
    callers don't have to remember to pass the pipeline kwarg, and so
    a future audit of "which call sites write keyboard findings" is
    a single grep instead of a "find all upsert_axe_violation
    callers and check their pipeline arg" exercise.
    """
    conn.execute(
        """
        INSERT INTO page_a11y_findings (
            page_id, scan_id, rule_id, wcag_sc, wcag_scs, wcag_level,
            impact, help, help_url, target_selector, failure_summary,
            html_snippet, target_hash, pipeline, criterion_sc, screenshot_hash
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(page_id, rule_id, target_hash) DO UPDATE SET
            scan_id = excluded.scan_id,
            wcag_sc = excluded.wcag_sc,
            wcag_scs = excluded.wcag_scs,
            wcag_level = excluded.wcag_level,
            impact = excluded.impact,
            help = excluded.help,
            help_url = excluded.help_url,
            target_selector = excluded.target_selector,
            failure_summary = excluded.failure_summary,
            html_snippet = excluded.html_snippet,
            criterion_sc = excluded.criterion_sc,
            screenshot_hash = excluded.screenshot_hash,
            updated_at = CURRENT_TIMESTAMP
        """,
        (
            page_id,
            scan_id,
            rule_id,
            wcag_sc,
            wcag_scs,
            wcag_level,
            impact,
            help,
            help_url,
            target_selector,
            failure_summary,
            html_snippet,
            target_hash,
            pipeline,
            criterion_sc,
            screenshot_hash,
        ),
    )
    row = conn.execute(
        "SELECT id FROM page_a11y_findings WHERE page_id = ? AND rule_id = ? AND target_hash = ?",
        (page_id, rule_id, target_hash),
    ).fetchone()
    return int(row["id"])


def upsert_responsive_finding(
    conn: sqlite3.Connection,
    *,
    page_id: int,
    scan_id: int,
    rule_id: str,
    wcag_sc: str | None,
    wcag_scs: str | None,
    wcag_level: str | None,
    impact: str | None,
    help: str,
    help_url: str,
    target_selector: str,
    failure_summary: str,
    html_snippet: str,
    target_hash: str,
    criterion_sc: str,
    pipeline: str = "responsive",
    screenshot_hash: str | None = None,
) -> int:
    """Idempotent upsert for a responsive/zoom probe finding.

    The row format is identical to the keyboard probe's — both are
    dynamic Playwright probes writing into ``page_a11y_findings`` —
    so this delegates to :func:`upsert_keyboard_finding`, which is
    pipeline-parameterized. A dedicated entry point keeps the
    per-pipeline call-site audit a single grep (the documented
    convention for this module).
    """
    return upsert_keyboard_finding(
        conn,
        page_id=page_id,
        scan_id=scan_id,
        rule_id=rule_id,
        wcag_sc=wcag_sc,
        wcag_scs=wcag_scs,
        wcag_level=wcag_level,
        impact=impact,
        help=help,
        help_url=help_url,
        target_selector=target_selector,
        failure_summary=failure_summary,
        html_snippet=html_snippet,
        target_hash=target_hash,
        criterion_sc=criterion_sc,
        pipeline=pipeline,
        screenshot_hash=screenshot_hash,
    )


def upsert_focus_finding(
    conn: sqlite3.Connection,
    *,
    page_id: int,
    scan_id: int,
    rule_id: str,
    wcag_sc: str | None,
    wcag_scs: str | None,
    wcag_level: str | None,
    impact: str | None,
    help: str,
    help_url: str,
    target_selector: str,
    failure_summary: str,
    html_snippet: str,
    target_hash: str,
    criterion_sc: str,
    pipeline: str = "focus",
    screenshot_hash: str | None = None,
) -> int:
    """Idempotent upsert for a live-page focus probe finding (SC 2.4.11).

    Same row format as the keyboard/responsive probes — delegates to the
    pipeline-parameterized :func:`upsert_keyboard_finding`.
    """
    return upsert_keyboard_finding(
        conn,
        page_id=page_id,
        scan_id=scan_id,
        rule_id=rule_id,
        wcag_sc=wcag_sc,
        wcag_scs=wcag_scs,
        wcag_level=wcag_level,
        impact=impact,
        help=help,
        help_url=help_url,
        target_selector=target_selector,
        failure_summary=failure_summary,
        html_snippet=html_snippet,
        target_hash=target_hash,
        criterion_sc=criterion_sc,
        pipeline=pipeline,
        screenshot_hash=screenshot_hash,
    )


def upsert_visual_finding(
    conn: sqlite3.Connection,
    *,
    page_id: int,
    scan_id: int,
    rule_id: str,
    wcag_sc: str | None,
    wcag_scs: str | None,
    wcag_level: str | None,
    impact: str | None,
    help: str,
    help_url: str,
    target_selector: str,
    failure_summary: str,
    html_snippet: str,
    target_hash: str,
    criterion_sc: str,
    pipeline: str = "visual",
    screenshot_hash: str | None = None,
) -> int:
    """Idempotent upsert for a visual (VLM) probe finding (SC 1.3.2).

    Same row format as the other dynamic-probe pipelines — delegates to the
    pipeline-parameterized :func:`upsert_keyboard_finding`.
    """
    return upsert_keyboard_finding(
        conn,
        page_id=page_id,
        scan_id=scan_id,
        rule_id=rule_id,
        wcag_sc=wcag_sc,
        wcag_scs=wcag_scs,
        wcag_level=wcag_level,
        impact=impact,
        help=help,
        help_url=help_url,
        target_selector=target_selector,
        failure_summary=failure_summary,
        html_snippet=html_snippet,
        target_hash=target_hash,
        criterion_sc=criterion_sc,
        pipeline=pipeline,
        screenshot_hash=screenshot_hash,
    )


def upsert_semantic_finding(
    conn: sqlite3.Connection,
    *,
    page_id: int,
    scan_id: int,
    criterion_sc: str,
    wcag_level: str | None,
    impact: str | None,
    help: str,
    target_selector: str,
    failure_summary: str,
    html_snippet: str,
    target_hash: str,
    wcag_scs: str | None = None,
    help_url: str | None = None,
) -> int:
    """Idempotent upsert for a per-criterion semantic finding.

    Writes to ``page_a11y_findings`` with ``pipeline='semantic'``.
    Mirrors :func:`upsert_axe_violation` deliberately — same table,
    same dedupe shape, same preservation-of-human-state-on-conflict
    semantics — but the natural key here is
    ``(page_id, criterion_sc, target_hash)`` instead of
    ``(page_id, rule_id, target_hash)`` because semantic analyzers
    don't have an axe-style ``rule_id``; they have a WCAG SC and a
    targeted element. We pack the criterion into the existing
    ``rule_id`` column too so the UI's "rule" filter still works
    without a special case.

    A re-run of the same analyzer against the same page upserts (the
    LLM may have refined its wording); the human-set ``status``
    workflow column is preserved.
    """
    rule_id = f"semantic:{criterion_sc}"
    conn.execute(
        """
        INSERT INTO page_a11y_findings (
            page_id, scan_id, rule_id, wcag_sc, wcag_scs, wcag_level,
            impact, help, help_url, target_selector, failure_summary,
            html_snippet, target_hash, pipeline, criterion_sc
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'semantic', ?)
        ON CONFLICT(page_id, rule_id, target_hash) DO UPDATE SET
            scan_id = excluded.scan_id,
            wcag_sc = excluded.wcag_sc,
            wcag_scs = excluded.wcag_scs,
            wcag_level = excluded.wcag_level,
            impact = excluded.impact,
            help = excluded.help,
            help_url = excluded.help_url,
            target_selector = excluded.target_selector,
            failure_summary = excluded.failure_summary,
            html_snippet = excluded.html_snippet,
            criterion_sc = excluded.criterion_sc,
            updated_at = CURRENT_TIMESTAMP
        """,
        (
            page_id,
            scan_id,
            rule_id,
            criterion_sc,
            wcag_scs,
            wcag_level,
            impact,
            help,
            help_url,
            target_selector,
            failure_summary,
            html_snippet,
            target_hash,
            criterion_sc,
        ),
    )
    row = conn.execute(
        "SELECT id FROM page_a11y_findings WHERE page_id = ? AND rule_id = ? AND target_hash = ?",
        (page_id, rule_id, target_hash),
    ).fetchone()
    return int(row["id"])


def increment_scan_axe_counters(
    conn: sqlite3.Connection,
    *,
    scan_id: int,
    pages_delta: int = 0,
    violations_delta: int = 0,
) -> None:
    """Bump the denormalized axe counters on the ``scans`` row.

    Used to keep ``scans.axe_pages_scanned`` and
    ``scans.axe_violations_total`` correct without a join when the
    scan-list view renders.
    """
    if pages_delta == 0 and violations_delta == 0:
        return
    conn.execute(
        """
        UPDATE scans
           SET axe_pages_scanned = axe_pages_scanned + ?,
               axe_violations_total = axe_violations_total + ?
         WHERE id = ?
        """,
        (pages_delta, violations_delta, scan_id),
    )


def increment_scan_alfa_counters(
    conn: sqlite3.Connection,
    *,
    scan_id: int,
    pages_delta: int = 0,
    failed_delta: int = 0,
    cant_tell_delta: int = 0,
) -> None:
    """Bump the independent Siteimprove Alfa coverage counters.

    ``cantTell`` is not a failure in ACT. It gets a separate counter so
    reports and exports can distinguish a deterministic finding from a lead
    that needs an expert answer.
    """
    if pages_delta == 0 and failed_delta == 0 and cant_tell_delta == 0:
        return
    conn.execute(
        """
        UPDATE scans
           SET alfa_pages_scanned = alfa_pages_scanned + ?,
               alfa_failed_total = alfa_failed_total + ?,
               alfa_cant_tell_total = alfa_cant_tell_total + ?
         WHERE id = ?
        """,
        (pages_delta, failed_delta, cant_tell_delta, scan_id),
    )


def increment_scan_method_coverage(
    conn: sqlite3.Connection,
    *,
    scan_id: int,
    method: Literal["semantic", "keyboard", "responsive"],
    pages_delta: int = 1,
) -> None:
    """Record pages actually evaluated by a non-engine scan method.

    ``method`` is a closed literal mapped to a trusted column name; callers
    cannot supply SQL.  Counting completed evaluations separately from
    findings lets reports distinguish "checked and found no issue" from
    "selected but never ran".
    """

    if pages_delta == 0:
        return
    columns = {
        "semantic": "semantic_pages_analyzed",
        "keyboard": "keyboard_pages_probed",
        "responsive": "responsive_pages_probed",
    }
    column = columns[method]
    conn.execute(
        f"UPDATE scans SET {column} = {column} + ? WHERE id = ?",  # noqa: S608
        (pages_delta, scan_id),
    )


def upsert_alfa_finding(
    conn: sqlite3.Connection,
    *,
    page_id: int,
    scan_id: int,
    rule_id: str,
    wcag_sc: str | None,
    wcag_scs: str | None,
    wcag_level: str | None,
    help: str,
    help_url: str,
    target_selector: str,
    failure_summary: str,
    html_snippet: str,
    target_hash: str,
    engine_outcome: str,
    engine_evidence_json: str,
) -> int:
    """Idempotently persist a Siteimprove Alfa actionable ACT outcome.

    Alfa's rule identifiers are engine-qualified by ``pipeline='alfa'`` and
    its outcome is retained verbatim enough to separate ``failed`` from
    ``cant_tell``. ``impact`` stays NULL: Alfa does not supply axe-compatible
    impact labels, and assigning one here would manufacture severity.
    """
    conn.execute(
        """
        INSERT INTO page_a11y_findings (
            page_id, scan_id, rule_id, wcag_sc, wcag_scs, wcag_level,
            impact, help, help_url, target_selector, failure_summary,
            html_snippet, target_hash, pipeline, criterion_sc,
            engine_outcome, engine_evidence_json
        )
        VALUES (?, ?, ?, ?, ?, ?, NULL, ?, ?, ?, ?, ?, ?, 'alfa', ?, ?, ?)
        ON CONFLICT(page_id, rule_id, target_hash) DO UPDATE SET
            scan_id = excluded.scan_id,
            wcag_sc = excluded.wcag_sc,
            wcag_scs = excluded.wcag_scs,
            wcag_level = excluded.wcag_level,
            help = excluded.help,
            help_url = excluded.help_url,
            target_selector = excluded.target_selector,
            failure_summary = excluded.failure_summary,
            html_snippet = excluded.html_snippet,
            criterion_sc = excluded.criterion_sc,
            engine_outcome = excluded.engine_outcome,
            engine_evidence_json = excluded.engine_evidence_json,
            updated_at = CURRENT_TIMESTAMP
        """,
        (
            page_id,
            scan_id,
            rule_id,
            wcag_sc,
            wcag_scs,
            wcag_level,
            help,
            help_url,
            target_selector,
            failure_summary,
            html_snippet,
            target_hash,
            wcag_sc,
            engine_outcome,
            engine_evidence_json,
        ),
    )
    row = conn.execute(
        "SELECT id FROM page_a11y_findings WHERE page_id = ? AND rule_id = ? AND target_hash = ?",
        (page_id, rule_id, target_hash),
    ).fetchone()
    return int(row["id"])


def upsert_page_image(
    conn: sqlite3.Connection,
    *,
    page_id: int,
    image_id: int,
    alt_text: str | None,
    role: str | None,
    context_snippet: str | None,
    position: int,
    bbox: dict[str, float] | None = None,
    above_fold: bool = False,
) -> None:
    """Idempotent upsert on (page_id, image_id, position)."""
    conn.execute(
        """
        INSERT INTO page_images (
            page_id, image_id, alt_text, role, context_snippet,
            position, bbox_json, above_fold
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(page_id, image_id, position) DO UPDATE SET
            alt_text = excluded.alt_text,
            role = excluded.role,
            context_snippet = excluded.context_snippet,
            bbox_json = excluded.bbox_json,
            above_fold = excluded.above_fold
        """,
        (
            page_id,
            image_id,
            alt_text,
            role,
            context_snippet,
            position,
            json.dumps(bbox, sort_keys=True) if bbox else None,
            1 if above_fold else 0,
        ),
    )
