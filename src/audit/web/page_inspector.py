"""On-demand, scan-scoped single-page renderer for the Page/DOM inspector.

The review UI wants to show *the exact page* (rendered HTML) beside *the
loaded DOM* (serialized HTML) without sending the auditor to the live site in
a new tab. Since migration 0027 the crawl persists each page's rendered
document (gzip) in ``pages.rendered_html``, so the inspector serves that
stored capture instantly. When nothing is stored, a scan predating the
column, a too-large/non-HTML page, or a scan configured with
``store_rendered_html=False``, it falls back to re-loading the single page
on demand in a throwaway browser.

Nothing is persisted by this module: the fallback render returns the
rendered HTML transiently, and the highlight ("point at the issue") is
applied client-side as a CSS outline on the returned DOM, there is no
screenshot capture, no blob, no image row, and no persistence of any kind.

This module is deliberately narrow and defensive:

* It re-fetches **one URL the scan already recorded**, never an arbitrary
  URL, never a cross-scan target. The endpoint is keyed by ``scan_id`` +
  ``page_id``, and the page must belong to that scan.
* It refuses anything that would not be a faithful, safe re-render: scans
  that are not ``completed`` (running/failed/interrupted would show a stale
  or partial page), records that belong to a login-protected report (whose
  session cannot be re-created here), and any target URL that falls outside
  the scan's recorded scope (host + registrable domain, honoring the scan's
  ``allow_subdomains`` setting).
* It bounds the work: a navigation/idle timeout and a cap on the serialized
  DOM length (truncated with an honest flag).

The fallback render itself is a throwaway Playwright browser, one page, no
probes, no axe pass, no crawl state. Rendering is explicitly an external
fetch, so this must only ever be reached behind the existing access-token
gate and a non-protected, completed report.
"""

from __future__ import annotations

import contextlib
import gzip
import json
import sqlite3
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from audit.crawler import url_policy

if TYPE_CHECKING:
    from playwright.async_api import ViewportSize

# Generous cap so a genuinely large rendered document is still inspectable
# without letting one pathological page feed an unbounded string into the
# browser JSON response.
MAX_INSPECT_DOM_CHARS = 2_000_000

_DEFAULT_VIEWPORT: ViewportSize = {"width": 1440, "height": 900}
_NAV_TIMEOUT_MS = 30_000
_IDLE_TIMEOUT_MS = 8_000


class InspectionUnavailableError(Exception):
    """A refusal that maps to an HTTP status + message in the API layer.

    Distinct from a *render* failure (the page is valid but could not be
    captured): this means the request cannot legitimately be inspected at
    all, so the caller should surface a non-2xx response.
    """

    def __init__(self, message: str, status_code: int = 409) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.detail = message


def _is_protected_report(conn: sqlite3.Connection, scan_id: int) -> bool:
    """True when ``scan_id`` belongs to a login-protected report.

    Guarded by a ``sqlite_master`` check because older databases may not have
    the ``protected_scans`` table yet; a missing table means none are
    protected, which is the correct behavior for a public/local install.
    """
    if not conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='protected_scans'"
    ).fetchone():
        return False
    return (
        conn.execute(
            "SELECT 1 FROM protected_scans WHERE scan_id = ? LIMIT 1",
            (scan_id,),
        ).fetchone()
        is not None
    )


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    """True when ``table`` is present, for schemas that predate it."""
    return (
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name = ?", (table,)
        ).fetchone()
        is not None
    )


def _dom_states(conn: sqlite3.Connection, page_id: int) -> list[dict[str, Any]]:
    """The states captured on this page, in the order the probe reached them.

    Metadata only. The documents are megabytes each and a reviewer looks at one
    at a time, so they are fetched per state rather than shipped together.
    """
    if not _table_exists(conn, "page_dom_states"):
        return []
    rows = conn.execute(
        "SELECT state_key, revealed_by, path_labels FROM page_dom_states "
        "WHERE page_id = ? ORDER BY rowid",
        (page_id,),
    ).fetchall()
    states: list[dict[str, Any]] = []
    for row in rows:
        try:
            path = json.loads(row["path_labels"] or "[]")
        except (ValueError, TypeError):
            path = []
        states.append(
            {
                "state_key": row["state_key"],
                "revealed_by": row["revealed_by"],
                "path_labels": [str(item) for item in path] if isinstance(path, list) else [],
            }
        )
    return states


