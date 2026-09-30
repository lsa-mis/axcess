"""Render a scan export exactly as the web export route does, minus the clock.

``GET /api/scans/{id}/export/{fmt}`` in ``audit.web.server`` collects the scan
once, dispatches to one renderer per format, and passes the result through
``label_draft_export``. This helper calls the same public entry points with
the same arguments, and ``tests/ui/test_export_route_parity.py`` checks the
result against a real download. The one difference in order is harmless:
the route collects the scan before its readiness check and this helper
checks first, but the check only reads the evaluation. Only the inputs that
would otherwise vary between runs are pinned: the UI base URL (the request's
base URL in the route), the Markdown generation time, and the workbook's
audit date. The route always passes its blob store to the workbook renderer;
pass ``blob_store`` to do the same, or the workbook embeds no screenshots.

The draft/final disposition is forced rather than derived. The route only
emits a draft when an expert evaluation is incomplete and a final artifact
when it is complete, so a real scan exercises one of the two. Rendering
both for every scan keeps ``label_draft_export`` under test regardless of
the evaluation state recorded in the database. The evaluation status printed
in the draft notice is still the scan's real one.

It deliberately does not import ``audit.web.server``: checkouts before the
lazy-app change built the FastAPI app, and swept the configured database, at
import time. ``scripts/export_diff.py`` must be able to render under such a
base checkout's ``PYTHONPATH`` without touching any database but its copy.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

from audit.blob_store import BlobStore
from audit.exports.audit_report import render_audit_report
from audit.exports.collector import collect_scan
from audit.exports.csv_export import render_csv
from audit.exports.jira_export import render_jira_csv
from audit.exports.json_export import render_json
from audit.exports.markdown_report import render_markdown
from audit.exports.xlsx_export import render_xlsx
from audit.web.export_readiness import (
    PublicExportReadiness,
    assess_public_export_readiness,
    label_draft_export,
)

# The same values the pre-existing goldens were recorded with
# (tests/unit/test_exports_jira_markdown.py and friends).
UI_BASE = "http://127.0.0.1:8765"
GENERATED_AT = datetime(2026, 4, 22, 12, 0, tzinfo=UTC)
AUDIT_DATE = "April 22, 2026"

#: Route format -> file extension, mirroring ``_EXPORT_EXTENSIONS`` in
#: ``audit.web.server``. ``tests/unit/test_export_goldens.py`` fails if the
#: route gains a format this harness does not render.
EXPORT_EXTENSIONS: dict[str, str] = {
    "csv": "csv",
    "json": "json",
    "jira": "jira.csv",
    "markdown": "md",
    "audit": "audit.md",
    "xlsx": "xlsx",
}
EXPORT_FORMATS = tuple(EXPORT_EXTENSIONS)


def evaluation_status(conn: sqlite3.Connection, scan_id: int) -> tuple[str, bool]:
    """Return ``(evaluation_status, route_would_label_draft)`` for ``scan_id``.

    Uses the route's own readiness check with the draft acknowledged, so the
    status matches what a real draft download would print.
    """
    readiness = assess_public_export_readiness(conn, scan_id, draft_acknowledged=True)
    return readiness.evaluation_status, readiness.is_draft


def render_unlabeled(
    conn: sqlite3.Connection,
    scan_id: int,
    export_format: str,
    *,
    blob_store: BlobStore | None = None,
) -> str | bytes:
    """Render one format before draft labeling, as the route's dispatch does."""
    scan = collect_scan(conn, scan_id, ui_base_url=UI_BASE)
    if export_format == "audit":
        return render_audit_report(scan, conn=conn, generated_at=GENERATED_AT)
    if export_format == "xlsx":
        return render_xlsx(scan, conn=conn, audit_date=AUDIT_DATE, blob_store=blob_store)
    if export_format == "markdown":
        return render_markdown(scan, generated_at=GENERATED_AT)
    if export_format == "csv":
        return render_csv(scan)
    if export_format == "json":
        return render_json(scan)
    if export_format == "jira":
        return render_jira_csv(scan)
    raise ValueError(f"Unknown export format: {export_format}")


def label(
    rendered: str | bytes,
    export_format: str,
    *,
    status: str,
    draft: bool,
) -> str | bytes:
    """Apply the route's draft labeling with a forced disposition."""
    readiness = PublicExportReadiness(evaluation_status=status, is_draft=draft)
    return label_draft_export(rendered, export_format=export_format, readiness=readiness)


def render_export(
    conn: sqlite3.Connection,
    scan_id: int,
    export_format: str,
    *,
    draft: bool,
    blob_store: BlobStore | None = None,
) -> str | bytes:
    """Render one export the way the route would, as a draft or a final."""
    status, _ = evaluation_status(conn, scan_id)
    rendered = render_unlabeled(conn, scan_id, export_format, blob_store=blob_store)
    return label(rendered, export_format, status=status, draft=draft)


def export_filename(stem: str, export_format: str, *, draft: bool) -> str:
    """``<stem>[_DRAFT].<ext>``, the naming ``public_export_filename`` uses."""
    marker = "_DRAFT" if draft else ""
    return f"{stem}{marker}.{EXPORT_EXTENSIONS[export_format]}"
