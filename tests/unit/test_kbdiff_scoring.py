"""Scoring, equivalence dismissal, and channel normalization.

The invariant under test throughout: no probe is ever silently dropped, and an
unmeasurable probe is never counted as a pass or a fail.
"""

from __future__ import annotations

import pytest

from audit.analyzer.keyboard.kbdiff.channels import diff, normalize
from audit.analyzer.keyboard.kbdiff.equivalence import apply_equivalence
from audit.analyzer.keyboard.kbdiff.model import (
    Effect,
    ModalityResult,
    ProbeOutcome,
    Verdict,
)
from audit.analyzer.keyboard.kbdiff.score import check_invariant, score_outcomes


def _effect(**channels: tuple[str, ...]) -> Effect:
    return Effect(frozenset(channels), dict(channels))


def _outcome(
    probe_id: str,
    verdict: Verdict,
    *,
    page: str = "a.html",
    in_tab: bool = False,
    mouse: Effect | None = None,
    keys: dict[str, Effect] | None = None,
) -> ProbeOutcome:
    return ProbeOutcome(
        probe_id=probe_id,
        page=page,
        viewport="desktop",
        in_tab_order=in_tab,
        tab_index=1 if in_tab else None,
        mouse=ModalityResult(attempted=True, effect=mouse or Effect()),
        keyboard_by_key={
            k: ModalityResult(attempted=True, effect=v) for k, v in (keys or {}).items()
        },
        verdict=verdict,
    )


class TestScoring:
    def test_every_probe_is_accounted_for(self):
        outcomes = [
            _outcome("p1", Verdict.VIOLATION),
            _outcome("p2", Verdict.NO_LEAD),
            _outcome("p3", Verdict.UNKNOWN),
        ]
        truth = {"p1": "violation", "p2": "ok", "p3": "violation"}
        score = score_outcomes(outcomes, truth, detector="d")

        assert score.total == 3
        check_invariant(score, 3)

    def test_unknown_is_not_a_pass_and_not_a_fail(self):
        """The upstream behaviour this replaces: a capped probe became a negative."""
        outcomes = [_outcome("p1", Verdict.UNKNOWN)]
        score = score_outcomes(outcomes, {"p1": "violation"}, detector="d")

        assert score.unknown == 1
        assert (score.tp, score.fp, score.fn, score.tn) == (0, 0, 0, 0)
        assert score.undecided == ["p1"]

    def test_precision_is_none_when_nothing_was_predicted_positive(self):
        """None, not 0.0. Zero would read as 'got everything wrong'."""
        score = score_outcomes([_outcome("p1", Verdict.NO_LEAD)], {"p1": "violation"}, detector="d")
        assert score.precision is None
        assert score.recall == 0.0

    def test_decoy_and_excluded_count_as_negatives(self):
        outcomes = [_outcome("p1", Verdict.VIOLATION), _outcome("p2", Verdict.NO_LEAD)]
        score = score_outcomes(outcomes, {"p1": "decoy", "p2": "excluded"}, detector="d")
        assert score.fp == 1
        assert score.tn == 1

    def test_coverage_reports_how_much_was_actually_decided(self):
        outcomes = [
            _outcome("p1", Verdict.VIOLATION),
            _outcome("p2", Verdict.UNKNOWN),
        ]
        score = score_outcomes(outcomes, {"p1": "violation", "p2": "violation"}, detector="d")
        assert score.coverage == 0.5

    def test_invariant_raises_when_probes_go_missing(self):
        score = score_outcomes([_outcome("p1", Verdict.NO_LEAD)], {"p1": "ok"}, detector="d")
        with pytest.raises(AssertionError, match="dropped"):
            check_invariant(score, 2)

    def test_probes_absent_from_truth_are_skipped_not_guessed(self):
        score = score_outcomes([_outcome("pX", Verdict.VIOLATION)], {"p1": "ok"}, detector="d")
        assert score.total == 0


