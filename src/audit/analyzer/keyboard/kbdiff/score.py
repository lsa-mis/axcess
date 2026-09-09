"""Scoring, with ``unknown`` kept out of the pass/fail buckets.

The rule that governs this module: **every probe is accounted for.**
``tp + fp + fn + tn + unknown`` always equals the number of probes scored. A
detector that cannot measure something has not passed it and has not failed it,
and folding those cases into either bucket flatters or damns the result for no
reason. Upstream had no ``unknown`` category at all, so a probe it could not
reach became evidence of a defect.

**Recall is strict**: ``tp / (tp + fn + unknown_positive)``. A real defect the
instrument could not read still counts against the detector, so refusing to
answer can never raise the headline figure. ``recall_conditional`` is the looser
form over decided probes only, published beside it as a diagnostic — the gap
between the two is the cost of what the instrument could not measure. Precision
is over predicted positives, which are by definition decided.

A detector scoring 100% on the 5 probes it managed to read is not better than
one scoring 90% on all 60, and the shape of this record makes that visible
rather than hiding it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from audit.analyzer.keyboard.kbdiff.model import ProbeOutcome, Verdict

# Ground-truth labels. ``violation`` is the only positive; the other three are
# all negatives, kept distinct because they fail in different ways and the
# report breaks them out.
POSITIVE_LABEL = "violation"
NEGATIVE_LABELS = ("ok", "decoy", "excluded")


@dataclass
class Score:
    """One detector's result on one cohort, in one viewport, in one mode."""

    detector: str
    cohort: str
    viewport: str
    mode: str  # "oracle" (targets supplied) or "end_to_end" (targets discovered)
    tp: int = 0
    fp: int = 0
    fn: int = 0
    tn: int = 0
    # Undecided probes, split by what the ground truth says they were. The split
    # matters: an unknown that was really a violation is a missed defect, and
    # folding it away is how a detector buys recall by refusing to answer.
    unknown_positive: int = 0
    unknown_negative: int = 0
    false_positives: list[str] = field(default_factory=list)
    false_negatives: list[str] = field(default_factory=list)
    undecided: list[str] = field(default_factory=list)

    @property
    def unknown(self) -> int:
        return self.unknown_positive + self.unknown_negative

    @property
    def decided(self) -> int:
        return self.tp + self.fp + self.fn + self.tn

    @property
    def total(self) -> int:
        """Every probe considered. The invariant this module exists to hold."""
        return self.decided + self.unknown

    @property
    def precision(self) -> float | None:
        """None, not zero, when nothing was predicted positive.

        Zero would read as "it got everything wrong"; the truth is that the
        question does not apply. Upstream printed an em dash for this case and
        was right to.
        """
        predicted_positive = self.tp + self.fp
        return self.tp / predicted_positive if predicted_positive else None

    @property
    def recall(self) -> float | None:
        """Strict recall: undecided positives count against us.

        ``tp / (tp + fn + unknown_positive)``. This is the headline figure, and
        the denominator is deliberately every real defect in the corpus — not
        every defect we managed to reach. Scoring over decided probes only would
        let a detector raise its recall by returning ``unknown`` on the hard
        cases, which is precisely backwards: refusing to answer is not a
        partial success. A real defect we could not measure is still a defect a
        user meets.
        """
        actual_positive = self.tp + self.fn + self.unknown_positive
        return self.tp / actual_positive if actual_positive else None

    @property
    def recall_conditional(self) -> float | None:
        """Recall over the probes we could decide. Diagnostic, never the headline.

        The gap between this and :attr:`recall` is exactly the cost of the
        probes the instrument could not read, which is worth seeing separately
        when deciding whether to fix the instrument or the detector.
        """
        decided_positive = self.tp + self.fn
        return self.tp / decided_positive if decided_positive else None

    @property
    def f1(self) -> float | None:
        """F1 over the strict recall, so undecided positives are priced in here too."""
        p, r = self.precision, self.recall
        if p is None or r is None or (p + r) == 0:
            return None
        return 2 * p * r / (p + r)

    @property
    def coverage(self) -> float:
        """Fraction of probes we could actually decide. Context for the rest."""
        return self.decided / self.total if self.total else 0.0

    def to_json(self) -> dict[str, Any]:
        return {
            "detector": self.detector,
            "cohort": self.cohort,
            "viewport": self.viewport,
            "mode": self.mode,
            "tp": self.tp,
            "fp": self.fp,
            "fn": self.fn,
            "tn": self.tn,
            "unknown": self.unknown,
            "unknown_positive": self.unknown_positive,
            "unknown_negative": self.unknown_negative,
            "decided": self.decided,
            "total": self.total,
            "classified_coverage": round(self.coverage, 4),
            "precision": _round(self.precision),
            "recall": _round(self.recall),
            "recall_conditional": _round(self.recall_conditional),
            "f1": _round(self.f1),
            "false_positives": sorted(self.false_positives),
            "false_negatives": sorted(self.false_negatives),
            "undecided": sorted(self.undecided),
        }


def _round(value: float | None) -> float | None:
    return None if value is None else round(value, 4)


def score_outcomes(
    outcomes: list[ProbeOutcome],
    truth: dict[str, str],
    *,
    detector: str,
    cohort: str = "all",
    viewport: str = "all",
    mode: str = "oracle",
) -> Score:
    """Score predictions against ground truth.

    ``truth`` maps probe id to label. A probe missing from ``truth`` is skipped
    entirely rather than guessed at: it is not our corpus to judge.
    """
    result = Score(detector=detector, cohort=cohort, viewport=viewport, mode=mode)

    for outcome in outcomes:
        label = truth.get(outcome.probe_id)
        if label is None:
            continue

        is_positive = label == POSITIVE_LABEL

        if outcome.verdict is Verdict.UNKNOWN:
            if is_positive:
                result.unknown_positive += 1
            else:
                result.unknown_negative += 1
            result.undecided.append(outcome.probe_id)
            continue

        predicted_positive = outcome.verdict is Verdict.VIOLATION
        if predicted_positive and is_positive:
            result.tp += 1
        elif predicted_positive and not is_positive:
            result.fp += 1
            result.false_positives.append(outcome.probe_id)
        elif not predicted_positive and is_positive:
            result.fn += 1
            result.false_negatives.append(outcome.probe_id)
        else:
            result.tn += 1

    return result


def check_invariant(score: Score, expected_total: int) -> None:
    """Fail loudly if any probe went missing.

    Called by the runner after every scoring pass. A silent drop is the failure
    mode this whole module is built to prevent, so it raises rather than logs.
    """
    if score.total != expected_total:
        raise AssertionError(
            f"score '{score.detector}' accounts for {score.total} probes, "
            f"expected {expected_total}; probes were dropped"
        )
