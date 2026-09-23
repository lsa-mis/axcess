"""Response-shape contract for the read endpoints the SPA depends on.

Each endpoint's JSON body is reduced to a type skeleton and compared with a
committed golden: dicts keep their (sorted) keys, lists keep the merged shape
of their first few elements, and scalars become their JSON type name. Values
are never recorded, so timestamps and ids cannot make it flaky, but a renamed
key, a dropped field, or a string that became a number fails. Status code and
content type are pinned alongside the body.

The endpoint list is explicit on purpose: adding an endpoint to the contract
is a reviewed change to this file and to ``golden/api_contract.json``.
"""

from __future__ import annotations

import functools
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from urllib.parse import quote

import httpx
import pytest
from fastapi.testclient import TestClient

from audit.db import repo
from audit.db.schema import connect
from audit.web import server

from ._golden import check_golden_document

pytestmark = pytest.mark.ui

_CONTRACT_GOLDEN = "api_contract.json"

# Label -> URL template. Labels name the route template so the golden reads
# as an API reference; the placeholders are ids from the seeded report.
_ENDPOINTS: tuple[tuple[str, str], ...] = (
    ("GET /health", "/health"),
    ("GET /api/scans", "/api/scans"),
    ("GET /api/scans/{scan_id}", "/api/scans/{scan}"),
    ("GET /api/scans/{scan_id}/issues", "/api/scans/{scan}/issues"),
    (
        "GET /api/scans/{scan_id}/issues/{issue_key} (axe issue)",
        "/api/scans/{scan}/issues/{axe_issue}",
    ),
    (
        "GET /api/scans/{scan_id}/issues/{issue_key} (image issue)",
        "/api/scans/{scan}/issues/{image_issue}",
    ),
    ("GET /api/scans/{scan_id}/findings", "/api/scans/{scan}/findings"),
    ("GET /api/scans/{scan_id}/findings/grouped", "/api/scans/{scan}/findings/grouped"),
    ("GET /api/findings/{finding_id}", "/api/findings/{finding}"),
    ("GET /api/scans/{scan_id}/a11y", "/api/scans/{scan}/a11y"),
    ("GET /api/scans/{scan_id}/a11y/by-rule", "/api/scans/{scan}/a11y/by-rule"),
    (
        "GET /api/scans/{scan_id}/a11y/findings?wcag_sc=1.3.1",
        "/api/scans/{scan}/a11y/findings?wcag_sc=1.3.1",
    ),
    ("GET /api/scans/{scan_id}/pages/{page_id}", "/api/scans/{scan}/pages/{page}"),
    ("GET /api/scans/{scan_id}/evaluation", "/api/scans/{scan}/evaluation"),
    ("GET /api/scans/{scan_id}/manual-checks", "/api/scans/{scan}/manual-checks"),
    ("GET /api/scans/{scan_id}/comparison", "/api/scans/{scan}/comparison"),
    (
        "GET /api/scans/{scan_id}/diff?compare_to={baseline_id}",
        "/api/scans/{scan}/diff?compare_to={baseline}",
    ),
    ("GET /api/capabilities/alfa", "/api/capabilities/alfa"),
    ("GET /api/capabilities/local-analysis", "/api/capabilities/local-analysis"),
    ("GET /api/capabilities/protected-scans", "/api/capabilities/protected-scans"),
    ("GET /api/tracking", "/api/tracking"),
    ("GET /api/scope-preview (empty)", "/api/scope-preview"),
    ("GET /api/scope-preview (valid url)", "/api/scope-preview?url=https://example.com/docs"),
    ("GET /api/scope-preview (invalid url)", "/api/scope-preview?url=ftp://example.com/"),
)

# Enough elements to merge the variants a list mixes (e.g. axe and image
# issue rows) without letting a long list dominate the run time.
_LIST_SAMPLE = 5
_ABSENT = "absent"
_SCALAR_NAMES: tuple[tuple[type, str], ...] = (
    # bool before int: ``True`` is an ``int`` too.
    (bool, "boolean"),
    (int, "integer"),
    (float, "number"),
    (str, "string"),
    (type(None), "null"),
)


def _parts(skeleton: Any) -> list[Any]:
    if isinstance(skeleton, str):
        return skeleton.split("|")
    if isinstance(skeleton, dict) and list(skeleton) == ["anyOf"]:
        return [part for option in skeleton["anyOf"] for part in _parts(option)]
    return [skeleton]


