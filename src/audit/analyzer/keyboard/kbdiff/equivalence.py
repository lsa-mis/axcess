"""Stage 4: drop findings whose functionality a keyboard user can already reach.

WCAG 2.1.1 asks whether the *functionality* is operable from a keyboard, not
whether one particular element is. A card whose whole surface is clickable is
not a defect when the heading inside it is a real link doing the same thing.
Without this stage the output is technically accurate and practically unusable,
because it reports every such wrapper.

Two corrections to upstream's implementation, both located in their source:

* **Same page only.** They built one ``keyboardReachable`` list across the whole
  corpus and searched it without a page guard, so a finding on page A could be
  dismissed by a control on page B. Conformance is evaluated per page; a control
  on another page is not an alternative a user has.
* **Effect equality, not coverage similarity.** They compared V8 executed-function
  sets with a Jaccard threshold. Their own sweep showed why that is fragile:
  0.50, 0.80 and 0.95 all scored identically, and only exact equality reached the
  headline number, because two *different* handlers inside a framework share
  almost every function they run — the scheduler, the reconciler, the synthetic
  event system. Any tolerant threshold silently deletes real defects. We compare
  the observable effect payloads instead, which is what "the same functionality"
  actually means.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from audit.analyzer.keyboard.kbdiff.coverage import jaccard
from audit.analyzer.keyboard.kbdiff.model import ProbeOutcome, Verdict

# The signal used to decide "these two controls do the same thing". Upstream
# published one; we shipped another; nobody had compared them. Each takes the
# finding and a candidate keyboard-reachable control and answers whether the
# candidate delivers the finding's functionality.
Strategy = Callable[[ProbeOutcome, ProbeOutcome], bool]


def _channels_match(finding: ProbeOutcome, candidate: ProbeOutcome) -> bool:
    """Shared precondition: both formulations require the channel sets to agree."""
    target = finding.mouse.effect.changed
    return any(
        result.attempted and result.uncertainty is None and result.effect.changed == target
        for result in candidate.keyboard_by_key.values()
    )


def by_payload(finding: ProbeOutcome, candidate: ProbeOutcome) -> bool:
    """Ours: the candidate's keypress produced the identical observable effect.

    Measures the user-visible result, so two handlers that share framework
    internals but do different things are not confused. Brittle where a handler
    writes nondeterministic content.
    """
    return any(
        result.attempted
        and result.uncertainty is None
        and result.effect.same_as(finding.mouse.effect)
        for result in candidate.keyboard_by_key.values()
    )


def by_coverage_exact(finding: ProbeOutcome, candidate: ProbeOutcome) -> bool:
    """Upstream's: same channels, and the executed-function sets are EQUAL.

    Requires coverage to have been collected; with none, it abstains rather than
    dismissing on no evidence.
    """
    if not finding.mouse.coverage:
        return False
    return any(
        result.attempted
        and result.uncertainty is None
        and result.effect.changed == finding.mouse.effect.changed
        and result.coverage == finding.mouse.coverage
        for result in candidate.keyboard_by_key.values()
    )


def by_coverage_jaccard(threshold: float) -> Strategy:
    """Upstream's threshold sweep. Their own result was that any tolerance below
    1.0 silently deletes real defects, because unrelated handlers inside one
    framework share ~95% of the functions they execute."""

    if not 0 <= threshold <= 1:
        raise ValueError("coverage similarity threshold must be between 0 and 1")

    def strategy(finding: ProbeOutcome, candidate: ProbeOutcome) -> bool:
        if not finding.mouse.coverage:
            return False
        return any(
            result.attempted
            and result.uncertainty is None
            and result.effect.changed == finding.mouse.effect.changed
            and result.coverage
            and jaccard(result.coverage, finding.mouse.coverage) >= threshold
            for result in candidate.keyboard_by_key.values()
        )

    return strategy


def by_containment(finding: ProbeOutcome, candidate: ProbeOutcome) -> bool:
    """Abstain: outcome records do not contain actual DOM relationships.

    A shared channel set or nearby Tab position cannot establish containment.
    This reserved strategy must not dismiss findings until that evidence exists.
    It is not used in the reported experiment.
    """
    return False


@dataclass(frozen=True)
class Dismissal:
    """One finding dropped because a keyboard-reachable control already does it."""

    probe_id: str
    dismissed_by: str
    signature: str


def apply_equivalence(
    outcomes: list[ProbeOutcome], strategy: Strategy = by_payload
) -> tuple[list[ProbeOutcome], list[Dismissal]]:
    """Downgrade violations that a keyboard-reachable control on the same page reproduces.

    A dismissing control must be in the tab order, must have produced an effect
    from a keypress, and that effect must equal the finding's mouse effect
    exactly. Returns the rewritten outcomes and the dismissals, so the report can
    show what was dropped and why rather than the count silently shrinking.
    """
    # Only same-page, same-viewport controls can serve as an alternative.
    reachable: dict[tuple[str, str], list[ProbeOutcome]] = {}
    for outcome in outcomes:
        if not outcome.in_tab_order:
            continue
        for result in outcome.keyboard_by_key.values():
            if result.attempted and not result.effect.is_empty:
                reachable.setdefault((outcome.page, outcome.viewport), []).append(outcome)
                break

    rewritten: list[ProbeOutcome] = []
    dismissals: list[Dismissal] = []

    for outcome in outcomes:
        if outcome.verdict is not Verdict.VIOLATION:
            rewritten.append(outcome)
            continue

        match = _find_equivalent(
            outcome, reachable.get((outcome.page, outcome.viewport), []), strategy
        )
        if match is None:
            rewritten.append(outcome)
            continue

        dismissals.append(Dismissal(outcome.probe_id, match, _signature(outcome)))
        rewritten.append(
            ProbeOutcome(
                probe_id=outcome.probe_id,
                page=outcome.page,
                viewport=outcome.viewport,
                in_tab_order=outcome.in_tab_order,
                tab_index=outcome.tab_index,
                mouse=outcome.mouse,
                keyboard_by_key=outcome.keyboard_by_key,
                verdict=Verdict.NO_LEAD,
                uncertainty=None,
                equivalent_control=match,
                reason=(
                    f"same functionality is reachable from {match}, "
                    "which is in the tab order on this page"
                ),
            )
        )

    return rewritten, dismissals


def _find_equivalent(
    finding: ProbeOutcome, candidates: list[ProbeOutcome], strategy: Strategy
) -> str | None:
    """The id of a keyboard-reachable control that delivers the finding's function."""
    for candidate in candidates:
        if candidate.probe_id == finding.probe_id:
            continue
        # A dismissing control needs evidence we can stand behind: a completed,
        # uncertainty-free trial that actually did something.
        if not any(
            r.attempted and r.uncertainty is None and not r.effect.is_empty
            for r in candidate.keyboard_by_key.values()
        ):
            continue
        if strategy(finding, candidate):
            return candidate.probe_id
    return None


def _signature(outcome: ProbeOutcome) -> str:
    return ";".join(sorted(outcome.mouse.effect.changed))
