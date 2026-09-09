"""Experimental keyboard-differential detector for SC 2.1.1 (Keyboard).

Not wired into the scan orchestrator. It is exercised only by
``experiments/tabbing/runner`` and scored against a held-out fixture corpus.
See ``experiments/tabbing/`` for the study this belongs to.
"""

from audit.analyzer.keyboard.kbdiff.candidates import (
    Candidate,
    candidate_probe_ids,
    collect_candidates,
)
from audit.analyzer.keyboard.kbdiff.differential import DifferentialRunner, TrialConfig
from audit.analyzer.keyboard.kbdiff.equivalence import Dismissal, apply_equivalence
from audit.analyzer.keyboard.kbdiff.model import (
    CHANNELS,
    Effect,
    ModalityResult,
    ProbeOutcome,
    Uncertainty,
    Verdict,
    decide,
)
from audit.analyzer.keyboard.kbdiff.score import Score, check_invariant, score_outcomes
from audit.analyzer.keyboard.kbdiff.taborder import TabOrder, compute_tab_order

__all__ = [
    "CHANNELS",
    "Candidate",
    "DifferentialRunner",
    "Dismissal",
    "Effect",
    "ModalityResult",
    "ProbeOutcome",
    "Score",
    "TabOrder",
    "TrialConfig",
    "Uncertainty",
    "Verdict",
    "apply_equivalence",
    "candidate_probe_ids",
    "check_invariant",
    "collect_candidates",
    "compute_tab_order",
    "decide",
    "score_outcomes",
]
