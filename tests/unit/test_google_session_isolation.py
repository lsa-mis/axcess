"""The Google sign-in belongs to the document check alone (the developer's rule, 2026-11-26).

The website checks (Click-Through, the form check, keyboard, zoom, focus,
page code, axe, Alfa, page loading) and their browsers must behave exactly
as before: no Google route guard, no blocked click, no changed context. So:

- no module of the crawler, the page checks (analyzer), the sign-in scans
  (protected) or the page fetchers imports the Google session;
- ``run_crawl`` hands the session to the tracker and closes it, nothing else;
- the session opens its own browser and never takes someone else's
  context or page;
- a real (static) crawl with a recording stand-in uses it only through the
  tracker's ``GoogleFiles`` methods.
"""

from __future__ import annotations

import ast
import inspect
import sqlite3
import textwrap
from pathlib import Path
from typing import Any

import httpx

from audit.crawler import orchestrator
from audit.crawler.orchestrator import CrawlConfig, run_crawl
from audit.linked_files.fetch import FetchedFile
from audit.linked_files.google_session import DatesRead, GoogleBrowserSession

SRC = Path(__file__).resolve().parents[2] / "src" / "audit"
#: Packages that must never see the Google session.
_KEPT_APART = ("crawler", "analyzer", "protected", "extractor")
_SESSION_MODULE = "audit.linked_files.google_session"


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
            found.update(f"{node.module}.{alias.name}" for alias in node.names)
    return found


def test_the_crawler_and_page_checks_never_import_the_google_session() -> None:
    offenders = []
    checked = 0
    for package in _KEPT_APART:
        for path in sorted((SRC / package).rglob("*.py")):
            checked += 1
            if _SESSION_MODULE in _imports(path) or "google_session" in path.read_text(
                encoding="utf-8"
            ):
                offenders.append(str(path.relative_to(SRC)))
    assert checked > 50, "the scan reads the packages it means to"
    assert offenders == []


def test_run_crawl_only_hands_the_session_to_the_tracker_and_closes_it() -> None:
    """Every use of ``google_files`` in ``run_crawl``: a None check, the
    tracker's ``attach_downloads(google=...)``, or ``.close()``."""
    function = ast.parse(textwrap.dedent(inspect.getsource(run_crawl))).body[0]
    parents: dict[ast.AST, ast.AST] = {}
    for node in ast.walk(function):
        for child in ast.iter_child_nodes(node):
            parents[child] = node
    uses: list[str] = []
    for node in ast.walk(function):
        if not (isinstance(node, ast.Name) and node.id == "google_files"):
            continue
        parent = parents[node]
        if isinstance(parent, ast.Compare):
            uses.append("checked")
        elif isinstance(parent, ast.Attribute) and parent.attr == "close":
            uses.append("closed")
        elif (
            isinstance(parent, ast.keyword)
            and parent.arg == "google"
            and isinstance(call := parents[parent], ast.Call)
            and isinstance(call.func, ast.Attribute)
            and call.func.attr == "attach_downloads"
        ):
            uses.append("tracker")
        else:
            uses.append(f"other: {ast.dump(parent)[:80]}")
    assert [use for use in uses if use.startswith("other")] == []
    assert uses.count("tracker") == 1
    assert "closed" in uses


def test_the_session_never_takes_another_browser() -> None:
    """No public method accepts a context, page or browser: the only browser
    it guards is the one it launched (``enter_scan_mode``)."""
    for name, member in inspect.getmembers(GoogleBrowserSession, inspect.isfunction):
        if name.startswith("_"):
            continue
        params = set(inspect.signature(member).parameters) - {"self"}
        assert params <= {"url", "address", "callback"}, (name, params)


