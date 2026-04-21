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