def _decode_state_html(
    conn: sqlite3.Connection, page_id: int, state_key: str
) -> str | None:
    """The captured markup for one state, or None when it was never stored."""
    if not _table_exists(conn, "page_dom_states"):
        return None
    row = conn.execute(
        "SELECT dom, encoding FROM page_dom_states WHERE page_id = ? AND state_key = ?",
        (page_id, state_key),
    ).fetchone()
    if row is None or row["encoding"] != "gzip":
        return None
    return _decode_stored_html(row["dom"])


def _has_column(conn: sqlite3.Connection, table: str, column: str) -> bool:
    """True when ``table`` already carries ``column``.

    ``pages.rendered_html`` arrived in migration 0027, and this module is
    reachable from a server running against a database that stopped earlier —
    naming the column unconditionally raised ``OperationalError`` out of the
    route as a 500. A missing column means nothing was stored, which is the
    same state as a scan that opted out of storing, so the caller already
    knows how to fall back.
    """
    return any(
        row["name"] == column
        for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
    )


def _assert_in_scope(target_url: str, seed_url: str, allow_subdomains: bool) -> None:
    """Refuse a target URL that is not within the scan's recorded scope.

    Reconstructs the scope from the scan's own ``seed_url`` and uses the
    same :func:`audit.crawler.url_policy.is_in_scope` the crawler used. The
    scope is built with ``whole_host=True`` so the path-prefix constraint
    cannot over-reject, a page recorded through a client-side redirect may
    legitimately sit outside the seed's literal path prefix, but must still
    live on the same site.
    """
    if not seed_url:
        raise InspectionUnavailableError(
            "This scan has no seed URL to verify scope against.", status_code=409
        )
    try:
        scope = url_policy.build_scope(seed_url, whole_host=True)
    except ValueError:
        raise InspectionUnavailableError(
            "This scan has an invalid seed URL.", status_code=409
        ) from None
    if not url_policy.is_in_scope(target_url, scope, allow_subdomains=allow_subdomains):
        raise InspectionUnavailableError(
            "The page is outside this scan's recorded scope.", status_code=409
        )


def _validate(conn: sqlite3.Connection, scan_id: int, page_id: int) -> dict[str, Any]:
    """Load + authorize the request, returning the pieces the renderer needs.

    Raises :class:`InspectionUnavailableError` for any refusal. The returned
    dict carries the scan row, the page row, the resolved target URL, and the
    scope-relevant config so the caller never re-parses JSON.
    """
    scan = conn.execute(
        "SELECT id, status, seed_url, config_json FROM scans WHERE id = ?",
        (scan_id,),
    ).fetchone()
    if scan is None:
        raise InspectionUnavailableError("Scan not found.", status_code=404)
    if scan["status"] != "completed":
        raise InspectionUnavailableError(
            "Only a completed report can be inspected on demand. "
            "This scan is still running or did not finish.",
            status_code=409,
        )
    if _is_protected_report(conn, scan_id):
        raise InspectionUnavailableError(
            "This is a login-protected report and cannot be re-rendered on demand.",
            status_code=409,
        )
    stored_column = (
        "rendered_html" if _has_column(conn, "pages", "rendered_html") else "NULL"
    )
    page = conn.execute(
        "SELECT id, url_normalized, title, status_code, render_mode, "
        f"{stored_column} AS rendered_html, fetched_at "
        "FROM pages WHERE id = ? AND scan_id = ?",
        (page_id, scan_id),
    ).fetchone()
    if page is None:
        raise InspectionUnavailableError("Page is not part of this report.", status_code=404)

    try:
        config = json.loads(scan["config_json"] or "{}")
    except (ValueError, TypeError):
        config = {}
    allow_subdomains = bool(config.get("allow_subdomains"))
    # Older configs predate the toggle and default to storing.
    store_rendered_html = bool(config.get("store_rendered_html", True))
    seed_url = scan["seed_url"] or config.get("start_url") or ""
    target_url = page["url_normalized"]
    _assert_in_scope(target_url, seed_url, allow_subdomains)

    return {
        "scan": scan,
        "page": page,
        "target_url": target_url,
        "store_rendered_html": store_rendered_html,
    }


