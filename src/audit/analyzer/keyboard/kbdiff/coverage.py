"""V8 precise coverage: which functions actually ran.

Collected only so upstream's Stage-4 formulation can be evaluated against ours
on identical measurements. Their filter asks whether two elements *executed the
same code*; ours asks whether they *produced the same observable effect*. Those
are different questions and, until now, nobody had scored them against each
other — upstream used coverage because it was already being collected for
another arm, not because it was shown to be the better signal.

The baseline subtraction matters and upstream flagged it: clicking a
handler-free target first and removing those functions from every later set
stripped 28 shared functions per click on their React page. Without it, two
handlers inside one framework look nearly identical because both run the
scheduler, the reconciler and the synthetic event system.
"""

from __future__ import annotations

import contextlib
from typing import Any

from audit.logging import get_logger

log = get_logger(__name__)


async def start(cdp: Any) -> None:
    """Arm precise coverage. Safe to call more than once."""
    with contextlib.suppress(Exception):
        await cdp.send("Profiler.enable")
        await cdp.send("Profiler.startPreciseCoverage", {"callCount": False, "detailed": True})


async def take(cdp: Any) -> frozenset[str]:
    """Executed-function identities since the previous call.

    A function counts as executed when any of its ranges has a non-zero count.
    Identity is ``url#name@offset`` — the offset keeps two same-named functions
    in one file distinct, which matters because minified bundles reuse names
    heavily.
    """
    try:
        result = await cdp.send("Profiler.takePreciseCoverage")
    except Exception as exc:
        log.debug("kbdiff.coverage_take_failed", error=str(exc)[:120])
        return frozenset()

    executed: set[str] = set()
    for script in result.get("result", []):
        url = script.get("url", "")
        for func in script.get("functions", []):
            ranges = func.get("ranges", [])
            if any(r.get("count", 0) > 0 for r in ranges):
                name = func.get("functionName") or "?"
                start_offset = ranges[0].get("startOffset", 0) if ranges else 0
                executed.add(f"{url}#{name}@{start_offset}")
    return frozenset(executed)


def jaccard(left: frozenset[str], right: frozenset[str]) -> float:
    """Set similarity in [0, 1]. 1.0 means identical, 0.0 means disjoint.

    Kept so the threshold sweep upstream published can be reproduced. Their
    result was that 0.50, 0.80 and 0.95 all score identically and only exact
    equality reaches the headline, because everything falling off the cliff
    between 0.95 and 1.0 is framework code shared by unrelated handlers.
    """
    if not left and not right:
        return 1.0
    union = left | right
    if not union:
        return 1.0
    return len(left & right) / len(union)


def subtract_baseline(executed: frozenset[str], baseline: frozenset[str]) -> frozenset[str]:
    """Remove functions that run on any click, handler or not.

    Upstream's recommendation, and worth taking: it is what separates "these two
    controls do the same thing" from "these two controls are both React".
    """
    return frozenset(executed - baseline)