class TestEquivalence:
    def test_same_page_control_with_the_same_effect_dismisses_a_finding(self):
        save = _effect(net=("/api/save",))
        outcomes = [
            _outcome("p1", Verdict.VIOLATION, mouse=save),
            _outcome("p2", Verdict.NO_LEAD, in_tab=True, keys={"Enter": save}),
        ]
        rewritten, dismissals = apply_equivalence(outcomes)

        assert rewritten[0].verdict is Verdict.NO_LEAD
        assert rewritten[0].equivalent_control == "p2"
        assert [d.probe_id for d in dismissals] == ["p1"]

    def test_a_control_on_another_page_does_not_dismiss(self):
        """Upstream searched every page's controls; conformance is per page.

        A keyboard user on ``a.html`` cannot use a control that only exists on
        ``b.html``, so the finding stands.
        """
        save = _effect(net=("/api/save",))
        outcomes = [
            _outcome("p1", Verdict.VIOLATION, page="a.html", mouse=save),
            _outcome("p2", Verdict.NO_LEAD, page="b.html", in_tab=True, keys={"Enter": save}),
        ]
        rewritten, dismissals = apply_equivalence(outcomes)

        assert rewritten[0].verdict is Verdict.VIOLATION
        assert dismissals == []

    def test_a_different_effect_does_not_dismiss(self):
        outcomes = [
            _outcome("p1", Verdict.VIOLATION, mouse=_effect(net=("/api/save",))),
            _outcome(
                "p2",
                Verdict.NO_LEAD,
                in_tab=True,
                keys={"Enter": _effect(net=("/api/delete",))},
            ),
        ]
        rewritten, _ = apply_equivalence(outcomes)
        assert rewritten[0].verdict is Verdict.VIOLATION

    def test_a_control_that_does_nothing_dismisses_nothing(self):
        outcomes = [
            _outcome("p1", Verdict.VIOLATION, mouse=_effect(dom=("1",))),
            _outcome("p2", Verdict.NO_LEAD, in_tab=True, keys={"Enter": Effect()}),
        ]
        rewritten, _ = apply_equivalence(outcomes)
        assert rewritten[0].verdict is Verdict.VIOLATION


class TestChannels:
    def test_normalize_strips_named_cache_busting_params(self):
        """A parameter whose purpose is to differ per request carries no meaning."""
        assert normalize("/api/x?t=1699999999") == normalize("/api/x?t=1700000000")

    def test_normalize_preserves_identifiers_in_the_path(self):
        """Two different order ids are two different outcomes.

        Blanket digit/hex collapsing was tried and removed. It absorbed
        timestamps, but it absorbed order numbers and amounts too, so a keypress
        that saved the WRONG record compared equal to one that saved the right
        one — a false negative with no trace in the evidence.
        """
        assert normalize("/api/orders/847213") != normalize("/api/orders/847214")
        assert normalize("/api/deadbeefcafe") != normalize("/api/0123456789ab")

    def test_distinct_six_digit_ids_are_not_equivalent(self):
        """The regression Codex asked for, at the Effect level."""
        left = _effect(dom=("receipt 847213",))
        right = _effect(dom=("receipt 998877",))
        assert not left.same_as(right)

    def test_diff_reports_appended_log_entries(self):
        before = {"dom": "1", "geometry": "1", "nav": "u", "net": [], "console": [], "storage": []}
        after = {**before, "net": ["/api/save"]}
        effect = diff(before, after)
        assert "net" in effect.changed
        assert effect.payloads["net"] == ("/api/save",)

    def test_diff_is_empty_when_nothing_changed(self):
        snap = {"dom": "1", "geometry": "1", "nav": "u", "net": [], "console": [], "storage": []}
        assert diff(snap, dict(snap)).is_empty

    def test_repeated_identical_calls_are_two_events(self):
        """Length-slicing, not set-diffing: two fetches to one URL is two events."""
        before = {
            "dom": "1",
            "geometry": "1",
            "nav": "u",
            "net": ["/a"],
            "console": [],
            "storage": [],
        }
        after = {**before, "net": ["/a", "/a", "/a"]}
        assert diff(before, after).payloads["net"] == ("/a", "/a")

    def test_geometry_change_alone_is_an_effect(self):
        """A pure-CSS :hover reveal touches no JS and leaves innerHTML identical."""
        before = {"dom": "1", "geometry": "1", "nav": "u", "net": [], "console": [], "storage": []}
        after = {**before, "geometry": "2"}
        effect = diff(before, after)
        assert effect.changed == frozenset({"geometry"})