async def _render_page(
    url: str,
    *,
    user_agent: str,
    viewport: ViewportSize,
    nav_timeout_ms: int,
    idle_timeout_ms: int,
) -> tuple[dict[str, Any] | None, str | None]:
    """Load ``url`` once in a throwaway headless Chromium.

    Returns ``(outcome, error)``. ``outcome`` is ``None`` when navigation or
    content-type makes a faithful capture impossible; the ``error`` string
    explains why and is surfaced to the operator. ``outcome`` carries the
    serialized rendered DOM, the final URL (a page may client-side redirect),
    and the live status code. Nothing is written to disk.
    """
    from playwright.async_api import async_playwright

    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            try:
                ctx = await browser.new_context(
                    user_agent=user_agent,
                    viewport=viewport,
                    service_workers="block",
                    accept_downloads=False,
                )
                page = await ctx.new_page()
                try:
                    resp = await page.goto(url, timeout=nav_timeout_ms, wait_until="load")
                except Exception as exc:
                    return None, f"Could not load the page: {exc}"
                if resp is None:
                    return None, "Browser navigation returned no document response."
                with contextlib.suppress(Exception):
                    await page.wait_for_load_state("networkidle", timeout=idle_timeout_ms)

                content_type = resp.headers.get("content-type", "text/html")
                status = resp.status
                if not (200 <= status < 300) or "text/html" not in content_type:
                    return None, (
                        f"The page returned {status} "
                        f"({content_type.split(';')[0].strip()}), so there is no "
                        "rendered HTML to show."
                    )

                dom = await page.content()
                return (
                    {
                        "dom_html": dom,
                        "final_url": page.url,
                        "status_code": status,
                    },
                    None,
                )
            finally:
                await browser.close()
    except Exception as exc:  # pragma: no cover - unexpected browser error
        return None, f"Inspection failed: {exc}"


def _page_payload(page: dict[str, Any], *, captured_at: str | None) -> dict[str, Any]:
    return {
        "id": page["id"],
        "url": page["url_normalized"],
        "title": page["title"],
        # Status recorded at scan time, the live re-render status is on the
        # render payload, so both are available to the UI.
        "status_code": page["status_code"],
        "render_mode": page["render_mode"],
        "captured_at": captured_at,
    }


def _decode_stored_html(blob: bytes | None) -> str | None:
    """Gunzip a persisted rendered document back to HTML text.

    Returns ``None`` when there is nothing stored or the bytes are not a valid
    gzip stream (e.g. an empty/zero-length page), the caller then falls back
    to an on-demand render.
    """
    if not blob:
        return None
    try:
        return gzip.decompress(blob).decode("utf-8", errors="replace")
    except Exception:
        return None


