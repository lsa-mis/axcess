"""Oracle logic for the keyboard differential.

Each test here pins a decision that upstream's implementation got wrong. The
names say which defect is being guarded, because the point of these is to fail
loudly if someone "simplifies" the oracle back into the shape that produced the
original false positives.
"""

from __future__ import annotations

from audit.analyzer.keyboard.kbdiff.model import (
    Effect,
    ModalityResult,
    Uncertainty,
    Verdict,
    decide,
)


def _effect(**channels: tuple[str, ...]) -> Effect:
    return Effect(frozenset(channels), dict(channels))


def _outcome(mouse: ModalityResult, keyboard: dict[str, ModalityResult], *, in_tab: bool):
    return decide(
        "p01",
        "a.html",
        "desktop",
        in_tab_order=in_tab,
        tab_index=3 if in_tab else None,
        mouse=mouse,
        keyboard_by_key=keyboard,
    )


class TestEffectEquality:
    def test_same_channels_and_payloads_are_the_same_effect(self):
        a = _effect(net=("/api/save",))
        assert a.same_as(_effect(net=("/api/save",)))

    def test_same_channel_different_payload_is_not_the_same_effect(self):
        """The bug this guards: upstream compared *whether* a channel changed.

        Both of these touch the network. They call different endpoints, so the
        keyboard did not reproduce what the mouse did.
        """
        assert not _effect(net=("/api/save",)).same_as(_effect(net=("/api/delete",)))

    def test_different_channels_are_not_the_same_effect(self):
        assert not _effect(net=("/api/x",)).same_as(_effect(console=("log:x",)))

    def test_empty_effect_is_empty(self):
        assert Effect().is_empty
        assert not _effect(dom=("123",)).is_empty


class TestDecide:
    def test_mouse_does_nothing_is_not_a_defect(self):
        """A decoy that looks clickable and does nothing is not a keyboard bug."""
        outcome = _outcome(
            ModalityResult(attempted=True, effect=Effect()),
            {"Enter": ModalityResult(attempted=True, effect=Effect())},
            in_tab=True,
        )
        assert outcome.verdict is Verdict.NO_LEAD

    def test_keyboard_reproducing_the_same_effect_passes(self):
        eff = _effect(net=("/api/save",))
        outcome = _outcome(
            ModalityResult(attempted=True, effect=eff),
            {"Enter": ModalityResult(attempted=True, effect=eff)},
            in_tab=True,
        )
        assert outcome.verdict is Verdict.NO_LEAD
        assert "Enter" in outcome.reason

    def test_unrelated_keyboard_effect_does_not_clear_a_defect(self):
        """Upstream's `k.length === 0` test cleared a defect on any keyboard noise.

        The mouse saved something; the keypress only logged a warning. That is
        still a control with no keyboard equivalent.
        """
        outcome = _outcome(
            ModalityResult(attempted=True, effect=_effect(net=("/api/save",))),
            {"Enter": ModalityResult(attempted=True, effect=_effect(console=("warn:x",)))},
            in_tab=True,
        )
        assert outcome.verdict is Verdict.VIOLATION

    def test_not_in_tab_order_with_mouse_effect_is_a_violation(self):
        outcome = _outcome(
            ModalityResult(attempted=True, effect=_effect(dom=("42",))),
            {"(none)": ModalityResult(attempted=False)},
            in_tab=False,
        )
        assert outcome.verdict is Verdict.VIOLATION
        assert "not in the tab order" in outcome.reason

    def test_focusable_but_inert_to_keys_is_still_a_violation(self):
        """The p10/p54 blind spot: in the tab order, but no key does anything.

        Every candidate generator that reports ``candidates - T`` deletes this
        case by construction. Testing actionability separately from reachability
        is the only way to catch it.
        """
        outcome = _outcome(
            ModalityResult(attempted=True, effect=_effect(dom=("42",))),
            {
                "Enter": ModalityResult(attempted=True, effect=Effect()),
                "Space": ModalityResult(attempted=True, effect=Effect()),
            },
            in_tab=True,
        )
        assert outcome.verdict is Verdict.VIOLATION
        assert "no key reproduced" in outcome.reason

    def test_tab_cap_is_unknown_not_a_violation(self):
        """A measurement we could not take is not evidence of a defect."""
        outcome = _outcome(
            ModalityResult(attempted=True, effect=_effect(dom=("42",))),
            {"(none)": ModalityResult(attempted=False, uncertainty=Uncertainty.TAB_CAP)},
            in_tab=False,
        )
        assert outcome.verdict is Verdict.UNKNOWN
        assert outcome.uncertainty is Uncertainty.TAB_CAP

    def test_failed_mouse_read_is_unknown(self):
        outcome = _outcome(
            ModalityResult(attempted=False, uncertainty=Uncertainty.UNRESOLVED),
            {},
            in_tab=False,
        )
        assert outcome.verdict is Verdict.UNKNOWN
        assert outcome.uncertainty is Uncertainty.UNRESOLVED

    def test_not_mouse_operable_is_unknown_not_a_violation(self):
        """`pointer-events:none` / `inert`: no user can click it either.

        Upstream reported three false positives of exactly this shape because
        their visibility gate did not cover these two cases.
        """
        outcome = _outcome(
            ModalityResult(attempted=False, uncertainty=Uncertainty.NOT_RENDERED),
            {},
            in_tab=False,
        )
        assert outcome.verdict is not Verdict.VIOLATION

    def test_any_key_succeeding_is_enough(self):
        """Space works even though Enter does not: the functionality is operable."""
        eff = _effect(dom=("42",))
        outcome = _outcome(
            ModalityResult(attempted=True, effect=eff),
            {
                "Enter": ModalityResult(attempted=True, effect=Effect()),
                "Space": ModalityResult(attempted=True, effect=eff),
            },
            in_tab=True,
        )
        assert outcome.verdict is Verdict.NO_LEAD


