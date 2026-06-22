"""Vision-model visual analyzers (run on a live-page screenshot).

Unlike the deterministic focus probe, these need a VLM: they screenshot the
rendered page and ask a local vision model a per-criterion question. First
criterion: SC 1.3.2 Meaningful Sequence (does the visual reading order match
the DOM/source order?). The vision capability is
:class:`audit.analyzer.vlm.vision.OllamaVisionProvider`.
"""

from audit.analyzer.visual.base import (
    RULE_MEANINGFUL_SEQUENCE,
    RULE_MOTION_NO_PAUSE,
    VisualFinding,
)
from audit.analyzer.visual.probe import VisualProbe

__all__ = [
    "RULE_MEANINGFUL_SEQUENCE",
    "RULE_MOTION_NO_PAUSE",
    "VisualFinding",
    "VisualProbe",
]
