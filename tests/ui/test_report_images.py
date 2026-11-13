"""Route tests for the report Images tab API.

``GET /api/scans/{id}/images`` lists a report's images by group;
``POST /api/scans/{id}/images/{image_id}/alt-check`` asks the local model
about one image. These pin the guards: no model set, a scan that is not
complete, an image from another scan, a model that times out or answers
nonsense. The list must keep working in every one of those cases.
"""

from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from audit.analyzer.ollama_base import OllamaError
from audit.analyzer.vlm.alt_check import AltCheckInput, AltCheckResult
from audit.blob_store import BlobStore
from audit.db import repo
from audit.db.schema import connect
from audit.web.server import create_app


class _Stub:
    model = "stub:1"
    prompt_version = "v1-test"

    def __init__(self, behaviour: str = "ok") -> None:
        self.behaviour = behaviour
        self.calls: list[AltCheckInput] = []

    async def check(self, image_bytes: bytes, given: AltCheckInput) -> AltCheckResult:
        self.calls.append(given)
        if self.behaviour == "slow":
            await asyncio.sleep(30)
        if self.behaviour == "bad":
            raise OllamaError("the model did not return valid JSON")
        return AltCheckResult(
            verdict="needs_better" if given.alt_text else None,
            reason="Too vague.",
            suggestion="Students talking outside Haven Hall",
            model=self.model,
            prompt_version=self.prompt_version,
        )


def _pixel_png(color: tuple[int, int, int]) -> bytes:
    from io import BytesIO

    from PIL import Image

    buffer = BytesIO()
    Image.new("RGB", (4, 4), color).save(buffer, format="PNG")
    return buffer.getvalue()


def _photo(
    db_path: Path,
    blob_dir: Path,
    scan_id: int,
    *,
    alt: str | None,
    color: tuple[int, int, int] = (10, 120, 40),
) -> int:
    """Add a photo with no text to a scan's first page; return its image id."""
    conn = connect(db_path)
    try:
        data = _pixel_png(color)
        content_hash, rel = BlobStore(blob_dir).store(data, "image/png")
        image_id = repo.upsert_image(
            conn,
            content_hash=content_hash,
            src_url="http://example.com/students.png",
            mime="image/png",
            bytes_len=len(data),
            width=40,
            height=40,
            blob_path=rel,
            has_svg_text=False,
            scan_id=scan_id,
        )
        page_id = conn.execute(
            "SELECT id FROM pages WHERE scan_id = ? ORDER BY id LIMIT 1", (scan_id,)
        ).fetchone()["id"]
        repo.upsert_page_image(
            conn,
            page_id=page_id,
            image_id=image_id,
            alt_text=alt,
            role=None,
            context_snippet="Our students",
            position=9,
        )
        conn.commit()
        return image_id
    finally:
        conn.close()


@pytest.fixture
def app_and_ids(seeded_db: tuple[Path, Path, int]) -> tuple[TestClient, int, int, Path]:
    db_path, blob_dir, scan_id = seeded_db
    photo = _photo(db_path, blob_dir, scan_id, alt="Campus")
    client = TestClient(create_app(db_path=db_path, blob_dir=blob_dir))
    return client, scan_id, photo, db_path


def test_list_groups_and_verdicts(app_and_ids: Any) -> None:
    client, scan_id, photo, _ = app_and_ids
    body = client.get(f"/api/scans/{scan_id}/images?group=with_text").json()
    assert body["counts"]["with_text"]["total"] == 2
    verdicts = {row["image_url"].rsplit("/", 1)[-1]: row["verdict"] for row in body["rows"]}
    assert verdicts == {"banner.png": "needs_alt", "logo.png": "good"}
    assert body["check_available"] is False

    with_alt = client.get(f"/api/scans/{scan_id}/images?group=with_alt").json()
    row = next(r for r in with_alt["rows"] if r["image_id"] == photo)
    assert row["verdict"] == "not_checked" and row["can_check"] is True


