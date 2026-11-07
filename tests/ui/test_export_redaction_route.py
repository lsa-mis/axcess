"""``?redact=true`` on the export routes: a redacted copy, for download only.

Private details seeded into the scan's stored evidence must be gone from
every downloaded format, and still be in the report the app shows: the
redaction applies to exports only.
"""

from __future__ import annotations

import io
import json
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from openpyxl import load_workbook

from audit.exports.redaction import REDACTION_NOTICE

from ._seed_evidence import add_screenshot_finding

_EMAIL = "jane.doe@example.com"
_PHONE = "555-123-4567"
_FIELD_VALUE = "4111 1111 1111 1111"
_SELECTOR = "form#pay input[name=card]"
_FORMATS = ("xlsx", "audit", "csv", "json", "markdown", "jira")


def _seed_private_details(db_path: Path, scan_id: int) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "UPDATE analyses SET ocr_text = ? WHERE image_id IN "
            "(SELECT image_id FROM findings WHERE scan_id = ?)",
            (f"Welcome back {_EMAIL}, call {_PHONE}", scan_id),
        )
        (page_id,) = conn.execute(
            "SELECT id FROM pages WHERE scan_id = ? ORDER BY id LIMIT 1", (scan_id,)
        ).fetchone()
        conn.execute(
            """
            INSERT INTO page_a11y_findings (
                page_id, scan_id, rule_id, help, target_selector, target_hash,
                html_snippet, failure_summary, status, created_at, updated_at,
                engine_outcome, pipeline, wcag_sc, wcag_level, impact
            ) VALUES (?, ?, 'label', 'Form elements must have labels', ?,
                      'seeded-private', ?, ?, 'new', CURRENT_TIMESTAMP,
                      CURRENT_TIMESTAMP, 'failed', 'axe', '4.1.2', 'A', 'critical')
            """,
            (
                page_id,
                scan_id,
                _SELECTOR,
                f'<input name="card" value="{_FIELD_VALUE}" data-owner="{_EMAIL}">',
                f"Fix any of the following: Form element for {_EMAIL} has no label",
            ),
        )


def _text_of(fmt: str, content: bytes) -> str:
    if fmt != "xlsx":
        return content.decode("utf-8")
    workbook = load_workbook(io.BytesIO(content))
    return "\n".join(
        str(cell.value)
        for sheet in workbook.worksheets
        for row in sheet.iter_rows()
        for cell in row
        if cell.value is not None
    )


@pytest.mark.parametrize("fmt", _FORMATS)
def test_redacted_download_removes_private_details_and_keeps_what_a_fix_needs(
    client: TestClient, seeded_db: tuple[Path, Path, int], fmt: str
) -> None:
    db_path, _, scan_id = seeded_db
    _seed_private_details(db_path, scan_id)

    full = client.get(f"/api/scans/{scan_id}/export/{fmt}", params={"draft": "acknowledged"})
    redacted = client.get(
        f"/api/scans/{scan_id}/export/{fmt}",
        params={"draft": "acknowledged", "redact": "true"},
    )

    assert full.status_code == 200, full.text
    assert redacted.status_code == 200, redacted.text
    full_text = _text_of(fmt, full.content)
    text = _text_of(fmt, redacted.content)
    # Without the option the export is unchanged, private details included,
    # so the test would notice if the seed never reached this format.
    assert "X-Axcess-Export-Redaction" not in full.headers
    if _EMAIL in full_text:
        assert _EMAIL not in text
    assert _FIELD_VALUE not in text
    assert _PHONE not in text
    assert "[redacted" in text or _EMAIL not in full_text
    assert REDACTION_NOTICE in text
    assert redacted.headers["X-Axcess-Export-Redaction"] == "best-effort"
    disposition = redacted.headers["content-disposition"]
    assert f'filename="scan_{scan_id}_DRAFT_REDACTED.' in disposition
    # Check names and element locators survive for the developer.
    if "label" in full_text and _SELECTOR in full_text:
        assert _SELECTOR in text


