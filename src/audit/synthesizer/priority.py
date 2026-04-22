"""Priority scoring + severity mapping for synthesized findings.

Formula (per PLAN.md Phase 5)::

    priority_score =
          classification_weight[vlm_class]   # essential=4, informational=3, logo=1,
                                              # decorative=1, no_meaningful_text=0, none=0
        + alt_adequacy_weight[bucket]        # missing=3, inadequate=2, partial=1, adequate=0
        + log1p(occurrence_count)            # ~0..3
        + visibility_weight                  # above_fold=+1, else=0

    severity = critical  if score >= 8
             | major     if score >= 5
             | minor     if score >= 2
             | info      otherwise

The weights live in this module so the formula can evolve in one place and
golden tests pin every (classification, adequacy) combination.
"""

from __future__ import annotations

from enum import StrEnum
from math import log1p

from audit.analyzer.vlm.base import VlmLabel
from audit.synthesizer.alt_compare import AltAdequacy


class Severity(StrEnum):
    CRITICAL = "critical"
    MAJOR = "major"
    MINOR = "minor"
    INFO = "info"


CLASSIFICATION_WEIGHTS: dict[VlmLabel | None, int] = {
    VlmLabel.ESSENTIAL: 4,
    VlmLabel.INFORMATIONAL: 3,
    VlmLabel.LOGO: 1,
    VlmLabel.DECORATIVE: 1,
    VlmLabel.NO_MEANINGFUL_TEXT: 0,
    None: 0,
}

ADEQUACY_WEIGHTS: dict[AltAdequacy, int] = {
    AltAdequacy.MISSING: 3,
    AltAdequacy.INADEQUATE: 2,
    AltAdequacy.PARTIAL: 1,
    AltAdequacy.ADEQUATE: 0,
}


def compute_priority_score(
    *,
    classification: VlmLabel | None,
    adequacy: AltAdequacy,
    occurrence_count: int,
    above_fold: bool,
) -> float:
    """Compute the priority score for one ``(image, scan)`` pair."""
    cls_weight = CLASSIFICATION_WEIGHTS.get(classification, 0)
    adeq_weight = ADEQUACY_WEIGHTS[adequacy]
    occ_weight = log1p(max(0, occurrence_count))
    vis_weight = 1 if above_fold else 0
    return round(cls_weight + adeq_weight + occ_weight + vis_weight, 3)


def severity_for(score: float) -> Severity:
    """Map a priority score to its severity bucket."""
    if score >= 8:
        return Severity.CRITICAL
    if score >= 5:
        return Severity.MAJOR
    if score >= 2:
        return Severity.MINOR
    return Severity.INFO