class _Recorder:
    """The tracker's ``GoogleFiles``, recording every attribute asked for."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def __getattribute__(self, name: str) -> Any:
        if not name.startswith("_") and name != "calls":
            object.__getattribute__(self, "calls").append(name)
        return object.__getattribute__(self, name)

    @property
    def active(self) -> bool:
        return True

    def allow_file(self, url: str) -> bool:
        return True

    async def fetch_export(self, address: str) -> FetchedFile:
        return FetchedFile("http_error", 401)

    async def fetch_drive(self, url: str) -> FetchedFile:
        return FetchedFile("http_error", 401)

    async def read_dates(self, url: str) -> DatesRead:
        return DatesRead("none")

    async def close(self) -> None:
        return None


SEED = "https://site.test/"
DOC = "https://docs.google.com/document/d/1docAAAAAAAAAAAAAAAAAA/edit"


async def test_a_crawl_uses_the_session_only_through_the_document_check(
    tmp_db: sqlite3.Connection,
) -> None:
    asked: list[str] = []

    def site(request: httpx.Request) -> httpx.Response:
        asked.append(str(request.url))
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(
            200,
            headers={"content-type": "text/html; charset=utf-8"},
            text=f'<!doctype html><html lang=en><title>t</title><a href="{DOC}">Doc</a></html>',
        )

    recorder = _Recorder()
    config = CrawlConfig(
        seed_url=SEED,
        max_pages=1,
        rps=100.0,
        workers=1,
        js_enabled=False,
        js_eager=False,
        axe_enabled=False,
        alfa_enabled=False,
        ocr_enabled=False,
        vlm_enabled=False,
        semantic_enabled=False,
        keyboard_probe_enabled=False,
        responsive_checks_enabled=False,
        focus_checks_enabled=False,
        visual_checks_enabled=False,
        interaction_checks_enabled=False,
        synthesize_enabled=False,
        image_extraction_enabled=False,
        google_sign_in=True,
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(site)) as client:
        summary = await run_crawl(tmp_db, config, http_client=client, google_files=recorder)
    assert summary.pages_fetched == 1
    # The page came through the crawl's own client; the Doc's export did not.
    assert SEED in asked
    assert not [url for url in asked if "/export" in url]
    # Only the tracker's methods, and the crawl's close at the end.
    assert set(recorder.calls) <= {
        "active",
        "allow_file",
        "fetch_export",
        "fetch_drive",
        "read_dates",
        "close",
    }
    assert "fetch_export" in recorder.calls
    assert recorder.calls.count("close") == 1
    stored = tmp_db.execute("SELECT config_json FROM scans").fetchone()[0]
    assert '"google_sign_in": true' in stored


def test_the_orchestrator_module_itself_has_no_google_behaviour() -> None:
    """Beyond the pass-through, no Google host or Google action in the crawl."""
    source = inspect.getsource(orchestrator)
    for word in ("accounts.google.com", "docs.google.com", "read_dates(", "fetch_export("):
        assert word not in source, word


# -- sign-in scans with "Sign in to Google for Google files" (2026-11-26) ------
# Two separate browsers, one after another: the site's own signed-in browser
# runs every website check as before; the Google browser is the document
# check's alone.


def test_the_session_is_built_from_nothing_of_another_browser() -> None:
    """Its constructor takes no context, page, request or session: only how
    to start its own Playwright, where its profile goes, and its pacing."""
    params = set(inspect.signature(GoogleBrowserSession.__init__).parameters) - {"self"}
    assert params == {
        "playwright_start",
        "profile_base",
        "pace_s",
        "clock",
        "sleep",
        "nav_timeout_ms",
    }


def test_the_sign_in_scan_hands_the_google_session_only_to_the_crawl() -> None:
    """In ``_run_local_login_background``, ``run.google`` is only checked,
    passed to ``run_crawl(google_files=...)``, and closed: never handed to
    the site session (``run.session``) or a page check."""
    from audit.web import server

    function = ast.parse(textwrap.dedent(inspect.getsource(server._run_local_login_background)))
    parents: dict[ast.AST, ast.AST] = {}
    for node in ast.walk(function):
        for child in ast.iter_child_nodes(node):
            parents[child] = node
    uses: list[str] = []
    for node in ast.walk(function):
        if not (
            isinstance(node, ast.Attribute)
            and node.attr == "google"
            and isinstance(node.value, ast.Name)
            and node.value.id == "run"
        ):
            continue
        parent = parents[node]
        if isinstance(parent, ast.Compare):
            uses.append("checked")
        elif isinstance(parent, ast.Attribute) and parent.attr == "close":
            uses.append("closed")
        elif (
            isinstance(parent, ast.keyword)
            and parent.arg == "google_files"
            and isinstance(call := parents[parent], ast.Call)
            and isinstance(call.func, ast.Name)
            and call.func.id == "run_crawl"
        ):
            uses.append("crawl")
        else:
            uses.append(f"other: {ast.dump(parent)[:80]}")
    assert [use for use in uses if use.startswith("other")] == []
    assert uses.count("crawl") == 1
    assert "closed" in uses
    # And nothing named "google" goes into a call on the site session.
    for node in ast.walk(function):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Attribute)
            and node.func.value.attr == "session"
        ):
            assert "google" not in ast.dump(node), ast.dump(node)[:120]


def test_the_site_session_module_knows_nothing_of_google() -> None:
    source = (SRC / "protected" / "session.py").read_text(encoding="utf-8")
    assert "google" not in source.lower()


def test_the_two_profiles_are_different_folders_with_different_prefixes(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """The site browser's start deletes every ``axcess-protected-browser-*``
    folder in its root; a Google profile is in another root, with another
    prefix, so it survives that sweep, and the reverse."""
    import tempfile

    from audit.linked_files import google_session
    from audit.protected import session as site_session

    assert not google_session.PROFILE_PREFIX.startswith(site_session._EPHEMERAL_PROFILE_PREFIX)
    assert not site_session._EPHEMERAL_PROFILE_PREFIX.startswith(google_session.PROFILE_PREFIX)
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    google_dir = google_session.create_profile_dir()
    try:
        site_dir = site_session._create_ephemeral_profile_dir()
        assert Path(google_dir).parent != Path(site_dir).parent
        assert Path(google_dir).parent.name == google_session.PROFILE_ROOT_NAME
        assert Path(google_dir).is_dir(), "the site browser's sweep removed the Google profile"
        # A second site browser start sweeps its own prefix only.
        site_session._create_ephemeral_profile_dir()
        assert Path(google_dir).is_dir()
        # A second Google session keeps the live site profile too.
        other_google = google_session.create_profile_dir()
        google_session.remove_profile_dir(other_google)
        assert not any(
            entry.name.startswith(site_session._EPHEMERAL_PROFILE_PREFIX)
            for entry in Path(google_dir).parent.iterdir()
        )
    finally:
        google_session.remove_profile_dir(google_dir)


async def test_a_sign_in_scan_with_google_needs_the_site_file_fetcher(
    tmp_db: sqlite3.Connection,
) -> None:
    """Every file that is not a Google file downloads through the site's
    sign-in, never anonymously: without that fetcher the crawl refuses to
    start, and the Google sign-in is closed (signed out, data deleted)."""
    import pytest

    recorder = _Recorder()
    config = CrawlConfig(seed_url=SEED, documents_signed_in=True, google_sign_in=True)
    with pytest.raises(ValueError, match="signed-in file fetcher"):
        await run_crawl(tmp_db, config, google_files=recorder)
    assert recorder.calls == ["close"]
