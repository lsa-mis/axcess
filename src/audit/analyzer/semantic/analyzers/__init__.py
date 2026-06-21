"""Concrete per-criterion semantic analyzers.

One class per WCAG SC. Each class implements the
:class:`audit.analyzer.semantic.base.SemanticAnalyzer` protocol and is
registered in :mod:`audit.analyzer.semantic.registry`.

Ships SC 2.4.4 (Link Purpose) and SC 2.4.6 (Headings descriptiveness);
more wave-1 SCs land one class at a time.
"""

from audit.analyzer.semantic.analyzers.sc_1_2_1 import (
    AudioTranscriptAnalyzer,
)
from audit.analyzer.semantic.analyzers.sc_2_4_4 import (
    LinkPurposeInContextAnalyzer,
)
from audit.analyzer.semantic.analyzers.sc_2_4_6 import (
    HeadingsAndLabelsAnalyzer,
)
from audit.analyzer.semantic.analyzers.sc_3_3_2 import (
    LabelsOrInstructionsAnalyzer,
)

__all__ = [
    "AudioTranscriptAnalyzer",
    "HeadingsAndLabelsAnalyzer",
    "LabelsOrInstructionsAnalyzer",
    "LinkPurposeInContextAnalyzer",
]
