"""One-at-a-time background worker for queued suggestions.

The person asks, gets an answer at once ("queued"), and can leave the page.
This worker picks the oldest queued row, asks the model, and saves the
result. Ollama runs one request at a time on most computers anyway, so a
single worker keeps the order fair and the waiting message honest.

All database work runs in a thread with its own connection, so the event
loop that serves the browser never waits on SQLite.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import sqlite3
from collections.abc import Callable
from pathlib import Path

from audit.db.schema import connect
from audit.suggest import context, repo
from audit.suggest.models import SuggestionResult
from audit.suggest.provider import (
    Provider,
    SuggestionError,
    build_prompt,
    choose_model,
    parse_answer,
)
from audit.suggest.verify import Outcome, Verifier

log = logging.getLogger(__name__)


class SuggestionWorker:
    def __init__(
        self,
        *,
        db_path: Path,
        blob_dir: Path,
        provider: Provider,
        verifier: Verifier,
        text_model: str,
        vision_model: str,
        timeout_s: float,
        connect_fn: Callable[[Path], sqlite3.Connection] = connect,
    ) -> None:
        self._db_path = db_path
        self._blob_dir = blob_dir
        self._provider = provider
        self._verifier = verifier
        self._text_model = text_model
        self._vision_model = vision_model
        self._timeout = timeout_s
        self._connect = connect_fn
        self._wake = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    def wake(self) -> None:
        self._wake.set()

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._task
        self._task = None

    def _with_conn(self, fn: Callable[[sqlite3.Connection], object]) -> object:
        conn = self._connect(self._db_path)
        try:
            return fn(conn)
        finally:
            conn.close()

    async def _db(self, fn: Callable[[sqlite3.Connection], object]) -> object:
        return await asyncio.to_thread(self._with_conn, fn)

    async def _run(self) -> None:
        try:
            await self._db(lambda c: repo.recover_after_restart(c) if repo.table_exists(c) else 0)
        except sqlite3.Error:
            log.warning("suggest.recover_failed")
        while True:
            try:
                handled = await self.process_one()
            except asyncio.CancelledError:
                raise
            except Exception:  # the worker must outlive one bad row
                log.exception("suggest.worker_error")
                handled = False
            if not handled:
                self._wake.clear()
                with contextlib.suppress(TimeoutError):
                    # Polls as a fallback in case a wake was missed.
                    await asyncio.wait_for(self._wake.wait(), timeout=30)

    async def process_one(self) -> bool:
        """Handle the oldest queued suggestion. False when none was waiting."""

        def claim(conn: sqlite3.Connection) -> sqlite3.Row | None:
            if not repo.table_exists(conn):
                return None
            return repo.claim_next(conn)

        row = await self._db(claim)
        if not isinstance(row, sqlite3.Row):
            return False
        sid = int(row["id"])
        try:
            result, outcome, used_vision = await self._suggest(row)
        except SuggestionError as exc:
            code, detail = exc.code, exc.detail
            await self._db(
                lambda c: repo.finish_failed(c, sid, error_code=code, error_detail=detail)
            )
            return True
        except context.OccurrenceNotFoundError:
            await self._db(lambda c: repo.finish_failed(c, sid, error_code="occurrence_gone"))
            return True
        except context.NothingToFixError:
            await self._db(lambda c: repo.finish_failed(c, sid, error_code="occurrence_gone"))
            return True
        except Exception:
            log.exception("suggest.unexpected")
            await self._db(lambda c: repo.finish_failed(c, sid, error_code="internal"))
            return True
        # finish_ready only updates a row that is still running, so a
        # cancel that arrived while the model was working wins.
        await self._db(
            lambda c: repo.finish_ready(
                c, sid, result=result, check_outcome=outcome, used_vision=used_vision
            )
        )
        return True

    async def _suggest(self, row: sqlite3.Row) -> tuple[SuggestionResult, Outcome, bool]:
        scan_id = int(row["scan_id"])
        kind = row["occurrence_kind"]
        oid = int(row["occurrence_id"])

        def build(conn: sqlite3.Connection) -> context.EvidenceBundle:
            return context.build(
                conn, self._blob_dir, scan_id=scan_id, occurrence_kind=kind, occurrence_id=oid
            )

        bundle = await self._db(build)
        if not isinstance(bundle, context.EvidenceBundle):
            raise SuggestionError("internal")
        choice = choose_model(bundle, text_model=self._text_model, vision_model=self._vision_model)
        uses_vision = choice.uses_vision
        try:
            raw = await self._generate(bundle, choice.model, with_image=uses_vision)
        except SuggestionError as exc:
            if not (uses_vision and exc.code == "model_missing"):
                raise
            # The picture model is not installed: answer from the text and
            # the image's stored facts rather than not at all.
            uses_vision = False
            raw = await self._generate(bundle, self._text_model, with_image=False)
        answer = parse_answer(raw)
        outcome: Outcome = "not_checked"
        if bundle.check_rule_id and answer.developer.after_html:
            outcome = await self._verifier.check(
                bundle.check_rule_id, answer.developer.after_html, answer.developer.css
            )
        result = SuggestionResult(
            summary=answer.summary,
            developer=answer.developer,
            editor=answer.editor,
            before_html=bundle.snippet,
            confidence=bundle.confidence,
            # A guess about behaviour always needs a person to check it,
            # whatever the model says.
            needs_manual_check=answer.needs_manual_check or bundle.confidence == "guess",
            manual_check_reason=answer.manual_check_reason,
            check_rule_id=bundle.check_rule_id,
        )
        return result, outcome, uses_vision

    async def _generate(
        self, bundle: context.EvidenceBundle, model: str, *, with_image: bool
    ) -> str:
        prompt = build_prompt(bundle, with_image=with_image)
        try:
            return await asyncio.wait_for(
                self._provider.generate(
                    prompt, model=model, image=bundle.image_bytes if with_image else None
                ),
                timeout=self._timeout,
            )
        except TimeoutError as exc:
            raise SuggestionError("timeout") from exc
