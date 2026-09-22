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
    # Page cache, expressed in KiB rather than pages so the size does not
    # move when the page size does. The web layer opens a connection per
    # request and a crawl holds one for its whole run; 64 MiB keeps a
    # report's working set resident instead of re-reading it from the OS
    # on every projection.
    conn.execute("PRAGMA cache_size = -65536")
    # Read the database through the page cache of the OS rather than
    # copying each page. 256 MiB is a ceiling, not an allocation: SQLite
    # maps up to the file's size, and a database smaller than this is
    # mapped whole. Harmless where mmap is unavailable, SQLite falls back
    # to ordinary reads.
    conn.execute("PRAGMA mmap_size = 268435456")
    # Sorting and the temporary B-trees behind GROUP BY belong in memory.
    # The alternative is a temp file per grouped query.
    conn.execute("PRAGMA temp_store = MEMORY")
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
