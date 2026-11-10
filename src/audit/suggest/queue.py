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
from audit.suggest.models import (
    CheckedCodeOption,
    CheckedDeveloperViewV2,
    ModelAnswerV2,
    SuggestionResult,
)
from audit.suggest.provider import (
    Provider,
    SuggestionError,
    build_prompt,
    choose_model,
    parse_answer,
)
from audit.suggest.verify import Outcome, Verifier, check_options

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
        self.busy = False

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
        # A canceled database row may still have a model request in flight.
        try:
            return await self._process_one()
        finally:
            self.busy = False

    async def _process_one(self) -> bool:

        def claim(conn: sqlite3.Connection) -> sqlite3.Row | None:
            if not repo.table_exists(conn):
                return None
            return repo.claim_next(conn)

        row = await self._db(claim)
        if not isinstance(row, sqlite3.Row):
            return False
        self.busy = True
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
        model = choice.model if uses_vision else self._text_model
        try:
            answer = _accept(raw, bundle)
        except SuggestionError as exc:
            if exc.code not in _RETRYABLE:
                raise
            # One second try that says what was wrong. The same prompt at
            # temperature 0 gives the same answer, so a plain repeat (or the
            # person pressing "Try again") cannot fix it; a changed prompt can.
            raw = await self._generate(
                bundle, model, with_image=uses_vision, correction=_correction(exc)
            )
            answer = _accept(raw, bundle)
        outcome: Outcome = "not_checked"
        outcomes = await check_options(
            self._verifier, bundle.check_rule_id, answer.developer.options
        )
        developer = CheckedDeveloperViewV2(
            change_sentence=answer.developer.change_sentence,
            options=[
                CheckedCodeOption(**option.model_dump(), check_outcome=checked)
                for option, checked in zip(answer.developer.options, outcomes, strict=True)
            ],
        )
        result = SuggestionResult(
            version=2,
            summary=answer.summary,
            developer=developer,
            editor=answer.editor,
            before_html=bundle.snippet,
            confidence=bundle.confidence,
            # A guess about behaviour always needs a person to check it,
            # whatever the model says.
            needs_manual_check=answer.needs_manual_check or bundle.confidence == "guess",
            manual_check_reason=answer.manual_check_reason,
            check_rule_id=bundle.check_rule_id,
            help_url=bundle.help_url,
        )
        return result, outcome, uses_vision

    async def _generate(
        self,
        bundle: context.EvidenceBundle,
        model: str,
        *,
        with_image: bool,
        correction: str | None = None,
    ) -> str:
        prompt = build_prompt(bundle, with_image=with_image, correction=correction)
        try:
            return await asyncio.wait_for(
                self._provider.generate(
                    prompt, model=model, image=bundle.image_bytes if with_image else None
                ),
                timeout=self._timeout,
            )
        except TimeoutError as exc:
            raise SuggestionError("timeout") from exc


_RETRYABLE = frozenset({"bad_answer", "no_change"})


def _accept(raw: str, bundle: context.EvidenceBundle) -> ModelAnswerV2:
    answer = parse_answer(raw)
    if not isinstance(answer, ModelAnswerV2):
        raise SuggestionError("bad_answer", "The model did not return two code options.")
    _reject_unchanged(answer, bundle.snippet)
    return answer


def _correction(exc: SuggestionError) -> str:
    if exc.code == "no_change":
        reason = "both options repeated the saved code without fixing the problem"
    elif exc.detail and "could run" in exc.detail:
        reason = (
            "it contained code that could run, such as a javascript: link, an inline "
            "event handler (on...=) or a script. Leave those parts out, even if the "
            "saved page code has them"
        )
    else:
        reason = "it was not in the expected JSON shape"
    return (
        f"Your previous answer was rejected because {reason}. "
        "Write a new answer that follows every rule above."
    )


def _same_code(a: str | None, b: str | None) -> bool:
    return " ".join((a or "").split()) == " ".join((b or "").split())


def _reject_unchanged(answer: ModelAnswerV2, before_html: str | None) -> None:
    """A copy of the saved element with no styles is not a fix; do not show it.

    Small models sometimes echo the input. Showing that as an option would
    claim a fix that changes nothing.
    """
    if before_html is None:
        return
    if all(
        _same_code(option.after_html, before_html) and not (option.css or "").strip()
        for option in answer.developer.options
    ):
        raise SuggestionError("no_change", "Both options repeated the saved code.")
