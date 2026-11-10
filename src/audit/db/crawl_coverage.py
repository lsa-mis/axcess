"""The pages a crawl knew about, and the count of those it did not visit.

One row per in-scope address in ``crawl_known_urls`` (migration 0032). The
orchestrator writes a row the moment it learns of an address, from the start
address, a sitemap, or a page, before deciding whether to queue it. That is
what lets a report say how many pages it left out: an address the crawl
refused or never reached still has a row, with no ``visited`` outcome.

A report counts three reasons, and only these:

* ``page_limit``: known, within the depth limit, never visited, and the scan
  stopped because it reached its page limit.
* ``depth_limit``: known, never visited, and found only more steps from the
  start than the depth limit allows.
* ``blocked``: refused by robots.txt, the blocked-address patterns (a sign-out
  link) or the operator's excluded addresses.

Out-of-scope addresses are never recorded: they are not pages under the
starting address, so they are not pages the report missed.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlsplit, urlunsplit

Outcome = Literal["visited", "duplicate", "blocked", "failed"]
Via = Literal["link", "sitemap"]


@dataclass(frozen=True, slots=True)
class KnownUrl:
    """What the crawl knows about one address after recording it."""

    min_depth: int
    outcome: str | None
    new: bool


@dataclass(frozen=True, slots=True)
class UnvisitedCounts:
    """Known pages a finished scan did not visit, by reason."""

    page_limit: int
    depth_limit: int
    blocked: int


def directory_twin(url: str) -> str | None:
    """The same address with a trailing slash, for a folder-like path.

    ``/docs/guides`` and ``/docs/guides/`` are one page on nearly every server
    (the first redirects to the second). A path whose last part has a dot
    (``/a.html``) is a file and has no twin.
    """
    parts = urlsplit(url)
    path = parts.path or "/"
    if path.endswith("/") or "." in path.rsplit("/", 1)[-1]:
        return None
    return urlunsplit(parts._replace(path=path + "/"))


def note_known(
    conn: sqlite3.Connection,
    *,
    scan_id: int,
    url: str,
    depth: int,
    via: Via,
) -> KnownUrl:
    """Record that the crawl learned of ``url`` at ``depth``; return its state.

    Repeat sightings only widen what is known: a link sets ``linked`` even if a
    sitemap listed the page first, and a shorter path lowers ``min_depth``.
    """
    linked = 1 if via == "link" else 0
    in_sitemap = 1 if via == "sitemap" else 0
    existed = (
        conn.execute(
            "SELECT 1 FROM crawl_known_urls WHERE scan_id = ? AND url_normalized = ?",
            (scan_id, url),
        ).fetchone()
        is not None
    )
    row = conn.execute(
        """
        INSERT INTO crawl_known_urls (scan_id, url_normalized, linked, in_sitemap, min_depth)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(scan_id, url_normalized) DO UPDATE SET
            linked = MAX(linked, excluded.linked),
            in_sitemap = MAX(in_sitemap, excluded.in_sitemap),
            min_depth = MIN(min_depth, excluded.min_depth)
        RETURNING min_depth, outcome
        """,
        (scan_id, url, linked, in_sitemap, depth),
    ).fetchone()
    return KnownUrl(min_depth=int(row["min_depth"]), outcome=row["outcome"], new=not existed)


def get_known(conn: sqlite3.Connection, *, scan_id: int, url: str) -> KnownUrl | None:
    """The stored state of ``url``, or None when the crawl never learned of it."""
    row = conn.execute(
        "SELECT min_depth, outcome FROM crawl_known_urls WHERE scan_id = ? AND url_normalized = ?",
        (scan_id, url),
    ).fetchone()
    if row is None:
        return None
    return KnownUrl(min_depth=int(row["min_depth"]), outcome=row["outcome"], new=False)


def set_outcome(
    conn: sqlite3.Connection,
    *,
    scan_id: int,
    url: str,
    outcome: Outcome,
    depth: int = 0,
) -> None:
    """Set what happened to ``url``. ``visited`` is final and is never replaced.

    Inserts the row when the address was not known yet (a redirect landing
    page, or a job queued before this table existed), at ``depth``.
    """
    conn.execute(
        """
        INSERT INTO crawl_known_urls (scan_id, url_normalized, linked, min_depth, outcome)
        VALUES (?, ?, 1, ?, ?)
        ON CONFLICT(scan_id, url_normalized) DO UPDATE SET outcome = excluded.outcome
        WHERE crawl_known_urls.outcome IS NULL OR crawl_known_urls.outcome != 'visited'
        """,
        (scan_id, url, depth, outcome),
    )


def finalize(
    conn: sqlite3.Connection,
    *,
    scan_id: int,
    max_depth: int,
    page_limit_reached: bool,
) -> UnvisitedCounts:
    """Store the unvisited counts on the scan and mark sitemap-only pages.

    Known pages within the depth limit that were never visited are counted
    against the page limit only when the scan actually reached it. Otherwise
    they were left by a scan that stopped early (it was interrupted), which is
    none of the three reasons, so they are not counted at all.
    """
    blocked = 0
    deep = 0
    waiting = 0
    rows = conn.execute(
        "SELECT url_normalized, min_depth, outcome FROM crawl_known_urls WHERE scan_id = ?",
        (scan_id,),
    ).fetchall()
    known = {str(r["url_normalized"]) for r in rows}
    for r in rows:
        if r["outcome"] == "blocked":
            blocked += 1
        elif r["outcome"] is None:
            # ``/docs/guides`` beside a known ``/docs/guides/`` is one page,
            # counted once under the spelling with the slash.
            twin = directory_twin(str(r["url_normalized"]))
            if twin is not None and twin in known:
                continue
            if int(r["min_depth"]) > max_depth:
                deep += 1
            else:
                waiting += 1
    counts = UnvisitedCounts(
        page_limit=waiting if page_limit_reached else 0,
        depth_limit=deep,
        blocked=blocked,
    )
    conn.execute(
        """
        UPDATE scans
           SET unvisited_page_limit = ?,
               unvisited_depth_limit = ?,
               unvisited_blocked = ?
         WHERE id = ?
        """,
        (counts.page_limit, counts.depth_limit, counts.blocked, scan_id),
    )
    conn.execute(
        """
        UPDATE pages
           SET found_only_in_sitemap = 1
         WHERE scan_id = ?
           AND url_normalized IN (
               SELECT url_normalized FROM crawl_known_urls
                WHERE scan_id = ? AND in_sitemap = 1 AND linked = 0
           )
        """,
        (scan_id, scan_id),
    )
    return counts


def page_exists(conn: sqlite3.Connection, *, scan_id: int, url: str) -> bool:
    """Whether a page row was recorded under exactly this requested address."""
    row = conn.execute(
        "SELECT 1 FROM pages WHERE scan_id = ? AND url_normalized = ?", (scan_id, url)
    ).fetchone()
    return row is not None


def page_landing_on(conn: sqlite3.Connection, *, scan_id: int, url: str) -> str | None:
    """The requested address of a page whose redirect landed on ``url``."""
    row = conn.execute(
        "SELECT url_normalized FROM pages WHERE scan_id = ? AND final_url = ? LIMIT 1",
        (scan_id, url),
    ).fetchone()
    return str(row["url_normalized"]) if row is not None else None


def page_for_address(conn: sqlite3.Connection, *, scan_id: int, url: str, raw: str) -> str | None:
    """A recorded page that is ``url``: requested as it, or redirected to it.

    ``raw`` is the address as the server returned it; a redirect's landing
    address is stored unnormalized, so both spellings are matched.
    """
    row = conn.execute(
        """
        SELECT url_normalized FROM pages
         WHERE scan_id = ? AND (url_normalized = ? OR final_url IN (?, ?))
         LIMIT 1
        """,
        (scan_id, url, url, raw),
    ).fetchone()
    return str(row["url_normalized"]) if row is not None else None


def pages_with_hash(conn: sqlite3.Connection, *, scan_id: int, html_hash: str) -> list[str]:
    """Requested addresses of the scan's pages with this content hash."""
    rows = conn.execute(
        "SELECT url_normalized FROM pages WHERE scan_id = ? AND html_hash = ? LIMIT 50",
        (scan_id, html_hash),
    ).fetchall()
    return [str(row["url_normalized"]) for row in rows]
