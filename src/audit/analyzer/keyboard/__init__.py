"""Dynamic keyboard-trap probe (WCAG SC 2.1.2 No Keyboard Trap).

Runs *inside* a live Playwright page after axe-core has finished, before
the page closes. The probe presses Tab in a loop while watching
``document.activeElement``; if focus gets stuck on a single element for
several presses, or if focus can't escape a modal via Escape, the probe
records a finding.

This is the GenA11y-paper-acknowledged "dynamic analysis" criterion:
static DOM/CSS reading can't tell you whether a keydown handler will
swallow the next Tab. Playwright is the only way.
"""

from audit.analyzer.keyboard.base import KeyboardTrap
from audit.analyzer.keyboard.probe import KeyboardProbe

__all__ = ["KeyboardProbe", "KeyboardTrap"]
