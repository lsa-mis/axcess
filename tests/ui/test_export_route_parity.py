"""The export harness renders exactly what the export route serves.

``tests/support/export_render.py`` reproduces ``GET /api/scans/{id}/export/{fmt}``
without the FastAPI app, so the export goldens and ``scripts/export_diff.py``
can render under any checkout. Its fidelity to the route was argued in its
docstring; this checks it. The rich golden scan is downloaded through the
real route (its blob store included) and compared with the harness render:
byte for byte for CSV, Jira CSV and JSON, by fingerprint for the workbook,
and for Markdown and the audit report with only the generation timestamp
removed, because the route does not pin the clock.

The client's base URL is the harness's pinned UI base, and the scan's finish
date is the pinned audit date, so everything else the route derives matches
without patching. The rich scan's evaluation is in progress, so the route
serves the acknowledged draft; a final is the same render, which
``label_draft_export`` returns unchanged.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from support.export_render import (
    EXPORT_FORMATS,
    UI_BASE,
    export_filename,
    render_export,
)
from support.rich_scan import database_path, seed_rich_scan, write_evidence_blobs
from support.xlsx_fingerprint import fingerprint_diff, fingerprint_xlsx

from audit.web.server import create_app


def _without_generated_line(text: str) -> str:
    return "\n".join(line for line in text.split("\n") if not line.startswith("_Generated "))


@pytest.mark.parametrize("export_format", EXPORT_FORMATS)
def test_harness_matches_the_route_download(
    tmp_db: sqlite3.Connection,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    export_format: str,
) -> None:
    monkeypatch.delenv("AUDIT_ACCESS_TOKEN", raising=False)
    scan_id = seed_rich_scan(tmp_db)
    tmp_db.commit()
    blobs = write_evidence_blobs(tmp_path / "blobs")
    client = TestClient(
        create_app(db_path=database_path(tmp_db), blob_dir=blobs.root), base_url=UI_BASE
    )

    response = client.get(
        f"/api/scans/{scan_id}/export/{export_format}", params={"draft": "acknowledged"}
    )
    assert response.status_code == 200, response.text
    assert response.headers["X-Axcess-Export-State"] == "draft"
    filename = export_filename(f"scan_{scan_id}", export_format, draft=True)
    assert response.headers["Content-Disposition"] == f'attachment; filename="{filename}"'

    harness = render_export(tmp_db, scan_id, export_format, draft=True, blob_store=blobs)
    if export_format == "xlsx":
        assert isinstance(harness, bytes)
        served = fingerprint_xlsx(response.content)
        # The route's evidence embedding is in play, not just the harness's.
        assert sum(len(sheet["images"]) for sheet in served["sheets"]) == 2
        diff = fingerprint_diff(fingerprint_xlsx(harness), served, labels=("harness", "route"))
        assert not diff, "\n".join(diff)
        return
    assert isinstance(harness, str)
    served_text = response.content.decode("utf-8")
    if export_format in {"markdown", "audit"}:
        assert served_text.count("\n_Generated ") == 1
        assert _without_generated_line(served_text) == _without_generated_line(harness)
    else:
        assert served_text == harness
