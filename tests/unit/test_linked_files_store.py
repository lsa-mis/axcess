"""Migration 0039 and the linked-file writes: rollback, bounds and scan isolation."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import httpx
import pytest

from audit.db import linked_files as store
from audit.linked_files.fetch import fetch_file

MIGRATION = Path(__file__).parents[2] / "src/audit/db/migrations/0039_linked_files"


def _scan_and_page(conn: sqlite3.Connection, host: str) -> tuple[int, int]:
    scan = conn.execute(
        "INSERT INTO scans (seed_url, status, config_json) VALUES (?, 'completed', '{}')",
        (f"https://{host}/",),
    ).lastrowid
    page = conn.execute(
        "INSERT INTO pages (scan_id, url_normalized, render_mode) VALUES (?, ?, 'js')",
        (scan, f"https://{host}/"),
    ).lastrowid
    return int(scan or 0), int(page or 0)


def _tables(conn: sqlite3.Connection) -> set[str]:
    return {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}


def test_forward_rollback_forward(tmp_db: sqlite3.Connection) -> None:
    scan, page = _scan_and_page(tmp_db, "a.test")
    file_id = store.upsert_file(
        tmp_db,
        scan_id=scan,
        url="https://a.test/x.pdf",
        file_type="pdf",
        found_by="extension",
        off_site=False,
    )
    assert file_id is not None
    store.add_ref(tmp_db, scan_id=scan, file_id=file_id, page_id=page, how="link", link_text="X")

    tmp_db.executescript(MIGRATION.with_suffix(".rollback.sql").read_text())
    assert not {"linked_files", "linked_file_refs"} & _tables(tmp_db)
    # The scan and its page are untouched.
    assert tmp_db.execute("SELECT COUNT(*) FROM pages").fetchone()[0] == 1

    tmp_db.executescript(MIGRATION.with_suffix(".sql").read_text())
    assert {"linked_files", "linked_file_refs"} <= _tables(tmp_db)
    assert tmp_db.execute("SELECT COUNT(*) FROM linked_files").fetchone()[0] == 0


def test_a_new_file_gets_the_status_its_type_decides(tmp_db: sqlite3.Connection) -> None:
    scan, _ = _scan_and_page(tmp_db, "a.test")
    for url, file_type in [("https://a.test/a.pdf", "pdf"), ("https://a.test/a.doc", "doc")]:
        store.upsert_file(
            tmp_db,
            scan_id=scan,
            url=url,
            file_type=file_type,  # type: ignore[arg-type]
            found_by="extension",
            off_site=False,
        )
    rows = {
        r[0]: (r[1], r[2])
        for r in tmp_db.execute("SELECT file_type, status, reason FROM linked_files")
    }
    assert rows == {"pdf": ("pending", None), "doc": ("could_not_check", "old_format")}


def test_the_database_refuses_a_status_outside_the_three(tmp_db: sqlite3.Connection) -> None:
    scan, _ = _scan_and_page(tmp_db, "a.test")
    with pytest.raises(sqlite3.IntegrityError):
        tmp_db.execute(
            "INSERT INTO linked_files (scan_id, url, file_type, found_by, status) "
            "VALUES (?, 'https://a.test/a.pdf', 'pdf', 'extension', 'accessible')",
            (scan,),
        )


def test_a_page_cannot_reference_another_scans_file(tmp_db: sqlite3.Connection) -> None:
    scan_a, page_a = _scan_and_page(tmp_db, "a.test")
    scan_b, page_b = _scan_and_page(tmp_db, "b.test")
    file_b = store.upsert_file(
        tmp_db,
        scan_id=scan_b,
        url="https://b.test/x.pdf",
        file_type="pdf",
        found_by="extension",
        off_site=False,
    )
    assert file_b is not None
    with pytest.raises(ValueError):
        store.add_ref(
            tmp_db, scan_id=scan_a, file_id=file_b, page_id=page_a, how="link", link_text=""
        )
    with pytest.raises(ValueError):
        store.add_ref(
            tmp_db, scan_id=scan_b, file_id=file_b, page_id=page_a, how="link", link_text=""
        )
    with pytest.raises(ValueError):
        store.set_result(
            tmp_db, scan_id=scan_a, file_id=file_b, result=store.CheckResult("not_sure")
        )
    assert store.add_ref(
        tmp_db, scan_id=scan_b, file_id=file_b, page_id=page_b, how="link", link_text=""
    )


def test_references_and_files_are_bounded(
    tmp_db: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(store, "MAX_REFS_PER_FILE", 2)
    monkeypatch.setattr(store, "MAX_FILES_PER_SCAN", 1)
    scan, page = _scan_and_page(tmp_db, "a.test")
    file_id = store.upsert_file(
        tmp_db,
        scan_id=scan,
        url="https://a.test/x.pdf",
        file_type="pdf",
        found_by="extension",
        off_site=False,
    )
    assert file_id is not None
    added = [
        store.add_ref(tmp_db, scan_id=scan, file_id=file_id, page_id=page, how="link", link_text=t)
        for t in ("one", "two", "three")
    ]
    assert added == [True, True, False]
    # The file already recorded is still found; a new one is refused.
    assert (
        store.upsert_file(
            tmp_db,
            scan_id=scan,
            url="https://a.test/x.pdf",
            file_type="pdf",
            found_by="extension",
            off_site=False,
        )
        == file_id
    )
    assert (
        store.upsert_file(
            tmp_db,
            scan_id=scan,
            url="https://a.test/y.pdf",
            file_type="pdf",
            found_by="extension",
            off_site=False,
        )
        is None
    )


def test_could_not_check_always_has_a_reason(tmp_db: sqlite3.Connection) -> None:
    scan, _ = _scan_and_page(tmp_db, "a.test")
    file_id = store.upsert_file(
        tmp_db,
        scan_id=scan,
        url="https://a.test/x.pdf",
        file_type="pdf",
        found_by="extension",
        off_site=False,
    )
    assert file_id is not None
    with pytest.raises(ValueError):
        store.set_result(
            tmp_db, scan_id=scan, file_id=file_id, result=store.CheckResult("could_not_check")
        )
    assert store.mark_unchecked(tmp_db, scan) == 1
    assert tmp_db.execute("SELECT status, reason FROM linked_files").fetchone()[:] == (
        "could_not_check",
        "not_checked",
    )


def _client(handler: httpx.MockTransport) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=handler)


async def test_a_file_over_the_limit_is_not_held() -> None:
    def answer(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"%PDF-" + b"x" * 5000)

    async with _client(httpx.MockTransport(answer)) as client:
        result = await fetch_file(client, "https://a.test/big.pdf", max_bytes=1000)
    assert (result.outcome, result.body) == ("too_large", b"")


async def test_a_declared_length_over_the_limit_is_refused_before_reading() -> None:
    def answer(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"Content-Length": "999999999"}, content=b"%PDF-")

    async with _client(httpx.MockTransport(answer)) as client:
        result = await fetch_file(client, "https://a.test/big.pdf", max_bytes=1000)
    assert result.outcome == "too_large"


async def test_errors_are_reported_not_raised() -> None:
    def gone(request: httpx.Request) -> httpx.Response:
        return httpx.Response(410)

    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    def slow(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    async with _client(httpx.MockTransport(gone)) as client:
        assert (await fetch_file(client, "https://a.test/x.pdf")).outcome == "http_error"
    async with _client(httpx.MockTransport(down)) as client:
        assert (await fetch_file(client, "https://a.test/x.pdf")).outcome == "broken_link"
    async with _client(httpx.MockTransport(slow)) as client:
        assert (await fetch_file(client, "https://a.test/x.pdf")).outcome == "timed_out"
