"""Live-page interaction probe: click controls, re-run axe on what appears."""

from audit.analyzer.interaction.base import InteractionResult, RevealedViolation
from audit.analyzer.interaction.probe import DEFAULT_BLOCKED_LABELS, InteractionProbe

__all__ = [
    "DEFAULT_BLOCKED_LABELS",
    "InteractionProbe",
    "InteractionResult",
    "RevealedViolation",
]
