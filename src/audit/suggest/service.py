"""Request-side rules for AI fix suggestions; no FastAPI or model imports.

Route handlers call these and turn :class:`SuggestionRefusedError` into an HTTP
status. Every check that keeps a report's data inside its own report lives
here, so it can be tested without a server.
"""

from __future__ import annotations

import sqlite3

from audit.config import Settings
from audit.suggest import context, repo
from audit.suggest.models import (
    AvailabilityReason,
    FeedbackUpdate,
    OccurrenceKind,
    SuggestionAvailability,
    SuggestionCreate,
    SuggestionRecord,
)
from audit.suggest.provider import Provider, SuggestionError, prompt_version


class SuggestionRefusedError(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


def _require_feature(conn: sqlite3.Connection, settings: Settings) -> None:
    if not settings.suggestions_enabled:
        raise SuggestionRefusedError(
            403, "AI suggestions are turned off. An administrator can turn them on."
        )
    if not repo.table_exists(conn):
        raise SuggestionRefusedError(
            503, "The database needs an update before AI suggestions work. Run `make migrate`."
        )


def _require_report(conn: sqlite3.Connection, scan_id: int, *, is_protected: bool) -> None:
    row = conn.execute("SELECT status FROM scans WHERE id = ?", (scan_id,)).fetchone()
    if row is None:
        raise SuggestionRefusedError(404, "Report not found.")
    if is_protected:
        raise SuggestionRefusedError(
            403,
            "AI suggestions are not available for signed-in (protected) reports. "
            "Their evidence stays encrypted.",
        )
    if row["status"] != "completed":
        raise SuggestionRefusedError(
            409, "AI suggestions are available once the scan has finished."
        )


def create(
    conn: sqlite3.Connection,
    settings: Settings,
    *,
    scan_id: int,
    body: SuggestionCreate,
    is_protected: bool,
) -> SuggestionRecord:
    _require_feature(conn, settings)
    _require_report(conn, scan_id, is_protected=is_protected)
    try:
        page_id, audience = context.locate(
            conn,
            scan_id=scan_id,
            occurrence_kind=body.occurrence_kind,
            occurrence_id=body.occurrence_id,
        )
    except context.OccurrenceNotFoundError as exc:
        raise SuggestionRefusedError(404, "That occurrence is not in this report.") from exc
    except context.NothingToFixError as exc:
        raise SuggestionRefusedError(
            409, "This is an old record kept for history. There is nothing to fix."
        ) from exc
    if repo.queue_length(conn) >= settings.suggestion_queue_max:
        raise SuggestionRefusedError(
            429, "Too many AI suggestions are waiting. Try again when some have finished."
        )
    # A second click while one is still waiting returns the waiting one
    # rather than queueing a duplicate.
    latest = repo.latest_for_occurrence(
        conn,
        scan_id=scan_id,
        occurrence_kind=body.occurrence_kind,
        occurrence_id=body.occurrence_id,
    )
    if latest is not None and latest["status"] in ("queued", "running"):
        return repo.to_record(conn, latest)
    sid = repo.insert(
        conn,
        scan_id=scan_id,
        page_id=page_id,
        occurrence_kind=body.occurrence_kind,
        occurrence_id=body.occurrence_id,
        audience_default=audience,
        text_model=settings.suggestion_text_model,
        vision_model=settings.suggestion_vision_model,
        prompt_version=prompt_version(),
    )
    return repo.to_record(conn, repo.require(conn, scan_id=scan_id, suggestion_id=sid))


def _readable(conn: sqlite3.Connection, scan_id: int, *, is_protected: bool) -> None:
    # Reading a saved suggestion does not need the feature on: turning it
    # off should not hide what people already read. It does need the table.
    if not repo.table_exists(conn):
        raise SuggestionRefusedError(404, "No AI suggestion yet.")
    if is_protected:
        raise SuggestionRefusedError(403, "AI suggestions are not available for protected reports.")
    if conn.execute("SELECT 1 FROM scans WHERE id = ?", (scan_id,)).fetchone() is None:
        raise SuggestionRefusedError(404, "Report not found.")


def get(
    conn: sqlite3.Connection, *, scan_id: int, suggestion_id: int, is_protected: bool
) -> SuggestionRecord:
    _readable(conn, scan_id, is_protected=is_protected)
    row = repo.get(conn, scan_id=scan_id, suggestion_id=suggestion_id)
    if row is None:
        raise SuggestionRefusedError(404, "AI suggestion not found.")
    return repo.to_record(conn, row)


def latest(
    conn: sqlite3.Connection,
    *,
    scan_id: int,
    occurrence_kind: OccurrenceKind,
    occurrence_id: int,
    is_protected: bool,
) -> SuggestionRecord | None:
    _readable(conn, scan_id, is_protected=is_protected)
    row = repo.latest_for_occurrence(
        conn, scan_id=scan_id, occurrence_kind=occurrence_kind, occurrence_id=occurrence_id
    )
    return repo.to_record(conn, row) if row is not None else None


def cancel(
    conn: sqlite3.Connection, *, scan_id: int, suggestion_id: int, is_protected: bool
) -> SuggestionRecord:
    _readable(conn, scan_id, is_protected=is_protected)
    if repo.get(conn, scan_id=scan_id, suggestion_id=suggestion_id) is None:
        raise SuggestionRefusedError(404, "AI suggestion not found.")
    repo.cancel(conn, scan_id=scan_id, suggestion_id=suggestion_id)
    return repo.to_record(conn, repo.require(conn, scan_id=scan_id, suggestion_id=suggestion_id))


def set_feedback(
    conn: sqlite3.Connection,
    *,
    scan_id: int,
    suggestion_id: int,
    body: FeedbackUpdate,
    is_protected: bool,
) -> SuggestionRecord:
    _readable(conn, scan_id, is_protected=is_protected)
    if not repo.set_feedback(
        conn, scan_id=scan_id, suggestion_id=suggestion_id, feedback=body.feedback
    ):
        raise SuggestionRefusedError(
            404, "No finished AI suggestion with that number in this report."
        )
    return repo.to_record(conn, repo.require(conn, scan_id=scan_id, suggestion_id=suggestion_id))


async def availability(
    conn: sqlite3.Connection,
    settings: Settings,
    provider: Provider | None,
    *,
    scan_running: bool,
) -> SuggestionAvailability:
    def result(
        reason: AvailabilityReason, *, queued: int = 0, missing: list[str] | None = None
    ) -> SuggestionAvailability:
        return SuggestionAvailability(
            enabled=reason == "ready",
            reason=reason,
            text_model=settings.suggestion_text_model,
            vision_model=settings.suggestion_vision_model,
            missing_models=missing or [],
            queue_length=queued,
            scan_running=scan_running,
        )

    if not settings.suggestions_enabled:
        return result("turned_off")
    if not repo.table_exists(conn):
        return result("database_update_needed")
    queued = repo.queue_length(conn)
    if provider is None:
        return result("model_unavailable", queued=queued)
    try:
        installed = await provider.installed_models()
    except SuggestionError:
        return result("model_unavailable", queued=queued)
    missing = [
        m
        for m in (settings.suggestion_text_model, settings.suggestion_vision_model)
        if m not in installed and f"{m}:latest" not in installed
    ]
    # Only the text model is required: without the vision model, image
    # problems still get an answer from the text model and the image's facts.
    if settings.suggestion_text_model in missing:
        return result("model_missing", queued=queued, missing=missing)
    return result("ready", queued=queued, missing=missing)
