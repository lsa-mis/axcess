"""Response-shape contract for the read endpoints the SPA depends on.

Each endpoint's JSON body is reduced to a type skeleton and compared with a
committed golden: dicts keep their (sorted) keys, lists keep the merged shape
of their first few elements, and scalars become their JSON type name. Values
are never recorded, so timestamps and ids cannot make it flaky, but a renamed
key, a dropped field, or a string that became a number fails. Status code and
content type are pinned alongside the body.

A skeleton pins only what the seed exercises: an empty list or object, or a
field that is ``null`` in every sampled row, records nothing about the shape
the SPA reads once it is populated. The shared seed is therefore extended
here until every such path carries a typed value in at least one recorded
variant of its route, and the few that cannot are listed in
``_UNPINNED_PATHS`` with the reason. Any other empty or always-null path
fails, so a later seed change cannot quietly drop coverage.

The endpoint list is explicit on purpose: adding an endpoint to the contract
is a reviewed change to this file and to ``golden/api_contract.json``.
"""

from __future__ import annotations

import functools
import json
import sqlite3
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from urllib.parse import quote

import httpx
import pytest
from fastapi.testclient import TestClient

from audit import coverage_matrix, evaluation
from audit.blob_store import BlobStore
from audit.db import repo
from audit.db.schema import connect
from audit.synthesizer.findings import synthesize_findings
from audit.web import server

from ._golden import check_golden_document
from .conftest import _pixel_png, _seed

pytestmark = pytest.mark.ui

_CONTRACT_GOLDEN = "api_contract.json"

