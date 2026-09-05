"""Responsive / zoom / text-spacing probe (SC 1.4.4, 1.4.10, 1.4.12).

Dynamic checks that need a live browser: resize the viewport to 320 px
and look for horizontal overflow (reflow), shrink to the standard 200 %
zoom proxy and look for clipped text, and inject the canonical WCAG
text-spacing override and look for clipping again. None of these are
possible from static HTML, and none are covered by axe-core.

Note: the "zoom-locked viewport meta" check (``user-scalable=no``)
deliberately does NOT live here, axe-core's ``meta-viewport`` rule
(tagged wcag144, in our default AA tag pack) already reports it, and
two pipelines reporting the same defect doubles the triage work.
"""

from audit.analyzer.responsive.base import ResponsiveFinding
from audit.analyzer.responsive.probe import ResponsiveProbe

__all__ = ["ResponsiveFinding", "ResponsiveProbe"]
