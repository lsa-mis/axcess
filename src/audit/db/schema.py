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
    """Explicit transaction block. Commits on success, rolls back on exception."""
    conn.execute("BEGIN")
    try:
        yield conn
    except Exception:
        conn.execute("ROLLBACK")
        raise
    else:
        conn.execute("COMMIT")
