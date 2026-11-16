"""Page code check: deterministic checks of the rendered page code (DOM).

Runs in the Playwright session right after the rule check (axe) and reads the
page without changing it. It reports patterns that axe-core does not, each
as its own issue type (``markup:<rule_id>``). No model is involved.
"""

from audit.analyzer.markup.base import (
    MAX_RESULTS_PER_RULE,
    PIPELINE,
    RULES,
    MarkupFinding,
    MarkupRule,
    rule_for,
)
from audit.analyzer.markup.probe import MarkupProbe

__all__ = [
    "MAX_RESULTS_PER_RULE",
    "PIPELINE",
    "RULES",
    "MarkupFinding",
    "MarkupProbe",
    "MarkupRule",
    "rule_for",
]
