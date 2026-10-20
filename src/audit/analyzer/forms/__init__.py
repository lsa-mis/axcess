"""Form error check (WCAG SC 3.3.1 Error Identification).

Submits each form once, empty, with every request that could change anything
blocked, and reports a form that detects an error without identifying it and
describing it in text. See ``base.py`` for the rules and ``probe.py`` for how
the page is driven.
"""

from audit.analyzer.forms.base import FormResult, classify, skip_reason
from audit.analyzer.forms.probe import ErrorIdentificationProbe

__all__ = ["ErrorIdentificationProbe", "FormResult", "classify", "skip_reason"]