class TestStrictRecall:
    """Undecided positives must count against recall.

    Without this, a detector improves its reported recall by returning
    ``unknown`` on the probes it finds hard, which inverts the incentive the
    score is supposed to create.
    """

    def test_unknown_positive_lowers_recall(self):
        outcomes = [
            _outcome("p1", Verdict.VIOLATION),
            _outcome("p2", Verdict.UNKNOWN),
        ]
        truth = {"p1": "violation", "p2": "violation"}
        score = score_outcomes(outcomes, truth, detector="d")

        assert score.unknown_positive == 1
        assert score.recall == 0.5  # 1 / (1 tp + 0 fn + 1 unknown positive)

    def test_conditional_recall_ignores_the_undecided(self):
        outcomes = [
            _outcome("p1", Verdict.VIOLATION),
            _outcome("p2", Verdict.UNKNOWN),
        ]
        truth = {"p1": "violation", "p2": "violation"}
        score = score_outcomes(outcomes, truth, detector="d")

        assert score.recall_conditional == 1.0
        assert score.recall != score.recall_conditional

    def test_refusing_to_answer_cannot_beat_answering_correctly(self):
        """The property that matters, stated directly as a comparison."""
        truth = {"p1": "violation", "p2": "violation"}
        answered = score_outcomes(
            [_outcome("p1", Verdict.VIOLATION), _outcome("p2", Verdict.VIOLATION)],
            truth,
            detector="answered",
        )
        refused = score_outcomes(
            [_outcome("p1", Verdict.VIOLATION), _outcome("p2", Verdict.UNKNOWN)],
            truth,
            detector="refused",
        )
        assert answered.recall is not None
        assert refused.recall is not None
        assert refused.recall < answered.recall

    def test_unknown_negative_does_not_touch_recall(self):
        outcomes = [_outcome("p1", Verdict.VIOLATION), _outcome("p2", Verdict.UNKNOWN)]
        score = score_outcomes(outcomes, {"p1": "violation", "p2": "decoy"}, detector="d")

        assert score.unknown_negative == 1
        assert score.recall == 1.0


class TestUnscoredCoverageStrategies:
    """Optional strategies must not combine evidence from unrelated key trials."""

    @pytest.mark.parametrize("kind", ["exact", "similarity"])
    def test_matching_channels_and_coverage_must_come_from_same_clean_trial(self, kind):
        from dataclasses import replace

        from audit.analyzer.keyboard.kbdiff.equivalence import (
            by_coverage_exact,
            by_coverage_jaccard,
        )
        from audit.analyzer.keyboard.kbdiff.model import Uncertainty

        mouse = ModalityResult(True, _effect(dom=("x",)), coverage=frozenset({"fn-a"}))
        finding = replace(_outcome("f", Verdict.VIOLATION), mouse=mouse)
        candidate = replace(
            _outcome("k", Verdict.NO_LEAD, in_tab=True),
            keyboard_by_key={
                "Enter": ModalityResult(True, mouse.effect, coverage=frozenset({"fn-b"})),
                "Space": ModalityResult(True, _effect(net=("/other",)), coverage=mouse.coverage),
                "ArrowDown": ModalityResult(
                    True,
                    mouse.effect,
                    uncertainty=Uncertainty.INSTRUMENT_ERROR,
                    coverage=mouse.coverage,
                ),
            },
        )
        strategy = by_coverage_exact if kind == "exact" else by_coverage_jaccard(1)
        assert not strategy(finding, candidate)
        candidate = replace(candidate, keyboard_by_key={"Enter": mouse})
        assert strategy(finding, candidate)

    def test_containment_abstains_without_dom_relationship_evidence(self):
        from audit.analyzer.keyboard.kbdiff.equivalence import by_containment

        finding = _outcome("f", Verdict.VIOLATION, mouse=_effect(dom=("x",)))
        candidate = _outcome("k", Verdict.NO_LEAD, in_tab=True, keys={"Enter": _effect(dom=("x",))})
        assert not by_containment(finding, candidate)