@pytest.mark.parametrize(
    "query",
    [
        "group=everything",
        "group=with_alt&verdict=bad",
        "group=with_alt&limit=51",
        "group=with_alt&limit=0",
    ],
)
def test_list_rejects_bad_parameters(app_and_ids: Any, query: str) -> None:
    client, scan_id, _, _ = app_and_ids
    assert client.get(f"/api/scans/{scan_id}/images?{query}").status_code in (400, 422)


def test_list_unknown_scan_is_404(app_and_ids: Any) -> None:
    client, *_ = app_and_ids
    assert client.get("/api/scans/9999/images").status_code == 404


def test_check_without_model_is_refused(app_and_ids: Any) -> None:
    client, scan_id, photo, _ = app_and_ids
    response = client.post(f"/api/scans/{scan_id}/images/{photo}/alt-check")
    assert response.status_code == 503
    assert "No local model" in response.json()["detail"]


def test_check_saves_and_returns_the_row(app_and_ids: Any) -> None:
    client, scan_id, photo, _ = app_and_ids
    stub = _Stub()
    client.app.state.alt_checker_factory = lambda _client: stub
    response = client.post(f"/api/scans/{scan_id}/images/{photo}/alt-check")
    assert response.status_code == 200, response.text
    row = response.json()
    assert row["verdict"] == "needs_better" and row["verdict_source"] == "local_model"
    assert row["suggestion"] == "Students talking outside Haven Hall"
    assert stub.calls[0].alt_text == "Campus"
    listed = client.get(f"/api/scans/{scan_id}/images?group=with_alt").json()
    assert listed["check_available"] is True
    assert next(r for r in listed["rows"] if r["image_id"] == photo)["suggestion"]


def test_check_refuses_image_from_another_scan(app_and_ids: Any) -> None:
    client, scan_id, _, db_path = app_and_ids
    conn = connect(db_path)
    try:
        other = int(
            conn.execute(
                "INSERT INTO scans (seed_url, status, config_json) "
                "VALUES ('http://other.test/', 'completed', '{}')"
            ).lastrowid
            or 0
        )
        conn.commit()
    finally:
        conn.close()
    blob_dir = Path(str(db_path)).parent / "blobs"
    repo_page = connect(db_path)
    try:
        repo.upsert_page(
            repo_page,
            scan_id=other,
            url_normalized="http://other.test/",
            status_code=200,
            title="Other",
            render_mode="static",
            html_hash="9" * 64,
        )
        repo_page.commit()
    finally:
        repo_page.close()
    # A different picture, so a different image row from the one in this scan.
    foreign = _photo(db_path, blob_dir, other, alt="Other", color=(200, 10, 10))
    client.app.state.alt_checker_factory = lambda _client: _Stub()
    # The image is real, but not on any page of this scan.
    response = client.post(f"/api/scans/{scan_id}/images/{foreign}/alt-check")
    assert response.status_code == 404
    # And the other scan's check never appears here.
    client.post(f"/api/scans/{other}/images/{foreign}/alt-check")
    rows = client.get(f"/api/scans/{scan_id}/images?group=with_alt").json()["rows"]
    assert all(r["image_id"] != foreign for r in rows)


def test_check_refuses_scan_that_is_not_complete(app_and_ids: Any) -> None:
    client, scan_id, photo, db_path = app_and_ids
    conn = connect(db_path)
    try:
        conn.execute("UPDATE scans SET status = 'running' WHERE id = ?", (scan_id,))
        conn.commit()
    finally:
        conn.close()
    client.app.state.alt_checker_factory = lambda _client: _Stub()
    assert client.post(f"/api/scans/{scan_id}/images/{photo}/alt-check").status_code == 409
    # Browsing still works.
    assert client.get(f"/api/scans/{scan_id}/images").status_code == 200


def test_check_reports_bad_answer_and_saves_nothing(app_and_ids: Any) -> None:
    client, scan_id, photo, db_path = app_and_ids
    client.app.state.alt_checker_factory = lambda _client: _Stub("bad")
    response = client.post(f"/api/scans/{scan_id}/images/{photo}/alt-check")
    assert response.status_code == 502
    assert "Nothing was saved" in response.json()["detail"]
    conn = connect(db_path)
    try:
        assert conn.execute("SELECT COUNT(*) FROM alt_text_checks").fetchone()[0] == 0
    finally:
        conn.close()


