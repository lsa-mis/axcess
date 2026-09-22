"""SQLite connection management with WAL mode and FK enforcement."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


def connect(db_path: Path) -> sqlite3.Connection:
    """Open a tuned SQLite connection (WAL, FK on, row factory)."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(
        str(db_path),
        detect_types=sqlite3.PARSE_DECLTYPES,
        isolation_level=None,
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    # Read the database through the page cache of the OS rather than
    # copying each page. 256 MiB is a ceiling, not an allocation: SQLite
    # maps up to the file's size, and a database smaller than this is
    # mapped whole. The mapping is shared and read-only, so it does not
    # multiply with the number of open connections. Harmless where mmap is
    # unavailable, SQLite falls back to ordinary reads.
    conn.execute("PRAGMA mmap_size = 268435456")
    # Deliberately NOT set here, both tried and removed:
    #
    #   cache_size    A larger page cache measured no faster than the
    #                 default once mmap was on, and it is per connection.
    #                 The web layer opens one per request and read routes
    #                 run in a threadpool, so the ceiling multiplies.
    #   temp_store    MEMORY forces every sort and GROUP BY B-tree onto the
    #                 heap with no spill, again per connection. The covering
    #                 index added in migration 0029 removed the temporary
    #                 B-tree from the projection this was meant to help, so
    #                 it bought nothing and risked unbounded growth under
    #                 concurrent large-report requests.
    #
    # Measured on a 2,276-finding report, fresh connection per call, which
    # is how the web layer works: stock 17.4 ms, mmap only 16.5 ms, all
    # three 16.7 ms. Re-measure before adding either back.
    return conn


@contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """Explicit transaction block. Commits on success, rolls back on exception.

    Not re-entrant: SQLite rejects a ``BEGIN`` inside an open transaction.
    Use :func:`write_batch` for code that may run inside one.
    """
    conn.execute("BEGIN")
    try:
        yield conn
    except Exception:
        conn.execute("ROLLBACK")
        raise
    else:
        conn.execute("COMMIT")


@contextmanager
def write_batch(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """Group a run of writes into one commit, joining an open transaction.

    The connection is opened in autocommit mode, so a loop of inserts is a
    loop of transactions, each with its own WAL commit and fsync. One page
    of crawl evidence is hundreds of such writes. Wrapping the loop makes
    it one commit.

    Re-entrant, like :func:`audit.db.repo._status_transaction`: if a
    transaction is already open this yields without starting a nested one,
    and the outermost block owns the commit. That matters because some
    repository helpers open their own transaction and may be called from
    inside a batch.

    Only wrap a run of writes with no ``await`` in it. The crawl's workers
    share a single connection, so a transaction held across a suspension
    point would capture whatever another worker writes next.

    Batching trades partial durability for speed: where a failing row used
    to leave the rows around it committed, a failure that aborts the
    transaction now discards the batch. Per-row errors that the caller
    catches and logs are unaffected, and a page whose evidence is lost can
    be crawled again.
    """
    if conn.in_transaction:
        yield conn
        return
    conn.execute("BEGIN")
    try:
        yield conn
    except Exception:
        conn.execute("ROLLBACK")
        raise
    else:
        conn.execute("COMMIT")