class TestUncertainKeyTrials:
    """A verdict needs a trial that actually happened.

    ``decide`` once fell through to VIOLATION whenever no key matched, without
    asking whether any key had been successfully delivered. An element whose
    every key trial errored was then reported as a confident defect on the
    strength of measurements that never took place.
    """

    def test_all_key_trials_failing_is_unknown_not_a_violation(self):
        outcome = _outcome(
            ModalityResult(attempted=True, effect=_effect(dom=("42",))),
            {
                "Enter": ModalityResult(attempted=False, uncertainty=Uncertainty.INSTRUMENT_ERROR),
                "Space": ModalityResult(attempted=False, uncertainty=Uncertainty.INSTRUMENT_ERROR),
            },
            in_tab=True,
        )
        assert outcome.verdict is Verdict.UNKNOWN
        assert outcome.uncertainty is Uncertainty.INSTRUMENT_ERROR

    def test_focus_landing_on_the_wrong_element_is_unknown(self):
        """Set T is measured on a separate load; the walk can end up one stop off."""
        outcome = _outcome(
            ModalityResult(attempted=True, effect=_effect(dom=("42",))),
            {"Enter": ModalityResult(attempted=False, uncertainty=Uncertainty.UNRESOLVED)},
            in_tab=True,
        )
        assert outcome.verdict is Verdict.UNKNOWN

    def test_an_errored_trial_cannot_clear_a_finding(self):
        """A matching effect from a trial we cannot vouch for proves nothing."""
        eff = _effect(dom=("42",))
        outcome = _outcome(
            ModalityResult(attempted=True, effect=eff),
            {
                "Enter": ModalityResult(
                    attempted=True, effect=eff, uncertainty=Uncertainty.INSTRUMENT_ERROR
                )
            },
            in_tab=True,
        )
        assert outcome.verdict is not Verdict.NO_LEAD

    def test_one_errored_key_withholds_the_verdict(self):
        """Mixed result: a clean key that does nothing plus a key that errored.

        Enter never ran; Space ran and did nothing. Enter may have been the
        working keyboard route, so we cannot call this a defect. Requiring
        *every* key to fail before admitting uncertainty would report a defect
        whenever one clean key happened to execute.
        """
        outcome = _outcome(
            ModalityResult(attempted=True, effect=_effect(dom=("42",))),
            {
                "Enter": ModalityResult(attempted=False, uncertainty=Uncertainty.INSTRUMENT_ERROR),
                "Space": ModalityResult(attempted=True, effect=Effect()),
            },
            in_tab=True,
        )
        assert outcome.verdict is Verdict.UNKNOWN
        assert "untested key" in outcome.reason

    def test_a_clean_match_still_wins_over_an_errored_sibling(self):
        """Uncertainty elsewhere must not mask a key that demonstrably worked."""
        eff = _effect(dom=("42",))
        outcome = _outcome(
            ModalityResult(attempted=True, effect=eff),
            {
                "Enter": ModalityResult(attempted=False, uncertainty=Uncertainty.INSTRUMENT_ERROR),
                "Space": ModalityResult(attempted=True, effect=eff),
            },
            in_tab=True,
        )
        assert outcome.verdict is Verdict.NO_LEAD

    def test_all_keys_clean_and_none_matching_is_still_a_violation(self):
        """The fix must not make every verdict uncertain."""
        outcome = _outcome(
            ModalityResult(attempted=True, effect=_effect(dom=("42",))),
            {
                "Enter": ModalityResult(attempted=True, effect=Effect()),
                "Space": ModalityResult(attempted=True, effect=Effect()),
            },
            in_tab=True,
        )
        assert outcome.verdict is Verdict.VIOLATION
