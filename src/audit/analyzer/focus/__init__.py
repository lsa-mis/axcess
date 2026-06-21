"""Live-page focus runtime probes (SC 2.4.11 today; 2.4.3 next).

These run inside the Playwright session (like the keyboard/responsive
probes) because they need the *rendered, interactive* page — focusing
elements and reading geometry that only exists at runtime. 2.4.11
(Focus Not Obscured) is fully deterministic (no model): focus each
element and check whether a position:fixed/sticky overlay covers it.
"""

from audit.analyzer.focus.base import RULE_FOCUS_OBSCURED, FocusFinding
from audit.analyzer.focus.probe import FocusProbe

__all__ = ["RULE_FOCUS_OBSCURED", "FocusFinding", "FocusProbe"]
