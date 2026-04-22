"""Local review UI — FastAPI + HTMX + Jinja on 127.0.0.1.

All routes are read-mostly against the SQLite audit DB. The only write path
is ``POST /findings/{id}/status``. Server binds to 127.0.0.1 only; no
authentication is provided because this is a single-user local tool.
"""

from __future__ import annotations

import math
import re
import sqlite3
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from fastapi import FastAPI, Form, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from audit import __version__
from audit.blob_store import BlobStore
from audit.config import get_settings
from audit.db.schema import connect
from audit.exports.collector import collect_scan
from audit.exports.csv_export import render_csv
from audit.exports.jira_export import render_jira_csv
from audit.exports.json_export import render_json
from audit.exports.markdown_report import render_markdown
from audit.logging import get_logger
from audit.synthesizer.diff import compute_diff

log = get_logger(__name__)

_STATUS_OPTIONS = (
    "new",
    "reviewing",
    "in_progress",
    "remediated",
    "accepted_risk",
    "false_positive",
)
_CLASSIFICATION_OPTIONS = (
    "essential",
    "informational",
    "logo",
    "decorative",
    "no_meaningful_text",
)
_SEVERITY_OPTIONS = ("critical", "major", "minor", "info")
_DESTRUCTIVE_TRANSITIONS = {"accepted_risk", "false_positive", "remediated"}
_PAGE_SIZE = 50
_CONTENT_HASH_RE = re.compile(r"^[0-9a-f]{64}$")

_EXPORT_RENDERERS: dict[str, Any] = {
    "csv": render_csv,
    "json": render_json,
    "jira": render_jira_csv,
    "markdown": render_markdown,
}
_EXPORT_MEDIA_TYPES = {
    "csv": "text/csv; charset=utf-8",
    "json": "application/json; charset=utf-8",
    "jira": "text/csv; charset=utf-8",
    "markdown": "text/markdown; charset=utf-8",
}
_EXPORT_EXTENSIONS = {"csv": "csv", "json": "json", "jira": "jira.csv", "markdown": "md"}

_BASE_DIR = Path(__file__).resolve().parent
_TEMPLATES_DIR = _BASE_DIR / "templates"
_STATIC_DIR = _BASE_DIR / "static"


