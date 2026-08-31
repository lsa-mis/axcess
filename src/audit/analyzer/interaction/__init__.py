"""Live-page interaction probe: click controls, re-run axe on what appears."""

from audit.analyzer.interaction.base import RevealedViolation
from audit.analyzer.interaction.probe import InteractionProbe

__all__ = ["InteractionProbe", "RevealedViolation"]
