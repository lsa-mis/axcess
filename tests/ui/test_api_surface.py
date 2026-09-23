"""Characterization of the FastAPI app that ``create_app()`` assembles.

Pins the route table in registration order (type, path, methods, name,
sync/async handler, wire parameter names), the middleware stack, exception
handlers, startup/shutdown hooks, and the exact OpenAPI document. Splitting
``create_app()`` into ``APIRouter`` modules must leave every one of these
unchanged; a failure here is the refactor changing behavior, not noise.

``create_app()`` has two build-time branches, so the structure is recorded
for each combination: the ``AUDIT_ACCESS_TOKEN`` gate adds a middleware, and
a built frontend adds the ``/app/assets`` and ``/app/fonts`` static mounts.
Goldens live in ``golden/``; see ``_golden.py`` for how to regenerate them.
"""

from __future__ import annotations

import inspect
import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.dependencies.utils import get_flat_dependant
from fastapi.routing import APIRoute
from starlette.routing import BaseRoute, Mount

from audit.web import server

from ._golden import check_golden_document, check_golden_entry, check_golden_keys

pytestmark = pytest.mark.ui

_SURFACE_GOLDEN = "api_surface.json"
_OPENAPI_GOLDEN = "api_openapi.json"

_GATE_VARIANTS = ("token-unset", "token-set")
_DIST_VARIANTS = ("dist-absent", "dist-built")


def _db_path(conn: sqlite3.Connection) -> Path:
    # The root ``tmp_db`` fixture yields a connection, not its path.
    return Path(conn.execute("PRAGMA database_list").fetchone()[2])


def _build_app(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    db_path: Path,
    *,
    gate: str,
    dist: str,
) -> FastAPI:
    # ``get_settings()`` builds a fresh Settings on every call (no cache to
    # clear), so the env var alone decides the gate. Unset is spelled as an
    # empty value rather than a deletion so a developer's ``.env`` cannot
    # switch the gate on for the unset variant.
    monkeypatch.setenv("AUDIT_ACCESS_TOKEN", "golden-token" if gate == "token-set" else "")
    if dist == "dist-built":
        # create_app mounts assets/ and fonts/ only when they are
        # directories; the SPA shell reads index.html per request.
        dist_dir = tmp_path / "dist"
        (dist_dir / "assets").mkdir(parents=True, exist_ok=True)
        (dist_dir / "fonts").mkdir(exist_ok=True)
        (dist_dir / "assets" / "index.js").write_text("", encoding="utf-8")
        (dist_dir / "fonts" / "font.woff2").write_bytes(b"")
        (dist_dir / "index.html").write_text("<!doctype html>", encoding="utf-8")
    else:
        dist_dir = tmp_path / "no-dist"
    monkeypatch.setattr(server, "_FRONTEND_DIST", dist_dir)
    blob_dir = tmp_path / "blobs"
    blob_dir.mkdir(exist_ok=True)
    return server.create_app(db_path=db_path, blob_dir=blob_dir)


def _qualified(obj: Any) -> str:
    if isinstance(obj, type):
        return f"{obj.__module__}.{obj.__qualname__}"
    return str(obj)


def _describe_route(route: BaseRoute) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "type": type(route).__name__,
        "path": getattr(route, "path", None),
        "methods": sorted(getattr(route, "methods", None) or []),
        "name": getattr(route, "name", None),
    }
    if isinstance(route, APIRoute):
        # The flattened dependant lists every parameter the request is
        # parsed for, including any a refactor moves into a ``Depends``;
        # ``alias`` is the name on the wire, which is what clients send.
        # Empty kinds are left out to keep the golden short.
        flat = get_flat_dependant(route.dependant)
        params = {
            "path": [p.alias for p in flat.path_params],
            "query": [p.alias for p in flat.query_params],
            "header": [p.alias for p in flat.header_params],
            "cookie": [p.alias for p in flat.cookie_params],
            "body": [p.alias for p in flat.body_params],
        }
        entry["async"] = inspect.iscoroutinefunction(route.endpoint)
        entry["params"] = {kind: names for kind, names in params.items() if names}
        entry["request_param"] = route.dependant.request_param_name
        entry["background_tasks_param"] = route.dependant.background_tasks_param_name
    if isinstance(route, Mount):
        entry["app"] = type(route.app).__name__
    return entry


def _describe_app(app: FastAPI) -> dict[str, Any]:
    return {
        "routes": [_describe_route(route) for route in app.routes],
        # Outermost first, as Starlette stores it. Decorator middleware is
        # a BaseHTTPMiddleware wrapping a named dispatch function; the rest
        # are recorded with their constructor keyword names (values hold
        # tmp paths and sizes, which are configuration, not structure).
        "middleware": [
            [
                m.cls.__name__,
                getattr(m.kwargs.get("dispatch"), "__name__", None),
                sorted(k for k in m.kwargs if k != "dispatch"),
            ]
            for m in app.user_middleware
        ],
        # Handler names too: dropping the custom validation handler would
        # leave FastAPI's default registered under the same key.
        "exception_handlers": {
            _qualified(exc): getattr(handler, "__name__", repr(handler))
            for exc, handler in sorted(
                app.exception_handlers.items(), key=lambda item: _qualified(item[0])
            )
        },
        "on_startup": [fn.__name__ for fn in app.router.on_startup],
        "on_shutdown": [fn.__name__ for fn in app.router.on_shutdown],
    }


@pytest.mark.parametrize("dist", _DIST_VARIANTS)
@pytest.mark.parametrize("gate", _GATE_VARIANTS)
def test_app_structure_matches_golden(
    tmp_db: sqlite3.Connection,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    gate: str,
    dist: str,
) -> None:
    app = _build_app(monkeypatch, tmp_path, _db_path(tmp_db), gate=gate, dist=dist)
    check_golden_entry(_SURFACE_GOLDEN, f"{gate}/{dist}", _describe_app(app))


def test_structure_golden_holds_exactly_the_build_variants() -> None:
    # Each variant above checks only its own entry, so without this a
    # renamed or dropped variant would leave a stale entry nobody reads.
    expected = {f"{gate}/{dist}" for gate in _GATE_VARIANTS for dist in _DIST_VARIANTS}
    check_golden_keys(_SURFACE_GOLDEN, expected)


def test_openapi_document_matches_golden_in_every_variant(
    tmp_db: sqlite3.Connection,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``json.dumps(app.openapi())`` is pinned as an exact string.

    Neither build-time branch reaches the schema (the token gate is
    middleware and static mounts are not API routes), so one golden serves
    all four variants; the loop proves that before comparing.
    """
    db_path = _db_path(tmp_db)
    documents: dict[str, dict[str, Any]] = {}
    for gate in _GATE_VARIANTS:
        for dist in _DIST_VARIANTS:
            app = _build_app(monkeypatch, tmp_path, db_path, gate=gate, dist=dist)
            documents[f"{gate}/{dist}"] = app.openapi()
    texts = {variant: json.dumps(document) for variant, document in documents.items()}
    reference = texts["token-unset/dist-absent"]
    diverged = sorted(variant for variant, text in texts.items() if text != reference)
    assert not diverged, (
        f"OpenAPI now differs by build variant ({diverged}); record one golden per variant."
    )
    check_golden_document(_OPENAPI_GOLDEN, documents["token-unset/dist-absent"])