# Label -> URL template. Labels name the route template so the golden reads
# as an API reference; the placeholders are ids from the seeded report. A
# parenthesized suffix or a query string marks a variant of the same route.
_ENDPOINTS: tuple[tuple[str, str], ...] = (
    ("GET /health", "/health"),
    ("GET /api/scans", "/api/scans"),
    ("GET /api/scans/{scan_id}", "/api/scans/{scan}"),
    ("GET /api/scans/{scan_id} (running)", "/api/scans/{running}"),
    ("GET /api/scans/{scan_id} (blocked)", "/api/scans/{blocked}"),
    ("GET /api/scans/{scan_id} (failed)", "/api/scans/{failed}"),
    ("GET /api/scans/{scan_id} (unknown scan)", "/api/scans/{missing}"),
    ("GET /api/scans/{scan_id}/issues", "/api/scans/{scan}/issues"),
    (
        "GET /api/scans/{scan_id}/issues/{issue_key} (axe issue)",
        "/api/scans/{scan}/issues/{axe_issue}",
    ),
    (
        "GET /api/scans/{scan_id}/issues/{issue_key} (image issue)",
        "/api/scans/{scan}/issues/{image_issue}",
    ),
    (
        "GET /api/scans/{scan_id}/issues/{issue_key} (alfa issue)",
        "/api/scans/{scan}/issues/{alfa_issue}",
    ),
    ("GET /api/scans/{scan_id}/findings", "/api/scans/{scan}/findings"),
    (
        "GET /api/scans/{scan_id}/findings?page=0 (validation error)",
        "/api/scans/{scan}/findings?page=0",
    ),
    ("GET /api/scans/{scan_id}/findings/grouped", "/api/scans/{scan}/findings/grouped"),
    ("GET /api/findings/{finding_id}", "/api/findings/{finding}"),
    ("GET /api/scans/{scan_id}/a11y", "/api/scans/{scan}/a11y"),
    ("GET /api/scans/{scan_id}/a11y/by-rule", "/api/scans/{scan}/a11y/by-rule"),
    (
        "GET /api/scans/{scan_id}/a11y/findings?wcag_sc=1.3.1",
        "/api/scans/{scan}/a11y/findings?wcag_sc=1.3.1",
    ),
    (
        "GET /api/scans/{scan_id}/a11y/findings?wcag_sc=1.4.3",
        "/api/scans/{scan}/a11y/findings?wcag_sc=1.4.3",
    ),
    ("GET /api/scans/{scan_id}/pages/{page_id}", "/api/scans/{scan}/pages/{page}"),
    ("GET /api/scans/{scan_id}/evaluation", "/api/scans/{scan}/evaluation"),
    ("GET /api/scans/{scan_id}/evaluation (not saved)", "/api/scans/{baseline}/evaluation"),
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


# Paths that stay empty or null in the extended seed, by route, and why.
# Everything else must carry a typed value (see ``_check_seed_coverage``).
_OFFLINE_OLLAMA = (
    "Ollama is stubbed offline so the run is hermetic; the online form is pinned "
    "by test_routes.py::test_local_analysis_capability_distinguishes_bundled_ocr_and_models."
)
_NEW_PAIR = "A new pair has no baseline side (DiffEntry); the other buckets pin it."
_RESOLVED_PAIR = "A resolved pair has no current side (DiffEntry); the other buckets pin it."
_UNPINNED_PATHS: dict[tuple[str, str], str] = {
    ("GET /api/capabilities/local-analysis", "body.semantic.ready_models"): _OFFLINE_OLLAMA,
    ("GET /api/capabilities/local-analysis", "body.vision.installed_size_bytes"): _OFFLINE_OLLAMA,
    ("GET /api/scans/{scan_id}/diff", "body.new[].previous_finding_id"): _NEW_PAIR,
    ("GET /api/scans/{scan_id}/diff", "body.new[].previous_severity"): _NEW_PAIR,
    ("GET /api/scans/{scan_id}/diff", "body.new[].previous_status"): _NEW_PAIR,
    ("GET /api/scans/{scan_id}/diff", "body.resolved[].current_finding_id"): _RESOLVED_PAIR,
    ("GET /api/scans/{scan_id}/diff", "body.resolved[].current_status"): _RESOLVED_PAIR,
    ("GET /api/scans/{scan_id}/diff", "body.resolved[].severity"): _RESOLVED_PAIR,
    ("GET /api/scans/{scan_id}/findings", "body.findings[].alt_adequacy"): (
        "_query_findings always sets it to None; the grouped endpoint carries adequacy."
    ),
}


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


# Fixed times, so ordering between reports and the running scan's pace are
# the same on every run.
_BASELINE_STARTED = "2026-09-01 12:00:00"
_CURRENT_STARTED = "2026-09-02 12:00:00"
_MODEL_VERSIONS = {"ocr": "tesseract-test", "vlm": "stub:1", "prompt": "v1-stub"}


def _page_ids(conn: sqlite3.Connection, scan_id: int) -> list[int]:
    rows = conn.execute("SELECT id FROM pages WHERE scan_id = ? ORDER BY id", (scan_id,))
    return [int(row["id"]) for row in rows]


def _logo_finding(conn: sqlite3.Connection, scan_id: int) -> int:
    row = conn.execute(
        "SELECT f.id FROM findings f JOIN images i ON i.id = f.image_id "
        "WHERE f.scan_id = ? AND i.src_url_canonical = 'http://example.com/logo.png'",
        (scan_id,),
    ).fetchone()
    return int(row["id"])


def _add_image(
    conn: sqlite3.Connection,
    blob_dir: Path,
    *,
    scan_id: int,
    page_id: int,
    name: str,
    color: tuple[int, int, int],
    alt_text: str | None,
    ocr_text: str,
) -> None:
    """Place one analyzed image of text on one page, as the extractor would."""
    png = _pixel_png(color=color)
    content_hash, blob_path = BlobStore(blob_dir).store(png, "image/png")
    image_id = repo.upsert_image(
        conn,
        content_hash=content_hash,
        src_url=f"http://example.com/{name}.png",
        mime="image/png",
        bytes_len=len(png),
        width=40,
        height=40,
        blob_path=blob_path,
        has_svg_text=False,
        scan_id=scan_id,
    )
    repo.upsert_page_image(
        conn,
        page_id=page_id,
        image_id=image_id,
        alt_text=alt_text,
        role=None,
        context_snippet=None,
        position=3,
    )
    repo.upsert_analysis(
        conn,
        image_id=image_id,
        ocr_text=ocr_text,
        ocr_confidence=90.0,
        vlm_classification="essential",
        vlm_rationale="Promotional text rendered as an image.",
        has_text=True,
        model_versions=_MODEL_VERSIONS,
    )


def _add_label_violation(
    conn: sqlite3.Connection, *, scan_id: int, page_id: int, element_id: str, **extra: Any
) -> None:
    """Record axe's ``label`` rule failing on ``<input id=element_id>``."""
    repo.upsert_axe_violation(
        conn,
        page_id=page_id,
        scan_id=scan_id,
        rule_id="label",
        wcag_sc="1.3.1",
        wcag_scs="1.3.1,3.3.2",
        wcag_level="A",
        impact="serious",
        help="Form elements must have labels",
        help_url="https://dequeuniversity.com/rules/axe/4.10/label",
        target_selector=f"#{element_id}",
        failure_summary="Fix the missing label.",
        html_snippet=f'<input id="{element_id}">',
        target_hash=f"api-contract-{element_id}",
        **extra,
    )


def _add_report_history(conn: sqlite3.Connection, blob_dir: Path, scan_id: int) -> int:
    """Give the report an earlier run of the same site; returns its id.

    The baseline is a second copy of the shared seed, so both images are in
    both reports: the diff has ``still_open`` pairs and comparison rows have
    a ``before`` side. One image on each side exists only there (``new`` and
    ``resolved``), and a status changed since the baseline fills
    ``status_changed``. The baseline also fails the axe rule the report
    fails, so that comparison row has before-side outcomes.
    """
    baseline = _seed(conn, blob_dir)
    _add_label_violation(
        conn, scan_id=baseline, page_id=_page_ids(conn, baseline)[0], element_id="contract"
    )
    for report, started in ((baseline, _BASELINE_STARTED), (scan_id, _CURRENT_STARTED)):
        conn.execute(
            "UPDATE scans SET started_at = ?, finished_at = datetime(?, '+1 hour') WHERE id = ?",
            (started, started, report),
        )
    _add_image(
        conn,
        blob_dir,
        scan_id=baseline,
        page_id=_page_ids(conn, baseline)[0],
        name="retired-offer",
        color=(200, 60, 60),
        alt_text=None,
        ocr_text="SUMMER OFFER",
    )
    _add_image(
        conn,
        blob_dir,
        scan_id=scan_id,
        page_id=_page_ids(conn, scan_id)[1],
        name="spring-sale",
        color=(60, 200, 60),
        alt_text="Sale",
        ocr_text="SPRING SALE ENDS FRIDAY",
    )
    for report in (baseline, scan_id):
        synthesize_findings(conn, scan_id=report)
    repo.bulk_set_findings_status(
        conn, finding_ids=[_logo_finding(conn, scan_id)], status="reviewing"
    )
    return baseline


def _add_a11y_evidence(conn: sqlite3.Connection, blob_dir: Path, scan_id: int) -> None:
    """Axe and Alfa rows for the a11y, issue and page endpoints.

    Two occurrences of one axe rule, one plain and one found in a revealed
    DOM state with a screenshot, so locations carry both the null and the
    populated form; and an Alfa ``cant_tell`` outcome for the engine fields
    only Alfa fills. All on the home page, which the page endpoint reads.
    The plain one repeats on a second page, as a shared component does, so
    the issue row reports it once and carries the repeat in
    ``repeat_finding_ids``.
    """
    pages = _page_ids(conn, scan_id)
    home = pages[0]
    screenshot_hash, _ = BlobStore(blob_dir).store(_pixel_png(color=(0, 0, 0)), "image/png")
    _add_label_violation(conn, scan_id=scan_id, page_id=home, element_id="contract")
    _add_label_violation(conn, scan_id=scan_id, page_id=pages[1], element_id="contract")
    _add_label_violation(
        conn,
        scan_id=scan_id,
        page_id=home,
        element_id="menu-search",
        screenshot_hash=screenshot_hash,
        revealed_by="Opened the Menu button",
        revealed_state_key="menu-open",
    )
    repo.upsert_alfa_finding(
        conn,
        page_id=home,
        scan_id=scan_id,
        rule_id="sia-r69",
        wcag_sc="1.4.3",
        wcag_scs="1.4.3",
        wcag_level="AA",
        help="WCAG 1.4.3: Contrast (Minimum)",
        help_url="https://alfa.siteimprove.com/rules/sia-r69",
        target_selector="p.hero",
        failure_summary="Alfa requires expert review.",
        html_snippet='<p class="hero">Welcome</p>',
        target_hash="api-contract-alfa",
        engine_outcome="cant_tell",
        # A background-sizing limitation is what fills ``manual_review_hint``.
        engine_evidence_json=json.dumps(
            {"diagnostics": ["Background image sizing is not supported."]}
        ),
    )


def _add_expert_review(conn: sqlite3.Connection, scan_id: int) -> None:
    """A saved evaluation with one decided criterion and two evidence notes.

    The criterion is the matrix's first, so it is inside the sample the
    skeleton takes of the manual-check list. One note cites a page and one
    does not, which is the difference ``page_id``/``page_url`` encode.
    """
    evaluation.upsert_evaluation(
        conn,
        scan_id,
        {"reviewer": "Contract reviewer", "purpose": "Pin the API", "status": "in_progress"},
    )
    criterion = coverage_matrix.load_matrix()[0].sc
    evaluation.update_manual_check(
        conn,
        scan_id=scan_id,
        criterion_sc=criterion,
        outcome="fail",
        rationale="The banner has no text alternative.",
    )
    for page_id, note in ((_page_ids(conn, scan_id)[0], "Home page banner."), (None, "Site-wide.")):
        evaluation.add_manual_evidence(
            conn,
            scan_id=scan_id,
            criterion_sc=criterion,
            note=note,
            page_id=page_id,
            evidence_url="http://example.com/",
        )


def _insert_scan(
    conn: sqlite3.Connection, seed_url: str, status: str, *, failure_reason: str | None = None
) -> int:
    finished_at = None if status == "running" else _CURRENT_STARTED
    cur = conn.execute(
        "INSERT INTO scans (seed_url, status, page_count, finding_count, config_json, "
        "started_at, finished_at, failure_reason) VALUES (?, ?, 1, 0, '{}', ?, ?, ?)",
        (seed_url, status, _BASELINE_STARTED, finished_at, failure_reason),
    )
    return int(cur.lastrowid or 0)


def _add_scan_states(conn: sqlite3.Connection) -> dict[str, int]:
    """Reports in the states the scan detail describes with extra fields.

    Each is on its own host, so none can become the comparison baseline.
    The running scan has settled and queued work and back-dated pages, so
    ``progress`` reports a pace-based ETA range rather than "estimating".
    """
    running = _insert_scan(conn, "http://running.example.org/", "running")
    for index, render_mode in enumerate(("static", "js")):
        page = repo.upsert_page(
            conn,
            scan_id=running,
            url_normalized=f"http://running.example.org/{index}",
            status_code=200,
            title=None,
            render_mode=render_mode,
            html_hash=None,
        )
        conn.execute(
            "UPDATE pages SET fetched_at = datetime(?, ?) WHERE id = ?",
            (_BASELINE_STARTED, f"+{index} minutes", page),
        )
    # lease_until in the queue's own ISO-8601 form (see ``_scan_progress``).
    jobs = (
        ("completed", None),
        ("completed", None),
        ("leased", "2026-09-01T12:05:00+00:00"),
        ("pending", None),
    )
    for index, (state, lease_until) in enumerate(jobs):
        payload = {"scan_id": running, "url": f"http://running.example.org/{index}", "depth": 1}
        conn.execute(
            "INSERT INTO jobs (kind, payload_json, state, lease_until) VALUES ('crawl', ?, ?, ?)",
            (json.dumps(payload), state, lease_until),
        )

    blocked = _insert_scan(conn, "http://blocked.example.org/", "completed")
    repo.upsert_page(
        conn,
        scan_id=blocked,
        url_normalized="http://blocked.example.org/",
        status_code=403,
        title="Access denied",
        render_mode="static",
        html_hash=None,
    )
    failed = _insert_scan(
        conn, "http://failed.example.org/", "failed", failure_reason="The site did not respond."
    )
    return {"running": running, "blocked": blocked, "failed": failed}


def _add_contract_evidence(db_path: Path, blob_dir: Path, scan_id: int) -> dict[str, Any]:
    """Extend the shared seed until the SPA-facing fields have typed values.

    Returns the ids the endpoint templates are filled from.
    """
    conn = connect(db_path)
    try:
        baseline = _add_report_history(conn, blob_dir, scan_id)
        _add_a11y_evidence(conn, blob_dir, scan_id)
        _add_expert_review(conn, scan_id)
        states = _add_scan_states(conn)
        missing = conn.execute("SELECT MAX(id) + 1 AS id FROM scans").fetchone()
        ids = {
            "scan": scan_id,
            "baseline": baseline,
            "page": _page_ids(conn, scan_id)[0],
            # The logo's occurrence has alt text; the banner's never does.
            "finding": _logo_finding(conn, scan_id),
            "missing": int(missing["id"]),
            **states,
        }
    finally:
        conn.close()
    return ids


def _first_issue_key(client: TestClient, scan_id: int, pipeline: str) -> str:
    rows = client.get(f"/api/scans/{scan_id}/issues").json()["rows"]
    key = next(row["issue_key"] for row in rows if row["pipeline"] == pipeline)
    return quote(str(key), safe="")


def _unpinned_paths(skeleton: Any, path: str) -> Iterator[str]:
    """Yield the paths whose skeleton records no type: ``[]``, ``{}`` or only ``null``."""
    if skeleton == [] or skeleton == {}:
        yield path
    elif isinstance(skeleton, str):
        if set(skeleton.split("|")) <= {"null", _ABSENT}:
            yield path
    elif isinstance(skeleton, dict) and list(skeleton) == ["anyOf"]:
        # A scalar option such as "null" beside a structure is nullability,
        # which is pinned; only the structured options can be empty.
        for option in skeleton["anyOf"]:
            if not isinstance(option, str):
                yield from _unpinned_paths(option, path)
    elif isinstance(skeleton, dict):
        for key, value in skeleton.items():
            yield from _unpinned_paths(value, f"{path}.{key}")
    else:
        yield from _unpinned_paths(skeleton[0], f"{path}[]")


def _route(label: str) -> str:
    """``"GET /api/x?y=1 (variant)"`` -> ``"GET /api/x"``."""
    return label.split(" (")[0].split("?")[0]


def _check_seed_coverage(observed: dict[str, Any]) -> None:
    # The variants of one route are checked together: a field only one
    # variant fills (``progress`` while running, ``error`` for a bad URL) is
    # pinned by that variant's entry. Error responses are their own group.
    groups: dict[tuple[str, int], Any] = {}
    for label, record in observed.items():
        key = (_route(label), record["status"])
        body = record["body"]
        groups[key] = _union(groups[key], body) if key in groups else body
    unpinned = {
        (route, path)
        for (route, _status), body in groups.items()
        for path in _unpinned_paths(body, "body")
    }
    uncovered = sorted(unpinned - _UNPINNED_PATHS.keys())
    stale = sorted(_UNPINNED_PATHS.keys() - unpinned)
    problems = []
    if uncovered:
        problems.append(
            "These paths are empty or always null, so the golden pins nothing about "
            "them. Extend _add_contract_evidence until they carry a value, or list "
            "them in _UNPINNED_PATHS with the reason:\n"
            + "\n".join(f"  {route}: {path}" for route, path in uncovered)
        )
    if stale:
        problems.append(
            "These _UNPINNED_PATHS entries now carry a value; remove them:\n"
            + "\n".join(f"  {route}: {path}" for route, path in stale)
        )
    if problems:
        pytest.fail("\n".join(problems), pytrace=False)


def test_read_endpoint_shapes_match_golden(
    client: TestClient, seeded_db: tuple[Path, Path, int]
) -> None:
    db_path, blob_dir, scan_id = seeded_db
    ids = _add_contract_evidence(db_path, blob_dir, scan_id)
    for pipeline in ("axe", "image", "alfa"):
        ids[f"{pipeline}_issue"] = _first_issue_key(client, scan_id, pipeline)

    observed: dict[str, Any] = {}
    for label, template in _ENDPOINTS:
        response = client.get(template.format(**ids))
        observed[label] = {
            "status": response.status_code,
            "content_type": response.headers.get("content-type"),
            "body": _skeleton(response.json()),
        }
    # Before the golden, so a golden cannot be regenerated from a seed that
    # has stopped exercising a field.
    _check_seed_coverage(observed)
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


def test_unpinned_paths_finds_empty_and_always_null_fields() -> None:
    skeleton = {
        "empty_list": [],
        "empty_object": {},
        "null": "null",
        "sometimes_missing_null": "absent|null",
        "nullable_string": "null|string",
        "rows": [{"anyOf": ["null", {"inner": "null", "typed": "integer"}]}],
    }
    assert sorted(_unpinned_paths(skeleton, "body")) == [
        "body.empty_list",
        "body.empty_object",
        "body.null",
        "body.rows[].inner",
        "body.sometimes_missing_null",
    ]


def test_skeleton_rejects_non_json_values() -> None:
    with pytest.raises(TypeError):
        _skeleton({"when": object()})