def test_redacted_json_is_still_valid_and_marked(
    client: TestClient, seeded_db: tuple[Path, Path, int]
) -> None:
    db_path, _, scan_id = seeded_db
    _seed_private_details(db_path, scan_id)

    response = client.get(
        f"/api/scans/{scan_id}/export/json", params={"draft": "acknowledged", "redact": "true"}
    )

    payload = json.loads(response.content)
    assert payload["redaction_notice"]["best_effort"] is True
    assert payload["export_notice"]["draft"] is True
    finding = next(f for f in payload["a11y_findings"] if f["rule_id"] == "label")
    assert finding["target_selector"] == _SELECTOR
    assert finding["html_snippet"] == (
        '<input name="card" value="[redacted]" data-owner="[redacted email]">'
    )


def test_redacted_workbook_leaves_out_screenshots(
    client: TestClient, seeded_db: tuple[Path, Path, int]
) -> None:
    db_path, blob_dir, scan_id = seeded_db
    add_screenshot_finding(db_path, blob_dir, scan_id)

    def picture_count(redact: bool) -> int:
        params = {"draft": "acknowledged"} | ({"redact": "true"} if redact else {})
        response = client.get(f"/api/scans/{scan_id}/export/xlsx", params=params)
        assert response.status_code == 200, response.text
        workbook = load_workbook(io.BytesIO(response.content))
        return sum(len(sheet._images) for sheet in workbook.worksheets)

    assert picture_count(redact=False) > 0
    assert picture_count(redact=True) == 0


def test_redaction_does_not_change_the_report_in_the_app(
    client: TestClient, seeded_db: tuple[Path, Path, int]
) -> None:
    db_path, _, scan_id = seeded_db
    _seed_private_details(db_path, scan_id)

    # The issue page shows each occurrence's element code (HTML).
    issue_url = f"/api/scans/{scan_id}/issues/axe:label"
    before = client.get(issue_url).json()
    client.get(
        f"/api/scans/{scan_id}/export/csv", params={"draft": "acknowledged", "redact": "true"}
    )
    after = client.get(issue_url).json()

    assert before == after
    assert _FIELD_VALUE in json.dumps(after)
    with sqlite3.connect(db_path) as conn:
        (snippet,) = conn.execute(
            "SELECT html_snippet FROM page_a11y_findings WHERE target_hash = 'seeded-private'"
        ).fetchone()
    assert _FIELD_VALUE in snippet


def test_export_options_describe_the_redacted_files(
    client: TestClient, seeded_db: tuple[Path, Path, int]
) -> None:
    _, _, scan_id = seeded_db

    plain = client.get(f"/api/scans/{scan_id}/exports").json()
    redacted = client.get(f"/api/scans/{scan_id}/exports", params={"redact": "true"}).json()

    assert plain["redacted"] is False
    assert redacted["redacted"] is True
    for option in redacted["formats"]:
        assert option["filename"].endswith(
            {
                "xlsx": ".xlsx",
                "audit": ".audit.md",
                "brief": ".fix-brief.md",
                "csv": ".csv",
                "json": ".json",
            }[option["format"]]
        )
        assert "_REDACTED." in option["filename"]
        response = client.get(
            f"/api/scans/{scan_id}/export/{option['format']}",
            params={"draft": "acknowledged", "redact": "true"},
        )
        filename = response.headers["content-disposition"].split('filename="', 1)[1].rstrip('"')
        assert option["filename"] == filename
        if option["format"] == "xlsx":
            assert abs(option["size_bytes"] - len(response.content)) <= 64
        else:
            assert option["size_bytes"] == len(response.content)


def test_an_unknown_report_is_still_refused_when_redacting(client: TestClient) -> None:
    """``redact=true`` does not bypass the route's existing refusals."""
    response = client.get("/api/scans/99999/export/csv", params={"redact": "true"})
    assert response.status_code == 404
