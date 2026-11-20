"""
0044: remove what the withdrawn veraPDF migration (0042) left behind.

0042 (``0042_linked_file_pdfua``, 2026-11-17) stored veraPDF's PDF/UA results:
``linked_files.pdfua_outcome``, ``linked_file_pdfua_failures`` and
``linked_file_checkers``. The developer then removed veraPDF from Axcess the
same day (it found no reader problem the pypdf checks missed on the labelled
real files) and its commits were taken out of history, 0042 with them. A
database that ran 0042 keeps those tables and that column; this drops them
where they exist and does nothing anywhere else.

Rollback does nothing: the results belonged to a feature that no longer
exists, and nothing reads them.
"""

from yoyo import step

__depends__ = {"0043_repair_linked_file_thumbnail_small"}


def apply_step(conn):  # type: ignore[no-untyped-def]
    cursor = conn.cursor()
    cursor.execute("DROP TABLE IF EXISTS linked_file_checkers")
    cursor.execute("DROP INDEX IF EXISTS idx_linked_file_pdfua_failures_scan")
    cursor.execute("DROP TABLE IF EXISTS linked_file_pdfua_failures")
    cursor.execute("PRAGMA table_info(linked_files)")
    if "pdfua_outcome" in {row[1] for row in cursor.fetchall()}:
        cursor.execute("ALTER TABLE linked_files DROP COLUMN pdfua_outcome")


def rollback_step(conn):  # type: ignore[no-untyped-def]
    pass


steps = [step(apply_step, rollback_step)]
