"""Unit tests for the env-gated webhook dispatcher."""

from __future__ import annotations

import json
import sqlite3

import httpx
import pytest
import respx

from audit.db import repo
from audit.exports.collector import collect_scan
from audit.exports.webhook import build_payload, is_enabled, post
from audit.synthesizer.findings import synthesize_findings


def _minimal_scan(conn: sqlite3.Connection) -> int:
    cur = conn.execute(
        "INSERT INTO scans (seed_url, status, page_count, finding_count, config_json) "
        "VALUES ('http://x/', 'completed', 1, 0, '{}')"
    )
    scan_id = int(cur.lastrowid or 0)
    page_id = repo.upsert_page(
        conn,
        scan_id=scan_id,
        url_normalized="http://x/",
        status_code=200,
        title="x",
        render_mode="static",
        html_hash="0" * 64,
    )
    image_id = repo.upsert_image(
        conn,
        content_hash="a" * 64,
        src_url="http://x/a.png",
        mime="image/png",
        bytes_len=1,
        width=1,
        height=1,
        blob_path="aa/" + "a" * 64 + ".png",
        has_svg_text=False,
        scan_id=scan_id,
    )
    repo.upsert_page_image(
        conn,
        page_id=page_id,
        image_id=image_id,
        alt_text=None,
        role=None,
        context_snippet=None,
        position=0,
    )
    repo.upsert_analysis(
        conn,
        image_id=image_id,
        ocr_text="BANNER TEXT",
        ocr_confidence=80.0,
        vlm_classification="essential",
        vlm_rationale="essential text in image",
        has_text=True,
        model_versions={"ocr": "stub", "vlm": "stub:1", "prompt": "v1-stub"},
    )
    synthesize_findings(conn, scan_id=scan_id)
    return scan_id


def test_is_enabled_only_when_env_set() -> None:
    assert not is_enabled({})
    assert not is_enabled({"AUDIT_WEBHOOK_URL": ""})
    assert not is_enabled({"AUDIT_WEBHOOK_URL": "   "})
    assert is_enabled({"AUDIT_WEBHOOK_URL": "http://example.com/hook"})


def test_build_payload_has_source_and_schema(tmp_db: sqlite3.Connection) -> None:
    scan_id = _minimal_scan(tmp_db)
    scan = collect_scan(tmp_db, scan_id)
    payload = build_payload(scan)
    assert payload["source"]["tool"] == "imagetextscanner"
    assert payload["schema_version"] >= 1
    assert payload["scan"]["id"] == scan_id


@pytest.mark.asyncio
async def test_post_is_noop_when_env_missing(tmp_db: sqlite3.Connection) -> None:
    scan_id = _minimal_scan(tmp_db)
    scan = collect_scan(tmp_db, scan_id)
    async with httpx.AsyncClient() as client:
        status = await post(scan, client=client, env={})
    assert status is None


@pytest.mark.asyncio
@respx.mock
async def test_post_sends_json_with_auth_header_when_token_set(
    tmp_db: sqlite3.Connection,
) -> None:
    scan_id = _minimal_scan(tmp_db)
    scan = collect_scan(tmp_db, scan_id)
    route = respx.post("https://hooks.example.com/ingest").mock(
        return_value=httpx.Response(202, json={"ok": True})
    )
    async with httpx.AsyncClient() as client:
        status = await post(
            scan,
            client=client,
            env={
                "AUDIT_WEBHOOK_URL": "https://hooks.example.com/ingest",
                "AUDIT_WEBHOOK_TOKEN": "sekret",
            },
        )
    assert status == 202
    assert route.call_count == 1
    sent = route.calls[0].request
    assert sent.headers["authorization"] == "Bearer sekret"
    body = json.loads(sent.content)
    assert body["scan"]["id"] == scan_id


@pytest.mark.asyncio
@respx.mock
async def test_post_swallows_http_errors(tmp_db: sqlite3.Connection) -> None:
    scan_id = _minimal_scan(tmp_db)
    scan = collect_scan(tmp_db, scan_id)
    respx.post("https://hooks.example.com/ingest").mock(side_effect=httpx.ConnectError("down"))
    async with httpx.AsyncClient() as client:
        status = await post(
            scan,
            client=client,
            env={"AUDIT_WEBHOOK_URL": "https://hooks.example.com/ingest"},
        )
    assert status is None


@pytest.mark.asyncio
@respx.mock
async def test_post_returns_non_2xx_status(tmp_db: sqlite3.Connection) -> None:
    scan_id = _minimal_scan(tmp_db)
    scan = collect_scan(tmp_db, scan_id)
    respx.post("https://hooks.example.com/ingest").mock(
        return_value=httpx.Response(500, text="oops")
    )
    async with httpx.AsyncClient() as client:
        status = await post(
            scan,
            client=client,
            env={"AUDIT_WEBHOOK_URL": "https://hooks.example.com/ingest"},
        )
    assert status == 500