def test_check_times_out(app_and_ids: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    client, scan_id, photo, _ = app_and_ids
    client.app.state.alt_checker_factory = lambda _client: _Stub("slow")
    real_wait_for = asyncio.wait_for

    async def short_wait_for(awaitable: Any, timeout: float) -> Any:
        return await real_wait_for(awaitable, timeout=0.05)

    monkeypatch.setattr(asyncio, "wait_for", short_wait_for)
    response = client.post(f"/api/scans/{scan_id}/images/{photo}/alt-check")
    assert response.status_code == 504


def test_rollback_drops_the_table(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2] / "src" / "audit" / "db" / "migrations"
    conn = sqlite3.connect(tmp_path / "x.db")
    conn.execute("CREATE TABLE scans (id INTEGER PRIMARY KEY)")
    conn.execute("CREATE TABLE images (id INTEGER PRIMARY KEY)")
    conn.executescript((root / "0032_alt_text_checks.sql").read_text())
    conn.executescript((root / "0032_alt_text_checks.rollback.sql").read_text())
    assert (
        conn.execute("SELECT name FROM sqlite_master WHERE name = 'alt_text_checks'").fetchone()
        is None
    )


def _zip(client: TestClient, scan_id: int) -> Any:
    import io
    import zipfile

    response = client.get(f"/api/scans/{scan_id}/images/export.zip")
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/zip"
    assert f"report-{scan_id}-images.zip" in response.headers["content-disposition"]
    return zipfile.ZipFile(io.BytesIO(response.content))


def test_zip_puts_images_in_group_and_verdict_folders(app_and_ids: Any) -> None:
    from openpyxl import load_workbook

    client, scan_id, photo, db_path = app_and_ids
    # Alt text from a crawled page that looks like a formula.
    conn = connect(db_path)
    try:
        conn.execute(
            "UPDATE page_images SET alt_text = ? WHERE image_id = ?",
            ('=HYPERLINK("http://evil.test","x")', photo),
        )
        conn.commit()
    finally:
        conn.close()
    archive = _zip(client, scan_id)
    names = archive.namelist()
    root = f"report-{scan_id}-images/"
    banner = [n for n in names if n.endswith("banner.png")]
    # An image with text and no alt text is in both of its groups.
    assert sorted(n.removeprefix(root).rsplit("/", 1)[0] for n in banner) == [
        "Images with text/Needs alt text",
        "Images without alt text/Needs alt text",
    ]
    assert any(
        n.startswith(root + "Images with text/Good alt text/") and n.endswith("logo.png")
        for n in names
    )
    assert any(
        n.startswith(root + "Images with alt text/Not checked yet/") and n.endswith("students.png")
        for n in names
    )

    import io

    wb = load_workbook(io.BytesIO(archive.read(root + "images.xlsx")))
    assert wb.sheetnames == ["About", "Images"]
    ws = wb["Images"]
    header = [c.value for c in ws[1]]
    assert header[:4] == ["Image number", "File name", "Groups", "Alt text verdict"]
    rows = [[c.value for c in r] for r in ws.iter_rows(min_row=2)]
    assert len(rows) == 3
    alt_col = header.index("Current alt text")
    photo_row = next(r for r in rows if r[0] == photo)
    cell = ws.cell(row=rows.index(photo_row) + 2, column=alt_col + 1)
    assert cell.data_type == "s" and cell.value.startswith("=HYPERLINK")
    files_col = header.index("Files in this ZIP")
    assert "Images with alt text/Not checked yet/" in photo_row[files_col]
    about = " ".join(str(c.value) for c in wb["About"]["A"] if c.value)
    assert "does not prove" in about


def test_zip_refuses_report_that_is_not_complete(app_and_ids: Any) -> None:
    client, scan_id, _, db_path = app_and_ids
    conn = connect(db_path)
    try:
        conn.execute("UPDATE scans SET status = 'running' WHERE id = ?", (scan_id,))
        conn.commit()
    finally:
        conn.close()
    assert client.get(f"/api/scans/{scan_id}/images/export.zip").status_code == 409
    assert client.get("/api/scans/9999/images/export.zip").status_code == 404
