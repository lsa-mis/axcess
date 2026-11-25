"""One page's Alfa checks: at load, and in each page state a click opened.

Axe runs inline: the tab waits for it. Alfa's rules take about 1.5 s per
snapshot, so the tab only takes the snapshot and moves on, and the checks
finish in the background (:meth:`AlfaWorker.submit`). This module carries
those pending checks from the tab to the place the page is saved, and turns
them into what is saved, the same way Click-Through treats axe:

* the load check is the baseline: everything in it belongs to the page;
* a page state adds only occurrences not already seen at load or in an
  earlier state, each with the control that revealed it.

Every check that could not run keeps its reason, so the log and the report
can say why rather than show a gap.
"""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass, field

from audit.analyzer.alfa import AlfaError, AlfaFinding, AlfaResult
from audit.logging import get_logger

log = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class AlfaStateCheck:
    """Alfa's check of one page state a click opened."""

    task: asyncio.Task[AlfaResult]
    #: Accessible name of the control, as ``page_a11y_findings.revealed_by``.
    revealed_by: str
    #: Click-Through's key for that control (``RevealedViolation.state_key``).
    state_key: str = ""


@dataclass(slots=True)
class AlfaPageChecks:
    """Pending Alfa checks for one page, filled in by the tab."""

    load: asyncio.Task[AlfaResult] | None = None
    #: Why the load check could not start (the snapshot failed), if it did not.
    load_error: str | None = None
    states: list[AlfaStateCheck] = field(default_factory=list)
    #: Why a page state could not be snapshotted, one entry per state.
    state_errors: list[str] = field(default_factory=list)

    def tasks(self) -> list[asyncio.Task[AlfaResult]]:
        found = [check.task for check in self.states]
        return [self.load, *found] if self.load is not None else found

    def cancel(self) -> None:
        """Stop every pending check, for a page that will not be saved."""
        for task in self.tasks():
            task.cancel()


@dataclass(frozen=True, slots=True)
class RevealedAlfaFinding:
    """An Alfa occurrence first seen after a click."""

    finding: AlfaFinding
    revealed_by: str
    state_key: str


@dataclass(frozen=True, slots=True)
class AlfaPageOutcome:
    """What one page's Alfa checks found, ready to save."""

    #: The load check's result; ``None`` when it could not run.
    load: AlfaResult | None
    #: Why the load check did not run.
    load_error: str | None
    revealed: tuple[RevealedAlfaFinding, ...] = ()
    #: Page states Alfa checked, and ones it could not, with reasons.
    states_checked: int = 0
    state_errors: tuple[str, ...] = ()
    #: Failures and "can't tell" results among the revealed occurrences.
    revealed_failed: int = 0
    revealed_cant_tell: int = 0


async def settle(checks: AlfaPageChecks) -> AlfaPageOutcome:
    """Wait for every check on the page and keep what each state added."""
    tasks = checks.tasks()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)

    load: AlfaResult | None = None
    load_error = checks.load_error
    if checks.load is not None:
        load, load_error = _result(checks.load)

    state_errors = list(checks.state_errors)
    if load is None:
        # Without the load result nothing tells a revealed occurrence from
        # one the page always had; reporting them all as revealed would be
        # wrong, so the states are not used.
        if checks.states:
            state_errors.extend(
                "Alfa's check of the loaded page failed, so its page states could not "
                "be compared with it."
                for _ in checks.states
            )
        return AlfaPageOutcome(load=None, load_error=load_error, state_errors=tuple(state_errors))

    seen = {finding.target_hash for finding in load.findings}
    revealed: list[RevealedAlfaFinding] = []
    checked = 0
    for state in checks.states:
        result, error = _result(state.task)
        if result is None:
            state_errors.append(error or "Alfa did not return a result.")
            continue
        checked += 1
        for finding in result.findings:
            if finding.target_hash in seen:
                continue
            seen.add(finding.target_hash)
            revealed.append(RevealedAlfaFinding(finding, state.revealed_by, state.state_key))
    return AlfaPageOutcome(
        load=load,
        load_error=None,
        revealed=tuple(revealed),
        states_checked=checked,
        state_errors=tuple(state_errors),
        revealed_failed=sum(1 for item in revealed if item.finding.outcome == "failed"),
        revealed_cant_tell=sum(1 for item in revealed if item.finding.outcome == "cant_tell"),
    )


# A plain XPath to an element of the top document, as Alfa reports one:
# "/html[1]/body[1]/main[1]/button[2]". Paths through a shadow root or a
# frame are not plain steps and are left out.
_XPATH = re.compile(r"(?:/[A-Za-z][A-Za-z0-9_.:-]*\[\d+\])+")
# A text node's last step, as Alfa reports the target of a text rule such
# as sia-r69 (contrast): ".../p[1]/a[1]/text()[1]".
_TEXT_STEP = re.compile(r"/text\(\)\[\d+\]$")


def alfa_xpath(target_hint: str) -> str | None:
    """The XPath of the element to photograph for an Alfa finding, or ``None``.

    ``target_hint`` is the bounded JSON summary ``evidence.mjs`` writes
    (``{"type": "element", "path": "/html[1]/...", ...}``). A text target
    (``"type": "text"``) gives the element that holds the text: a text node
    has no box of its own to outline, and without this every contrast
    occurrence went without a screenshot (report 79: 29 of 29).
    """
    try:
        target = json.loads(target_hint)
    except (TypeError, ValueError):
        return None
    path = target.get("path") if isinstance(target, dict) else None
    if not isinstance(path, str) or len(path) > 2000:
        return None
    if target.get("type") == "text":
        path = _TEXT_STEP.sub("", path)
    if not _XPATH.fullmatch(path):
        return None
    return path


def _result(task: asyncio.Task[AlfaResult]) -> tuple[AlfaResult | None, str | None]:
    if task.cancelled():
        return None, "Alfa's check was stopped before it finished."
    exc = task.exception()
    if exc is None:
        return task.result(), None
    if isinstance(exc, AlfaError):
        return None, str(exc)
    # Never let an unexpected error pass for a clean result.
    log.warning("alfa.check_crashed", error_type=type(exc).__name__, error=str(exc)[:300])
    return None, f"Alfa failed unexpectedly ({type(exc).__name__}: {str(exc)[:200]})."
