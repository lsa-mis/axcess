"""Live-page error-identification runtime probe (SC 3.3.1).

Runs inside the Playwright session (like the keyboard/focus/responsive
probes) because the error state it checks only exists after a form tries to
validate. It triggers each invalid form's client-side validation with
``reportValidity()`` — which never submits — and then reads the DOM to check
whether the resulting error is identified in text and associated with the
field. Fully deterministic (no model).
"""

from audit.analyzer.error_id.base import (
    RULE_NOT_ASSOCIATED,
    RULE_NOT_IDENTIFIED,
    ErrorIdentificationFinding,
)
from audit.analyzer.error_id.probe import ErrorIdentificationProbe, classify

__all__ = [
    "RULE_NOT_ASSOCIATED",
    "RULE_NOT_IDENTIFIED",
    "ErrorIdentificationFinding",
    "ErrorIdentificationProbe",
    "classify",
]