def _iso_timestamp(value: Any) -> str | None:
    """Normalize a page ``fetched_at`` value to an ISO-8601 string."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


async def inspect_page(
    conn: sqlite3.Connection,
    *,
    scan_id: int,
    page_id: int,
    user_agent: str,
    viewport: ViewportSize | None = None,
    nav_timeout_ms: int = _NAV_TIMEOUT_MS,
    idle_timeout_ms: int = _IDLE_TIMEOUT_MS,
    max_dom_chars: int = MAX_INSPECT_DOM_CHARS,
    state_key: str | None = None,
) -> dict[str, Any]:
    """Serve one scan-scoped page for the Page/DOM inspector.

    Prefers the rendered HTML persisted at scan time (instant, offline, no
    browser); only when that is absent (a scan predating persistence, or a
    too-large/non-HTML page) does it re-render on demand. A valid page whose
    HTML can't be produced returns a ``render.ok: False`` payload (HTTP 200);
    an invalid/non-inspectable request raises
    :class:`InspectionUnavailableError`. Nothing is persisted.

    ``state_key`` asks for one of the DOM states the interaction probe
    captured instead of the page as it loaded. A state that was never captured
    is reported as missing and **never** substituted with a live render: that
    render is the page loading now, which is precisely the state the reviewer
    said they did not want, and passing it off as the dialog they asked for
    would be a more convincing version of the bug this all exists to fix.
    """
    validated = _validate(conn, scan_id, page_id)
    page = validated["page"]
    states = _dom_states(conn, page_id)

    if state_key:
        captured = _decode_state_html(conn, page_id, state_key)
        return {
            "page": _page_payload(page, captured_at=_iso_timestamp(page["fetched_at"])),
            "store_rendered_html": validated["store_rendered_html"],
            "states": states,
            "render": (
                _render_payload(
                    ok=True,
                    source="state",
                    final_url=page["url_normalized"],
                    status_code=page["status_code"],
                    dom_html=captured,
                    max_dom_chars=max_dom_chars,
                )
                | {"state_key": state_key}
                if captured is not None
                else {
                    "ok": False,
                    "source": "state",
                    "state_key": state_key,
                    "error": (
                        "This interaction state was not captured. Reports made "
                        "before state capture, and scans that declined to store "
                        "rendered pages, keep no markup for it."
                    ),
                }
            ),
        }

    stored = _decode_stored_html(page["rendered_html"])
    if stored is not None:
        return {
            "page": _page_payload(page, captured_at=_iso_timestamp(page["fetched_at"])),
            "store_rendered_html": validated["store_rendered_html"],
            "states": states,
            "render": _render_payload(
                ok=True,
                source="stored",
                final_url=page["url_normalized"],
                status_code=page["status_code"],
                dom_html=stored,
                max_dom_chars=max_dom_chars,
            ),
        }

    # ``timezone.utc`` is used over the ``datetime.UTC`` alias because mypy's
    # bundled 3.11 typeshed here does not expose the alias yet.
    captured_at = datetime.now(timezone.utc).isoformat()  # noqa: UP017
    outcome, error = await _render_page(
        validated["target_url"],
        user_agent=user_agent,
        viewport=viewport or _DEFAULT_VIEWPORT,
        nav_timeout_ms=nav_timeout_ms,
        idle_timeout_ms=idle_timeout_ms,
    )

    if outcome is None:
        return {
            "page": _page_payload(page, captured_at=captured_at),
            "store_rendered_html": validated["store_rendered_html"],
            "states": states,
            "render": {
                "ok": False,
                "source": "live",
                "error": error or "The page could not be rendered.",
            },
        }

    return {
        "page": _page_payload(page, captured_at=captured_at),
        "store_rendered_html": validated["store_rendered_html"],
        "states": states,
        "render": _render_payload(
            ok=True,
            source="live",
            final_url=outcome["final_url"],
            status_code=outcome["status_code"],
            dom_html=outcome["dom_html"],
            max_dom_chars=max_dom_chars,
        ),
    }


def _render_payload(
    *,
    ok: bool,
    source: str,
    final_url: str | None,
    status_code: int | None,
    dom_html: str | None,
    max_dom_chars: int,
) -> dict[str, Any]:
    """Shape the ``render`` object, truncating the DOM to the honest bound."""
    dom = dom_html or ""
    dom_truncated = len(dom) > max_dom_chars
    if dom_truncated:
        dom = dom[:max_dom_chars]
    return {
        "ok": ok,
        "source": source,
        "final_url": final_url,
        "status_code": status_code,
        "dom_html": dom,
        "dom_chars": max_dom_chars if dom_truncated else len(dom),
        "dom_truncated": dom_truncated,
    }
