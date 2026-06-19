"""Typed upsert helpers for the core entity tables.

Every write here is idempotent against the natural key of the row so the
orchestrator can re-process a page on resume without producing duplicates.
"""

from __future__ import annotations

import json
import sqlite3


def upsert_page(
    conn: sqlite3.Connection,
    *,
    scan_id: int,
    url_normalized: str,
    status_code: int | None,
    title: str | None,
    render_mode: str,
    html_hash: str | None,
) -> int:
    """Insert (or update) a page row. Returns its id."""
    cur = conn.execute(
        """
        INSERT INTO pages (scan_id, url_normalized, status_code, title, render_mode, html_hash)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(scan_id, url_normalized) DO UPDATE SET
            status_code = excluded.status_code,
            title = excluded.title,
            render_mode = excluded.render_mode,
            html_hash = excluded.html_hash,
            fetched_at = CURRENT_TIMESTAMP
        RETURNING id
        """,
        (scan_id, url_normalized, status_code, title, render_mode, html_hash),
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


def bulk_set_findings_status(
    conn: sqlite3.Connection,
    *,
    finding_ids: list[int],
    status: str,
    actor: str = "user",
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
    if status not in _VALID_STATUSES:
        raise ValueError(f"Unknown status: {status!r}")
    if not finding_ids:
        return 0
    # Pull current status for each id so finding_history is accurate
    # (the bulk UPDATE later loses the prior value).
    placeholders = ",".join("?" for _ in finding_ids)
    rows = conn.execute(
        f"SELECT id, scan_id, status FROM findings WHERE id IN ({placeholders})",  # noqa: S608 — fixed-shape IN list
        tuple(finding_ids),
    ).fetchall()
    if not rows:
        return 0
    history = [
        (int(r["id"]), int(r["scan_id"]), str(r["status"]), status, actor)
        for r in rows
    ]
    conn.executemany(
        """
        INSERT INTO finding_history
            (finding_id, scan_id, change_type, from_status, to_status, actor, note)
        VALUES (?, ?, 'status_change', ?, ?, ?, NULL)
        """,
        history,
    )
    cur = conn.execute(
        f"""
        UPDATE findings
           SET status = ?, updated_at = CURRENT_TIMESTAMP
         WHERE id IN ({placeholders})
        """,  # noqa: S608 — fixed-shape IN list
        (status, *finding_ids),
    )
    return int(cur.rowcount or 0)


def bulk_set_a11y_findings_status(
    conn: sqlite3.Connection,
    *,
    finding_ids: list[int],
    status: str,
) -> int:
    """Update many ``page_a11y_findings`` rows to the same status.

    Mirrors :func:`bulk_set_findings_status` for the axe pipeline. No
    history table for v1 — same call-out as the single-finding endpoint:
    we can promote ``a11y_finding_history`` later if an audit trail is
    requested. The status enum is validated; empty input is a no-op.
    """
    if status not in _VALID_STATUSES:
        raise ValueError(f"Unknown status: {status!r}")
    if not finding_ids:
        return 0
    placeholders = ",".join("?" for _ in finding_ids)
    cur = conn.execute(
        f"""
        UPDATE page_a11y_findings
           SET status = ?, updated_at = CURRENT_TIMESTAMP
         WHERE id IN ({placeholders})
        """,  # noqa: S608 — fixed-shape IN list
        (status, *finding_ids),
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
            html_snippet, target_hash
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
        ),
    )
    row = conn.execute(
        "SELECT id FROM page_a11y_findings "
        "WHERE page_id = ? AND rule_id = ? AND target_hash = ?",
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
            html_snippet, target_hash, pipeline, criterion_sc
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
            criterion_sc = excluded.criterion_sc,
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
        ),
    )
    row = conn.execute(
        "SELECT id FROM page_a11y_findings "
        "WHERE page_id = ? AND rule_id = ? AND target_hash = ?",
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
        "SELECT id FROM page_a11y_findings "
        "WHERE page_id = ? AND rule_id = ? AND target_hash = ?",
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
