"""Concrete per-criterion semantic analyzers.

One class per WCAG SC. Each class implements the
:class:`audit.analyzer.semantic.base.SemanticAnalyzer` protocol and is
registered in :mod:`audit.analyzer.semantic.registry`.

Phase 9.1 ships SC 2.4.4 only. Phases 9.2+ add the rest of the
wave-1 SCs (see :doc:`PLAN.md`).
"""

from audit.analyzer.semantic.analyzers.sc_2_4_4 import (
    LinkPurposeInContextAnalyzer,
)

__all__ = ["LinkPurposeInContextAnalyzer"]
