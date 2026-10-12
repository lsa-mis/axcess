"""SQL for ``fix_suggestions``. Every read that serves a browser is scan-scoped."""

from __future__ import annotations

import json
import sqlite3
from typing import Any, cast

from audit.suggest.context import stored_help_url
from audit.suggest.models import (
    Audience,
    ErrorCode,
    Feedback,
    OccurrenceKind,
    SuggestionRecord,
    SuggestionResult,
)

# Old versions kept per occurrence; "Suggest again" beyond this drops the
# oldest finished one so a curious reviewer cannot grow the table forever.
MAX_VERSIONS_PER_OCCURRENCE = 10

_COLUMNS = (
    "id, scan_id, page_id, occurrence_kind, occurrence_id, status, audience_default, "
    "text_model, vision_model, prompt_version, result_json, check_outcome, error_code, "
    "error_detail, feedback, created_at, started_at, finished_at"
)


def table_exists(conn: sqlite3.Connection) -> bool:
    return (
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'fix_suggestions'"
        ).fetchone()
        is not None
    )


def insert(
    conn: sqlite3.Connection,
    *,
    scan_id: int,
    page_id: int,
    occurrence_kind: OccurrenceKind,
    occurrence_id: int,
    audience_default: Audience,
    text_model: str,
    vision_model: str | None,
    prompt_version: str,
) -> int:
    cur = conn.execute(
        """
        INSERT INTO fix_suggestions (
            scan_id, page_id, occurrence_kind, occurrence_id, audience_default,
            text_model, vision_model, prompt_version
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            scan_id,
            page_id,
            occurrence_kind,
            occurrence_id,
            audience_default,
            text_model,
            vision_model,
            prompt_version,
        ),
    )
    new_id = int(cur.lastrowid or 0)
    _prune(conn, scan_id=scan_id, occurrence_kind=occurrence_kind, occurrence_id=occurrence_id)
    return new_id


def _prune(
    conn: sqlite3.Connection, *, scan_id: int, occurrence_kind: str, occurrence_id: int
) -> None:
    conn.execute(
        """
        DELETE FROM fix_suggestions
         WHERE id IN (
            SELECT id FROM fix_suggestions
             WHERE scan_id = ? AND occurrence_kind = ? AND occurrence_id = ?
               AND status IN ('ready', 'failed', 'cancelled')
             ORDER BY id DESC
             LIMIT -1 OFFSET ?
         )
        """,
        (scan_id, occurrence_kind, occurrence_id, MAX_VERSIONS_PER_OCCURRENCE - 1),
    )


def get(conn: sqlite3.Connection, *, scan_id: int, suggestion_id: int) -> sqlite3.Row | None:
    return cast(
        "sqlite3.Row | None",
        conn.execute(
            f"SELECT {_COLUMNS} FROM fix_suggestions WHERE id = ? AND scan_id = ?",  # noqa: S608 - fixed column list
            (suggestion_id, scan_id),
        ).fetchone(),
    )


def get_any(conn: sqlite3.Connection, suggestion_id: int) -> sqlite3.Row | None:
    """Worker-only lookup by id; never used to answer a browser request."""
    return cast(
        "sqlite3.Row | None",
        conn.execute(
            f"SELECT {_COLUMNS} FROM fix_suggestions WHERE id = ?",  # noqa: S608 - fixed column list
            (suggestion_id,),
        ).fetchone(),
    )


def latest_for_occurrence(
    conn: sqlite3.Connection,
    *,
    scan_id: int,
    occurrence_kind: OccurrenceKind,
    occurrence_id: int,
) -> sqlite3.Row | None:
    return cast(
        "sqlite3.Row | None",
        conn.execute(
            f"""
            SELECT {_COLUMNS} FROM fix_suggestions
             WHERE scan_id = ? AND occurrence_kind = ? AND occurrence_id = ?
             ORDER BY id DESC LIMIT 1
            """,  # noqa: S608 - fixed column list
            (scan_id, occurrence_kind, occurrence_id),
        ).fetchone(),
    )


def queue_length(conn: sqlite3.Connection) -> int:
    row = conn.execute(
        "SELECT COUNT(*) FROM fix_suggestions WHERE status IN ('queued', 'running')"
    ).fetchone()
    return int(row[0])


def queue_position(conn: sqlite3.Connection, suggestion_id: int) -> int:
    """How many requests are ahead of this queued one (0 = next)."""
    row = conn.execute(
        "SELECT COUNT(*) FROM fix_suggestions WHERE id < ? AND status IN ('queued', 'running')",
        (suggestion_id,),
    ).fetchone()
    return int(row[0])


def claim_next(conn: sqlite3.Connection) -> sqlite3.Row | None:
    """Move the oldest queued row to running and return it, atomically."""
    return cast(
        "sqlite3.Row | None",
        conn.execute(
            f"""
            UPDATE fix_suggestions
               SET status = 'running',
                   started_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
             WHERE id = (
                SELECT id FROM fix_suggestions WHERE status = 'queued' ORDER BY id LIMIT 1
             )
               AND status = 'queued'
            RETURNING {_COLUMNS}
            """  # noqa: S608 - fixed column list
        ).fetchone(),
    )


def finish_ready(
    conn: sqlite3.Connection,
    suggestion_id: int,
    *,
    result: SuggestionResult,
    check_outcome: str,
    used_vision: bool,
) -> bool:
    # ``vision_model`` keeps the model's name only when it was the one that
    # answered, so "Written by" names the model that actually wrote it.
    cur = conn.execute(
        """
        UPDATE fix_suggestions
           SET status = 'ready', result_json = ?, check_outcome = ?,
               vision_model = CASE WHEN ? THEN vision_model ELSE NULL END,
               finished_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
         WHERE id = ? AND status = 'running'
        """,
        (result.model_dump_json(), check_outcome, used_vision, suggestion_id),
    )
    return cur.rowcount == 1


def finish_failed(
    conn: sqlite3.Connection,
    suggestion_id: int,
    *,
    error_code: ErrorCode,
    error_detail: str | None = None,
) -> bool:
    cur = conn.execute(
        """
        UPDATE fix_suggestions
           SET status = 'failed', error_code = ?, error_detail = ?,
               finished_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
         WHERE id = ? AND status = 'running'
        """,
        (error_code, error_detail, suggestion_id),
    )
    return cur.rowcount == 1


def cancel(conn: sqlite3.Connection, *, scan_id: int, suggestion_id: int) -> bool:
    cur = conn.execute(
        """
        UPDATE fix_suggestions
           SET status = 'cancelled', finished_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
         WHERE id = ? AND scan_id = ? AND status IN ('queued', 'running')
        """,
        (suggestion_id, scan_id),
    )
    return cur.rowcount == 1


def is_cancelled(conn: sqlite3.Connection, suggestion_id: int) -> bool:
    row = conn.execute(
        "SELECT status FROM fix_suggestions WHERE id = ?", (suggestion_id,)
    ).fetchone()
    return row is None or row["status"] == "cancelled"


def set_feedback(
    conn: sqlite3.Connection, *, scan_id: int, suggestion_id: int, feedback: Feedback | None
) -> bool:
    cur = conn.execute(
        "UPDATE fix_suggestions SET feedback = ? WHERE id = ? AND scan_id = ? AND status = 'ready'",
        (feedback, suggestion_id, scan_id),
    )
    return cur.rowcount == 1


def recover_after_restart(conn: sqlite3.Connection) -> int:
    """A row left running had its worker die with the process; fail it.

    Queued rows are kept: the new worker picks them up, so a person who
    asked before a restart still gets their suggestion.
    """
    cur = conn.execute(
        """
        UPDATE fix_suggestions
           SET status = 'failed', error_code = 'restarted',
               finished_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
         WHERE status = 'running'
        """
    )
    return int(cur.rowcount)


def require(conn: sqlite3.Connection, *, scan_id: int, suggestion_id: int) -> sqlite3.Row:
    row = get(conn, scan_id=scan_id, suggestion_id=suggestion_id)
    if row is None:
        raise LookupError(suggestion_id)
    return row


def to_record(conn: sqlite3.Connection, row: sqlite3.Row) -> SuggestionRecord:
    result: SuggestionResult | None = None
    if row["result_json"]:
        answer_data = json.loads(row["result_json"])
        answer_data["help_url"] = (
            stored_help_url(
                conn, scan_id=int(row["scan_id"]), occurrence_id=int(row["occurrence_id"])
            )
            if row["occurrence_kind"] == "a11y"
            else None
        )
        result = SuggestionResult.model_validate(answer_data)
    position = queue_position(conn, int(row["id"])) if row["status"] == "queued" else None
    data: dict[str, Any] = {
        "id": int(row["id"]),
        "scan_id": int(row["scan_id"]),
        "page_id": int(row["page_id"]),
        "occurrence_kind": row["occurrence_kind"],
        "occurrence_id": int(row["occurrence_id"]),
        "status": row["status"],
        "audience_default": row["audience_default"],
        "text_model": row["text_model"],
        "vision_model": row["vision_model"],
        "result": result,
        "check_outcome": row["check_outcome"],
        "error_code": row["error_code"],
        "error_detail": row["error_detail"],
        "feedback": row["feedback"],
        "created_at": row["created_at"],
        "finished_at": row["finished_at"],
        "queue_position": position,
    }
    return SuggestionRecord.model_validate(data)
