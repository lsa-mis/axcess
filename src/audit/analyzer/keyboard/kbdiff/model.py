"""Data model for the keyboard-differential experiment (SC 2.1.1).

Experimental. Nothing in this subpackage is imported by the scan
orchestrator; it exists to be scored by ``experiments/tabbing/runner``.

The one design rule that shapes every type here: **an inconclusive probe is
not a negative.** Upstream's harness folded "we could not reach it inside the
Tab cap" into "not keyboard reachable", which silently converts a measurement
failure into a defect. :class:`Verdict` therefore has three values, not two,
and :class:`Uncertainty` records *why* so the report can break the number out
instead of hiding it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class Verdict(StrEnum):
    """What we concluded about one probe, in one viewport.

    ``UNKNOWN`` is a first-class outcome, never coerced to a negative: it means
    the instrument did not get a clean read, which is a different statement from
    "the keyboard works here".

    ``NO_LEAD`` is deliberately not called ``OK``. A passing automated trial does
    not establish that an element is accessible — only that this detector, with
    these keys and these channels, found nothing. Naming it ``OK`` invites the
    report to claim conformance, which is exactly what we promised not to do.
    """

    VIOLATION = "violation"  # mouse did something the keyboard could not reproduce
    NO_LEAD = "no_lead"  # this detector found nothing; NOT a claim of accessibility
    UNKNOWN = "unknown"  # we could not measure it; NOT a pass and NOT a fail


class Uncertainty(StrEnum):
    """Why a probe scored :attr:`Verdict.UNKNOWN`.

    Each value is a distinct instrument failure, kept separate because they
    have different fixes: a cap is a budget problem, an unresolved target is a
    selector problem, and an unsupported construct is a scope problem.
    """

    TAB_CAP = "tab_cap_exhausted"  # ran out of Tab presses before finding it
    UNRESOLVED = "target_unresolved"  # probe id matched no node in the pierced tree
    NOT_RENDERED = "not_rendered"  # no box: display:none, zero-size, off-viewport
    UNSUPPORTED = "unsupported"  # construct we knowingly do not handle
    INSTRUMENT_ERROR = "instrument_error"  # a channel raised; read is untrustworthy


# Observation channels. `dom` and `geometry` are digests (cheap, order-stable);
# the rest carry payloads, because "something changed" and "the *same* thing
# changed" are different questions and upstream only ever asked the first.
CHANNELS: tuple[str, ...] = (
    "dom",
    "geometry",
    "storage",
    "net",
    "console",
    "canvas",
    "nav",
)


@dataclass(frozen=True)
class Effect:
    """The observable consequence of one action, per channel.

    ``payloads`` maps a channel name to a *sorted, normalized* list of what
    changed on it — the URLs fetched, the storage keys and values written, the
    console lines emitted. Sorting makes the comparison order-independent.
    Normalization is deliberately narrow (see ``channels.py``): only named
    cache-busting query parameters are collapsed. Blanket digit/hex stripping
    was tried and removed because it absorbed order ids and amounts along with
    timestamps, so a handler that emits a fresh random token on every
    activation will still compare unequal — a disclosed limitation, visible in
    the evidence, rather than a silent dismissal.

    This is the core departure from upstream. Their oracle asked "did any
    channel change?" and so a keyboard press that logged an unrelated warning
    counted as the element working. We compare the payloads themselves.
    """

    changed: frozenset[str] = frozenset()
    payloads: dict[str, tuple[str, ...]] = field(default_factory=dict)

    @property
    def is_empty(self) -> bool:
        """True when the action produced no observable effect at all."""
        return not self.changed

    def same_as(self, other: Effect) -> bool:
        """Whether two effects are the *same* effect, not merely both non-empty.

        Requires the identical channel set and, on every channel carrying a
        payload, the identical payload. Digest-only channels (``dom``,
        ``geometry``) compare by their digest, which is already in ``payloads``
        as a single-element tuple.
        """
        if self.changed != other.changed:
            return False
        return all(
            self.payloads.get(channel, ()) == other.payloads.get(channel, ())
            for channel in self.changed
        )

    def to_json(self) -> dict[str, Any]:
        """Serialize for ``raw.json``; the report is written from this."""
        return {
            "changed": sorted(self.changed),
            "payloads": {k: list(v) for k, v in sorted(self.payloads.items())},
        }


@dataclass(frozen=True)
class ModalityResult:
    """What one input modality (mouse, or one key) did to one probe.

    ``coverage`` holds the V8 executed-function identities for the trial, and is
    empty unless coverage collection was switched on. It exists so upstream's
    Stage-4 formulation — which compares executed-function sets rather than
    observable effects — can be evaluated against ours on the same measurements.
    """

    attempted: bool
    effect: Effect = Effect()
    note: str | None = None
    uncertainty: Uncertainty | None = None
    coverage: frozenset[str] = frozenset()

    def to_json(self) -> dict[str, Any]:
        return {
            "attempted": self.attempted,
            "effect": self.effect.to_json(),
            "note": self.note,
            "uncertainty": self.uncertainty.value if self.uncertainty else None,
            "coverage_size": len(self.coverage),
        }


@dataclass(frozen=True)
class ProbeOutcome:
    """One probe, one viewport, both modalities, and the verdict.

    ``keyboard_by_key`` holds one result per key tried, each from its own fresh
    page state. Upstream pressed Enter, Space and ArrowDown in sequence against
    one mutable page, so a toggle that opened on Enter and closed on Space
    netted to "no effect" and scored as a false positive. Keys are independent
    trials here for exactly that reason.
    """

    probe_id: str
    page: str
    viewport: str
    in_tab_order: bool
    tab_index: int | None
    mouse: ModalityResult
    keyboard_by_key: dict[str, ModalityResult]
    verdict: Verdict
    uncertainty: Uncertainty | None = None
    equivalent_control: str | None = None
    reason: str = ""

    def to_json(self) -> dict[str, Any]:
        """Serialize for ``raw.json``. Schema 2.

        Two changes from schema 1, both to stop the file misleading a reader:

        * ``mouse_effect`` and ``keyboard_by_key[k].effect`` are now the **same
          shape** — an :class:`Effect`. Schema 1 put the mouse's channel list one
          level deeper than the keyboard's, under ``mouse_effect.effect``, so a
          reader comparing the two naively saw every mouse effect as empty.
        * The **union across keys is gone**. It took the first payload seen per
          channel across every key trial, so it could describe a state no single
          trial ever produced — a plausible-looking effect that never happened.
          Verdicts are decided per key, so the per-key records are the evidence;
          anything that needs a summary should say which key it means.
        """
        return {
            "schema_version": 2,
            "id": self.probe_id,
            "page": self.page,
            "viewport": self.viewport,
            "in_tab_order": self.in_tab_order,
            "tab_index": self.tab_index,
            "predicted": self.verdict.value,
            "uncertainty_reason": self.uncertainty.value if self.uncertainty else None,
            "equivalent_control": self.equivalent_control,
            "reason": self.reason,
            # Effect, matching the per-key shape exactly.
            "mouse_effect": self.mouse.effect.to_json(),
            # Everything else the mouse trial recorded, kept beside it rather
            # than wrapped around it.
            "mouse_trial": {
                "attempted": self.mouse.attempted,
                "note": self.mouse.note,
                "uncertainty": self.mouse.uncertainty.value if self.mouse.uncertainty else None,
                "coverage_size": len(self.mouse.coverage),
            },
            "keyboard_by_key": {k: v.to_json() for k, v in sorted(self.keyboard_by_key.items())},
        }


def decide(
    probe_id: str,
    page: str,
    viewport: str,
    *,
    in_tab_order: bool,
    tab_index: int | None,
    mouse: ModalityResult,
    keyboard_by_key: dict[str, ModalityResult],
) -> ProbeOutcome:
    """Apply the oracle to one probe's measurements.

    The rule, in order:

    1. If the mouse read failed, we know nothing -> ``UNKNOWN``.
    2. If the mouse produced no effect, there is no functionality to be missing
       -> ``OK``. (A decoy that does nothing is not a keyboard defect.)
    3. If *any* key reproduced the *same* effect -> ``OK``.
    4. If the element is not in the tab order at all, no key could have been
       tried -> ``VIOLATION``.
    5. Otherwise it is focusable but no key reproduced the effect ->
       ``VIOLATION``. This is the case upstream's ``candidates - T`` subtraction
       removes by construction (their p10/p54 blind spot): the element *is* a
       tab stop, so every candidate generator drops it, yet pressing keys on it
       does nothing. Testing actionability separately from reachability is what
       catches it.
    """
    if mouse.uncertainty is not None:
        return ProbeOutcome(
            probe_id,
            page,
            viewport,
            in_tab_order,
            tab_index,
            mouse,
            keyboard_by_key,
            Verdict.UNKNOWN,
            mouse.uncertainty,
            reason=f"mouse read failed: {mouse.uncertainty.value}",
        )

    if mouse.effect.is_empty:
        return ProbeOutcome(
            probe_id,
            page,
            viewport,
            in_tab_order,
            tab_index,
            mouse,
            keyboard_by_key,
            Verdict.NO_LEAD,
            None,
            reason="mouse produced no observable effect; nothing to reproduce",
        )

    for key, result in sorted(keyboard_by_key.items()):
        # Only a clean trial can clear a finding. A trial that errored may have
        # produced its "matching" effect for reasons we cannot vouch for.
        if result.uncertainty is not None or not result.attempted:
            continue
        if result.effect.same_as(mouse.effect):
            return ProbeOutcome(
                probe_id,
                page,
                viewport,
                in_tab_order,
                tab_index,
                mouse,
                keyboard_by_key,
                Verdict.NO_LEAD,
                None,
                reason=f"{key} reproduced the same effect as the mouse",
            )

    # A cap we hit while walking to this element means we never actually got to
    # press a key on it. That is a failed measurement, not a defect.
    if not in_tab_order and any(
        r.uncertainty is Uncertainty.TAB_CAP for r in keyboard_by_key.values()
    ):
        return ProbeOutcome(
            probe_id,
            page,
            viewport,
            in_tab_order,
            tab_index,
            mouse,
            keyboard_by_key,
            Verdict.UNKNOWN,
            Uncertainty.TAB_CAP,
            reason="tab cap exhausted before the element was reached",
        )

    if not in_tab_order:
        return ProbeOutcome(
            probe_id,
            page,
            viewport,
            in_tab_order,
            tab_index,
            mouse,
            keyboard_by_key,
            Verdict.VIOLATION,
            None,
            reason="mouse-operable and not in the tab order",
        )

    # The element is a tab stop and no key reproduced the effect -- but that is
    # only a defect if every key was actually delivered. **Any** failed trial is
    # enough to withhold the verdict, not just a total failure: if Enter errored
    # and Space cleanly did nothing, Enter may have been the working route, and
    # we cannot tell. Requiring *all* keys to fail before admitting uncertainty
    # would report a defect whenever one clean key happened to run.
    blocked = next(
        (r.uncertainty for r in keyboard_by_key.values() if r.uncertainty is not None),
        None,
    )
    if blocked is not None:
        return ProbeOutcome(
            probe_id,
            page,
            viewport,
            in_tab_order,
            tab_index,
            mouse,
            keyboard_by_key,
            Verdict.UNKNOWN,
            blocked,
            reason=(
                "at least one key trial failed, so an untested key may be the "
                "working keyboard route"
            ),
        )

    usable = [r for r in keyboard_by_key.values() if r.attempted]
    if not usable:
        blocked = next(
            (r.uncertainty for r in keyboard_by_key.values() if r.uncertainty is not None),
            Uncertainty.INSTRUMENT_ERROR,
        )
        return ProbeOutcome(
            probe_id,
            page,
            viewport,
            in_tab_order,
            tab_index,
            mouse,
            keyboard_by_key,
            Verdict.UNKNOWN,
            blocked,
            reason="no key trial completed cleanly; the element was never actually tested",
        )

    return ProbeOutcome(
        probe_id,
        page,
        viewport,
        in_tab_order,
        tab_index,
        mouse,
        keyboard_by_key,
        Verdict.VIOLATION,
        None,
        reason="focusable, but no key reproduced the mouse's effect",
    )