def _merge_objects(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    return {key: _union(a.get(key, _ABSENT), b.get(key, _ABSENT)) for key in sorted(a | b)}


def _merge_arrays(a: list[Any], b: list[Any]) -> list[Any]:
    if not a or not b:
        return a or b
    return [_union(a[0], b[0])]


def _union(a: Any, b: Any) -> Any:
    """Merge two skeletons: objects by key, arrays by element, scalars as ``a|b``."""
    if a == b:
        return a
    parts = _parts(a) + _parts(b)
    scalars = sorted({part for part in parts if isinstance(part, str)})
    objects = [part for part in parts if isinstance(part, dict)]
    arrays = [part for part in parts if isinstance(part, list)]
    structured = []
    if objects:
        structured.append(functools.reduce(_merge_objects, objects))
    if arrays:
        structured.append(functools.reduce(_merge_arrays, arrays))
    if not structured:
        return "|".join(scalars)
    if not scalars and len(structured) == 1:
        return structured[0]
    options: list[Any] = ["|".join(scalars)] if scalars else []
    return {"anyOf": [*options, *structured]}


def _skeleton(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _skeleton(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        if not value:
            return []
        return [functools.reduce(_union, (_skeleton(item) for item in value[:_LIST_SAMPLE]))]
    for kind, name in _SCALAR_NAMES:
        if isinstance(value, kind):
            return name
    raise TypeError(f"not a JSON value: {value!r}")


class _UnreachableOllama:
    """Stands in for ``httpx.AsyncClient`` so the capability probe is offline."""

    def __init__(self, **_kwargs: object) -> None:
        pass

    async def __aenter__(self) -> _UnreachableOllama:
        return self

    async def __aexit__(self, *_args: object) -> None:
        return None

    async def get(self, url: str) -> httpx.Response:
        raise httpx.ConnectError(f"offline: {url}")


@pytest.fixture(autouse=True)
def _hermetic_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin everything outside the seed that decides a response's shape.

    Autouse, so it runs before the ``client`` fixture builds the app and
    reads settings. Without it the local machine leaks in: an installed
    Alfa runner or Ollama turns a ``reason`` string into ``null``.
    """
    monkeypatch.setenv("AUDIT_ACCESS_TOKEN", "")
    monkeypatch.setenv("AUDIT_PROTECTED_SCANS_ENABLED", "false")
    monkeypatch.setattr(
        server,
        "alfa_availability",
        lambda: SimpleNamespace(available=False, reason="Alfa runner is not installed."),
    )
    monkeypatch.setattr(server.httpx, "AsyncClient", _UnreachableOllama)


def _add_contract_evidence(db_path: Path, scan_id: int) -> dict[str, Any]:
    """Extend the shared seed so the list endpoints return real rows.

    The seed has image findings only; an axe violation gives the a11y and
    issue endpoints rows to describe, and an earlier completed scan of the
    same site gives comparison and diff a baseline.
    """
    conn = connect(db_path)
    try:
        conn.execute("UPDATE scans SET started_at = '2026-09-02 12:00:00' WHERE id = ?", (scan_id,))
        baseline = int(
            conn.execute(
                "INSERT INTO scans (seed_url, status, page_count, finding_count, config_json, "
                "started_at) VALUES ('http://example.com/', 'completed', 0, 0, '{}', "
                "'2026-09-01 12:00:00')"
            ).lastrowid
            or 0
        )
        page = int(
            conn.execute(
                "SELECT id FROM pages WHERE scan_id = ? ORDER BY id LIMIT 1", (scan_id,)
            ).fetchone()[0]
        )
        repo.upsert_axe_violation(
            conn,
            page_id=page,
            scan_id=scan_id,
            rule_id="label",
            wcag_sc="1.3.1",
            wcag_scs="1.3.1,3.3.2",
            wcag_level="A",
            impact="serious",
            help="Form elements must have labels",
            help_url="https://dequeuniversity.com/rules/axe/4.10/label",
            target_selector="#contract",
            failure_summary="Fix the missing label.",
            html_snippet='<input id="contract">',
            target_hash="api-contract",
        )
        finding = int(
            conn.execute(
                "SELECT id FROM findings WHERE scan_id = ? ORDER BY id LIMIT 1", (scan_id,)
            ).fetchone()[0]
        )
    finally:
        conn.close()
    return {"scan": scan_id, "baseline": baseline, "page": page, "finding": finding}


def _first_issue_key(client: TestClient, scan_id: int, pipeline: str) -> str:
    rows = client.get(f"/api/scans/{scan_id}/issues").json()["rows"]
    key = next(row["issue_key"] for row in rows if row["pipeline"] == pipeline)
    return quote(str(key), safe="")


def test_read_endpoint_shapes_match_golden(
    client: TestClient, seeded_db: tuple[Path, Path, int]
) -> None:
    db_path, _, scan_id = seeded_db
    ids = _add_contract_evidence(db_path, scan_id)
    ids["axe_issue"] = _first_issue_key(client, scan_id, "axe")
    ids["image_issue"] = _first_issue_key(client, scan_id, "image")

    observed: dict[str, Any] = {}
    for label, template in _ENDPOINTS:
        response = client.get(template.format(**ids))
        observed[label] = {
            "status": response.status_code,
            "content_type": response.headers.get("content-type"),
            "body": _skeleton(response.json()),
        }
    check_golden_document(_CONTRACT_GOLDEN, observed)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ({"b": 1, "a": [True, None]}, {"a": ["boolean|null"], "b": "integer"}),
        ([{"x": 1}, {"x": "s", "y": 2.5}], [{"x": "integer|string", "y": "absent|number"}]),
        ([None, {"x": 1}], [{"anyOf": ["null", {"x": "integer"}]}]),
        ([[], [1]], [["integer"]]),
    ],
)
def test_skeleton_records_shape_not_values(value: Any, expected: Any) -> None:
    assert _skeleton(value) == expected


def test_skeleton_rejects_non_json_values() -> None:
    with pytest.raises(TypeError):
        _skeleton({"when": object()})
