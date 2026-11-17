"""
0043: add ``linked_files.thumbnail_small_hash`` where 0041 left it out.

0041 was edited after it had already run on some databases (2026-11-16):
its first version added only ``thumbnail_hash``, and the second column was
added to the file the same day. yoyo never runs a migration twice, so those
databases never got ``thumbnail_small_hash``, and every finished PDF check
then failed to save ("no such column"), leaving each file "not checked".
This adds the column only where it is missing, so a database that has it
(every one created from the committed 0041) is left untouched.

Rollback does nothing: the column belongs to 0041, whose rollback drops it.
A migration file that has run anywhere must never be edited again; add a
new one instead.
"""

from yoyo import step

__depends__ = {"0041_linked_file_thumbnails"}


def apply_step(conn):  # type: ignore[no-untyped-def]
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(linked_files)")
    columns = {row[1] for row in cursor.fetchall()}
    if "thumbnail_small_hash" not in columns:
        cursor.execute("ALTER TABLE linked_files ADD COLUMN thumbnail_small_hash TEXT")


def rollback_step(conn):  # type: ignore[no-untyped-def]
    pass


steps = [step(apply_step, rollback_step)]