def create_app(db_path: Path | None = None, blob_dir: Path | None = None) -> FastAPI:
    """Build the FastAPI app. Accepts overrides so tests can point at tmp paths."""
    settings = get_settings()
    resolved_db = db_path or settings.db_path
    resolved_blob = blob_dir or settings.blob_dir
    blob_store = BlobStore(resolved_blob)

    app = FastAPI(title="Image Text Audit", version=__version__)
    app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")
    templates = Jinja2Templates(directory=_TEMPLATES_DIR)

    def get_conn() -> sqlite3.Connection:
        return connect(resolved_db)

    def render(
        request: Request,
        template: str,
        context: dict[str, Any],
        *,
        partial: str | None = None,
    ) -> HTMLResponse:
        """Render full template normally; render ``partial`` for HTMX requests."""
        chosen = (
            partial
            if partial is not None and request.headers.get("HX-Request") == "true"
            else template
        )
        return templates.TemplateResponse(request, chosen, context)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    @app.get("/", include_in_schema=False)
    def root() -> RedirectResponse:
        return RedirectResponse("/scans", status_code=307)

    @app.get("/scans", response_class=HTMLResponse)
    def scans_list(request: Request) -> HTMLResponse:
        with get_conn() as conn:
            rows = conn.execute(
                "SELECT id, seed_url, status, page_count, finding_count, started_at "
                "FROM scans ORDER BY id DESC"
            ).fetchall()
        return render(
            request,
            "scans.html",
            {"scans": [dict(r) for r in rows], "active": "scans"},
        )

    @app.get("/scans/{scan_id}", response_class=HTMLResponse)
    def scan_detail(request: Request, scan_id: int) -> HTMLResponse:
        with get_conn() as conn:
            scan = _load_scan_or_404(conn, scan_id)
            breakdown = _severity_breakdown(conn, scan_id)
            prev = conn.execute(
                """
                SELECT id FROM scans
                 WHERE seed_url = ? AND id <> ? AND status = 'completed'
                 ORDER BY id DESC LIMIT 1
                """,
                (scan["seed_url"], scan_id),
            ).fetchone()
            previous_scan_id = int(prev["id"]) if prev is not None else None
        return render(
            request,
            "scan_detail.html",
            {
                "scan": scan,
                "by_severity": breakdown,
                "previous_scan_id": previous_scan_id,
                "active": "scan",
            },
        )

    @app.get("/scans/{scan_id}/findings", response_class=HTMLResponse)
    def scan_findings(
        request: Request,
        scan_id: int,
        severity: str = Query(default=""),
        status: str = Query(default=""),
        classification: str = Query(default=""),
        q: str = Query(default=""),
        page: int = Query(default=1, ge=1),
    ) -> HTMLResponse:
        with get_conn() as conn:
            scan = _load_scan_or_404(conn, scan_id)
            filters: dict[str, str] = {
                "severity": severity if severity in _SEVERITY_OPTIONS else "",
                "status": status if status in _STATUS_OPTIONS else "",
                "classification": (
                    classification if classification in _CLASSIFICATION_OPTIONS else ""
                ),
                "q": q,
            }
            findings, total = _query_findings(
                conn, scan_id=scan_id, filters=filters, page=page, size=_PAGE_SIZE
            )
        pagination = _pagination(page=page, size=_PAGE_SIZE, total=total, filters=filters)
        return render(
            request,
            "findings.html",
            {
                "scan": scan,
                "findings": findings,
                "filters": filters,
                "status_options": list(_STATUS_OPTIONS),
                "classification_options": list(_CLASSIFICATION_OPTIONS),
                "pagination": pagination,
                "active": "findings",
            },
            partial="partials/findings_table.html",
        )

    @app.get("/findings/{finding_id}", response_class=HTMLResponse)
    def finding_detail(request: Request, finding_id: int) -> HTMLResponse:
        with get_conn() as conn:
            row = conn.execute(
                """
                SELECT f.id, f.scan_id, f.status, f.severity, f.priority_score,
                       f.remediation_hint, f.wcag_criterion,
                       i.id AS image_id, i.content_hash, i.blob_path, i.mime,
                       i.width, i.height, i.has_svg_text, i.src_url_canonical,
                       a.ocr_text, a.ocr_confidence, a.vlm_classification,
                       a.vlm_rationale
                  FROM findings f
                  JOIN images i ON i.id = f.image_id
                  LEFT JOIN analyses a ON a.image_id = i.id
                 WHERE f.id = ?
                 ORDER BY
                    CASE WHEN a.vlm_classification IS NOT NULL THEN 0 ELSE 1 END,
                    a.analyzed_at DESC
                 LIMIT 1
                """,
                (finding_id,),
            ).fetchone()
            if row is None:
                raise HTTPException(status_code=404, detail="Finding not found")
            finding = dict(row)
            finding["alt_adequacy"] = None
            scan = _load_scan_or_404(conn, int(finding["scan_id"]))
            occurrences = [
                dict(r)
                for r in conn.execute(
                    """
                    SELECT pi.page_id, pi.alt_text, pi.above_fold,
                           p.url_normalized AS page_url
                      FROM page_images pi
                      JOIN pages p ON p.id = pi.page_id
                     WHERE pi.image_id = ? AND p.scan_id = ?
                     ORDER BY pi.position
                    """,
                    (finding["image_id"], finding["scan_id"]),
                ).fetchall()
            ]
        return render(
            request,
            "finding_detail.html",
            {
                "finding": finding,
                "scan": scan,
                "occurrences": occurrences,
                "status_options": list(_STATUS_OPTIONS),
                "active": "findings",
            },
        )

    @app.post("/findings/{finding_id}/status", response_class=HTMLResponse)
    def set_finding_status(
        request: Request,
        finding_id: int,
        status: str = Form(...),
        confirm: str | None = Form(default=None),
    ) -> HTMLResponse:
        if status not in _STATUS_OPTIONS:
            raise HTTPException(status_code=400, detail="Unknown status value")
        with get_conn() as conn:
            existing = conn.execute(
                "SELECT status FROM findings WHERE id = ?", (finding_id,)
            ).fetchone()
            if existing is None:
                raise HTTPException(status_code=404, detail="Finding not found")
            prev = existing["status"]
            if (
                status in _DESTRUCTIVE_TRANSITIONS
                and prev != status
                and confirm != "yes"
                and request.headers.get("HX-Request") == "true"
            ):
                return HTMLResponse(
                    '<span role="alert">Confirm marking as '
                    f"<strong>{status}</strong>. Re-submit with confirm=yes.</span>",
                )
            conn.execute(
                "UPDATE findings SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (status, finding_id),
            )
            conn.execute(
                """
                INSERT INTO finding_history
                    (finding_id, scan_id, change_type, from_status, to_status, actor, note)
                SELECT id, scan_id, 'status_change', ?, ?, 'user', NULL
                  FROM findings WHERE id = ?
                """,
                (prev, status, finding_id),
            )
        if request.headers.get("HX-Request") == "true":
            return HTMLResponse(
                f'<span class="subtle">Status updated to <strong>{status}</strong>.</span>'
            )
        return HTMLResponse(f'<meta http-equiv="refresh" content="0;url=/findings/{finding_id}">')

    @app.get("/pages/{page_id}", response_class=HTMLResponse)
    def page_detail(request: Request, page_id: int) -> HTMLResponse:
        with get_conn() as conn:
            page = conn.execute(
                "SELECT id, scan_id, url_normalized, status_code, title, "
                "render_mode, fetched_at FROM pages WHERE id = ?",
                (page_id,),
            ).fetchone()
            if page is None:
                raise HTTPException(status_code=404, detail="Page not found")
            scan = _load_scan_or_404(conn, int(page["scan_id"]))
            rows = conn.execute(
                """
                SELECT pi.position, pi.alt_text,
                       i.src_url_canonical,
                       f.id AS finding_id, f.severity
                  FROM page_images pi
                  JOIN images i ON i.id = pi.image_id
                  LEFT JOIN findings f ON f.image_id = i.id AND f.scan_id = ?
                 WHERE pi.page_id = ?
                 ORDER BY pi.position
                """,
                (page["scan_id"], page_id),
            ).fetchall()
        enriched = [{**dict(r), "src_url_short": _short_url(r["src_url_canonical"])} for r in rows]
        return render(
            request,
            "page_detail.html",
            {
                "page": dict(page),
                "page_images": enriched,
                "scan": scan,
                "active": "findings",
            },
        )

    @app.get("/scans/{scan_id}/diff", response_class=HTMLResponse)
    def scan_diff(
        request: Request,
        scan_id: int,
        compare_to: int | None = Query(default=None),
    ) -> HTMLResponse:
        with get_conn() as conn:
            scan = _load_scan_or_404(conn, scan_id)
            if compare_to is None:
                prev = conn.execute(
                    """
                    SELECT id FROM scans
                     WHERE seed_url = ? AND id <> ? AND status = 'completed'
                     ORDER BY id DESC LIMIT 1
                    """,
                    (scan["seed_url"], scan_id),
                ).fetchone()
                if prev is None:
                    raise HTTPException(
                        status_code=400,
                        detail="No prior completed scan to compare against.",
                    )
                compare_to = int(prev["id"])
            compare_scan = _load_scan_or_404(conn, compare_to)
            report = compute_diff(conn, current_scan_id=scan_id, compare_to_scan_id=compare_to)
        return render(
            request,
            "diff.html",
            {
                "scan": scan,
                "compare_to": compare_scan,
                "report": report,
                "counts": report.counts,
                "active": "scan",
            },
        )

    @app.get("/scans/{scan_id}/export/{fmt}")
    def export_scan(request: Request, scan_id: int, fmt: str) -> Response:
        """Download a scan export as CSV / JSON / Jira CSV / Markdown."""
        fmt_lower = fmt.lower()
        if fmt_lower not in _EXPORT_RENDERERS:
            raise HTTPException(status_code=400, detail="Unknown export format")
        ui_base = str(request.base_url).rstrip("/")
        with get_conn() as conn:
            try:
                scan = collect_scan(conn, scan_id, ui_base_url=ui_base)
            except ValueError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
        rendered = _EXPORT_RENDERERS[fmt_lower](scan)
        media = _EXPORT_MEDIA_TYPES[fmt_lower]
        ext = _EXPORT_EXTENSIONS[fmt_lower]
        filename = f"scan_{scan_id}.{ext}"
        return Response(
            content=rendered,
            media_type=media,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    @app.get("/blobs/{content_hash}")
    def serve_blob(content_hash: str) -> Response:
        """Serve an image blob by content hash. Hash format is validated."""
        if not _CONTENT_HASH_RE.match(content_hash):
            raise HTTPException(status_code=400, detail="Invalid content hash")
        with get_conn() as conn:
            row = conn.execute(
                "SELECT mime, blob_path FROM images "
                "WHERE content_hash = ? AND blob_path IS NOT NULL",
                (content_hash,),
            ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Blob not found")
        full = blob_store.path_for(row["blob_path"]).resolve()
        try:
            full.relative_to(blob_store.root.resolve())
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Path outside blob root") from exc
        if not full.exists():
            raise HTTPException(status_code=404, detail="Blob file missing")
        return FileResponse(full, media_type=row["mime"] or "application/octet-stream")

    return app


def _load_scan_or_404(conn: sqlite3.Connection, scan_id: int) -> dict[str, Any]:
    row = conn.execute(
        "SELECT id, seed_url, status, page_count, finding_count, error_count, "
        "started_at, finished_at, config_json FROM scans WHERE id = ?",
        (scan_id,),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Scan not found")
    return dict(row)


def _severity_breakdown(conn: sqlite3.Connection, scan_id: int) -> dict[str, int]:
    rows = conn.execute(
        "SELECT severity, COUNT(*) AS n FROM findings WHERE scan_id = ? GROUP BY severity",
        (scan_id,),
    ).fetchall()
    return {r["severity"]: int(r["n"]) for r in rows}


def _query_findings(
    conn: sqlite3.Connection,
    *,
    scan_id: int,
    filters: dict[str, str],
    page: int,
    size: int,
) -> tuple[list[dict[str, Any]], int]:
    clauses = ["f.scan_id = ?"]
    params: list[Any] = [scan_id]
    if filters["severity"]:
        clauses.append("f.severity = ?")
        params.append(filters["severity"])
    if filters["status"]:
        clauses.append("f.status = ?")
        params.append(filters["status"])
    if filters["classification"]:
        clauses.append("a.vlm_classification = ?")
        params.append(filters["classification"])
    if filters["q"]:
        clauses.append("(i.src_url_canonical LIKE ? OR a.ocr_text LIKE ? OR pi.alt_text LIKE ?)")
        like = f"%{filters['q']}%"
        params.extend([like, like, like])
    where = " AND ".join(clauses)

    count_sql = f"""
        SELECT COUNT(DISTINCT f.id) AS n
          FROM findings f
          JOIN images i ON i.id = f.image_id
          LEFT JOIN analyses a ON a.image_id = i.id
          LEFT JOIN page_images pi ON pi.image_id = i.id
         WHERE {where}
    """  # noqa: S608  # `where` built from a closed enum list, not user input
    total = int(conn.execute(count_sql, params).fetchone()["n"])
    offset = (page - 1) * size
    list_sql = f"""
        SELECT DISTINCT f.id, f.severity, f.priority_score, f.status,
               a.vlm_classification, a.ocr_text,
               i.src_url_canonical
          FROM findings f
          JOIN images i ON i.id = f.image_id
          LEFT JOIN analyses a ON a.image_id = i.id
          LEFT JOIN page_images pi ON pi.image_id = i.id
         WHERE {where}
         ORDER BY f.priority_score DESC, f.id ASC
         LIMIT ? OFFSET ?
    """  # noqa: S608
    rows = conn.execute(list_sql, [*params, size, offset]).fetchall()
    findings: list[dict[str, Any]] = []
    for r in rows:
        item = dict(r)
        item["src_url_short"] = _short_url(item["src_url_canonical"])
        item["alt_adequacy"] = None
        findings.append(item)
    return findings, total


def _pagination(*, page: int, size: int, total: int, filters: dict[str, str]) -> dict[str, Any]:
    total_pages = max(1, math.ceil(total / size))
    base = {k: v for k, v in filters.items() if v}
    prev_qs = urlencode({**base, "page": max(1, page - 1)})
    next_qs = urlencode({**base, "page": min(total_pages, page + 1)})
    return {
        "page": page,
        "total_pages": total_pages,
        "total": total,
        "prev_qs": prev_qs,
        "next_qs": next_qs,
    }


def _short_url(url: str | None) -> str:
    if not url:
        return "—"
    if url.startswith("inline-svg://"):
        return "(inline svg)"
    match = re.match(r"^https?://[^/]+(/.*)?$", url)
    if match:
        return match.group(1) or "/"
    return url


# Module-level app instance so `uvicorn audit.web.server:app` works.
app = create_app()
