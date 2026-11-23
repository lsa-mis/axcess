"""One log line for every check that did not run, with the reason.

A check that silently did nothing looks exactly like a check that found
nothing. Every place a scan skips a check, or a check fails, logs it here as
one event, ``check.not_run``, so the log (``data/logs/axcess.log``) answers
"why is this check missing from my report?" with a reason a person can read:

    check.not_run check=alfa scope=page url=https://example.edu/
        reason="Alfa took longer than 75 seconds to check this page state."

Fields:

* ``check``: the check's key, as in the report (``axe``, ``alfa``,
  ``keyboard``, ``interaction``, ``ocr``, ...).
* ``scope``: ``scan`` (the whole scan), ``page``, or ``page_state`` (one
  state a click opened).
* ``reason``: why, in words.
* ``url``: the page, left out of sign-in scans (``protected=True``), where an
  address can carry session detail. The reason is cut before any error
  output copied from another program, for the same reason.

``scan``-scope lines for checks the person chose not to run are ``info``;
everything else is a ``warning``, because the check was wanted.
"""

from __future__ import annotations

from typing import Any, Literal

from audit.logging import get_logger

log = get_logger("audit.checks")

Scope = Literal["scan", "page", "page_state"]

#: Marks where a reason starts quoting another program's error output.
_RAW_OUTPUT_MARKERS = (" Error output:", " Last error output:")


def not_run(
    check: str,
    *,
    reason: str,
    scope: Scope,
    url: str | None = None,
    protected: bool = False,
    chosen: bool = False,
    **extra: Any,
) -> None:
    """Log that ``check`` did not run for ``scope``, and why.

    ``chosen`` marks a check the person turned off: expected, so ``info``.
    """
    fields: dict[str, Any] = {"check": check, "scope": scope}
    if protected:
        fields["protected_context"] = True
        reason = _without_raw_output(reason)
    elif url is not None:
        fields["url"] = url
    fields["reason"] = " ".join(str(reason).split())[:1000]
    fields.update(extra)
    if chosen:
        log.info("check.not_run", **fields)
    else:
        log.warning("check.not_run", **fields)


def _without_raw_output(reason: str) -> str:
    for marker in _RAW_OUTPUT_MARKERS:
        index = reason.find(marker)
        if index >= 0:
            reason = reason[:index]
    return reason
