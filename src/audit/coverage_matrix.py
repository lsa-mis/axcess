"""WCAG 2.2 A/AA coverage matrix — loader + summary.

The data lives in ``rules/wcag_coverage.yaml`` (the authoritative, honest
source of truth for which success criteria Axcess checks automatically,
AI-assists, or leaves to manual testing). This module loads + validates it
and exposes a small typed surface that the audit report, the ``/api/tracking``
endpoint, and the landing-page generator all read from — so the
"what's covered / what needs manual testing" story is told from ONE place.

Keep it honest: a criterion is only ``automated`` when a deterministic
pipeline catches essentially all of its testable failures. Everything else is
``partial`` (mechanical failures only), ``ai-assisted`` (model flags leads a
human confirms), or ``manual`` (no automated coverage).
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from importlib import resources

import yaml

_RULES_PACKAGE = "audit.rules"
_MATRIX_FILE = "wcag_coverage.yaml"

# The four honesty buckets, ordered most → least automated for display.
METHODS: tuple[str, ...] = ("automated", "partial", "ai-assisted", "manual")
PIPELINES: tuple[str, ...] = ("axe", "keyboard", "responsive", "focus", "image", "semantic")
LEVELS: tuple[str, ...] = ("A", "AA")

# Human-facing one-liners for each method (used in report + UI legends).
METHOD_LABELS: dict[str, str] = {
    "automated": "Automated",
    "partial": "Partly automated",
    "ai-assisted": "AI-assisted",
    "manual": "Manual only",
}
METHOD_BLURB: dict[str, str] = {
    "automated": "A deterministic pipeline catches essentially all testable failures.",
    "partial": "Automated checks catch the mechanical failures; the rest needs a human.",
    "ai-assisted": "A local model flags candidates — a human confirms before counting them.",
    "manual": "No automated detection — a human must test this criterion.",
}


@dataclass(frozen=True)
class Criterion:
    """One WCAG 2.2 A/AA success criterion and how Axcess covers it."""

    sc: str  # dotted number, e.g. "2.4.6"
    name: str
    level: str  # "A" | "AA"
    method: str  # one of METHODS
    pipelines: tuple[str, ...]  # which pipelines touch it ([] if manual)
    confidence: str  # "high" | "medium" | "low" | "n/a"
    automated_check: str  # what the tool does automatically ("" if none)
    manual_check: str  # what a human must still verify (always present)

    @property
    def is_covered(self) -> bool:
        """True if any Axcess pipeline contributes to this criterion."""
        return self.method != "manual"

    @property
    def needs_manual(self) -> bool:
        """True if a human must still test something for this criterion.

        Almost always true — even ``automated`` criteria leave a residual
        judgement — which is the whole point of the transparency model.
        """
        return bool(self.manual_check.strip())


@dataclass(frozen=True)
class CoverageSummary:
    """Roll-up counts for headlines + legends."""

    total: int
    by_method: dict[str, int]
    by_level: dict[str, dict[str, int]]  # level -> method -> count

    @property
    def covered(self) -> int:
        """Criteria with any automated/AI contribution (not manual-only)."""
        return self.total - self.by_method.get("manual", 0)

    @property
    def manual_only(self) -> int:
        return self.by_method.get("manual", 0)


class CoverageMatrixError(RuntimeError):
    """Raised when the YAML is missing, malformed, or fails validation."""


@lru_cache(maxsize=1)
def load_matrix() -> tuple[Criterion, ...]:
    """Load + validate the matrix once. Raises on any inconsistency.

    Validation is strict on purpose: a typo in an SC number or an invalid
    method would silently corrupt every coverage surface, so we fail loud at
    import/first-use rather than render a wrong conformance picture.
    """
    try:
        text = (resources.files(_RULES_PACKAGE) / _MATRIX_FILE).read_text(encoding="utf-8")
        data = yaml.safe_load(text) or {}
    except (FileNotFoundError, yaml.YAMLError) as exc:  # pragma: no cover - config error
        raise CoverageMatrixError(f"cannot read {_MATRIX_FILE}: {exc}") from exc

    raw = data.get("criteria")
    if not isinstance(raw, list) or not raw:
        raise CoverageMatrixError("wcag_coverage.yaml has no 'criteria' list")

    out: list[Criterion] = []
    seen: set[str] = set()
    for i, row in enumerate(raw):
        if not isinstance(row, dict):
            raise CoverageMatrixError(f"criteria[{i}] is not a mapping")
        sc = str(row.get("sc", "")).strip()
        if not sc:
            raise CoverageMatrixError(f"criteria[{i}] is missing 'sc'")
        if sc in seen:
            raise CoverageMatrixError(f"duplicate criterion {sc}")
        seen.add(sc)

        method = str(row.get("method", "")).strip()
        if method not in METHODS:
            raise CoverageMatrixError(f"{sc}: invalid method {method!r} (want one of {METHODS})")
        level = str(row.get("level", "")).strip()
        if level not in LEVELS:
            raise CoverageMatrixError(f"{sc}: invalid level {level!r}")

        pipelines = tuple(str(p).strip() for p in (row.get("pipelines") or ()))
        bad = [p for p in pipelines if p not in PIPELINES]
        if bad:
            raise CoverageMatrixError(f"{sc}: unknown pipeline(s) {bad}")
        # Honesty guards: manual ⇒ no pipelines; non-manual ⇒ at least one.
        if method == "manual" and pipelines:
            raise CoverageMatrixError(f"{sc}: method 'manual' must have no pipelines")
        if method != "manual" and not pipelines:
            raise CoverageMatrixError(f"{sc}: method {method!r} requires ≥1 pipeline")

        manual_check = str(row.get("manual_check", "")).strip()
        if not manual_check:
            raise CoverageMatrixError(f"{sc}: manual_check is required (the transparency promise)")

        out.append(
            Criterion(
                sc=sc,
                name=str(row.get("name", "")).strip(),
                level=level,
                method=method,
                pipelines=pipelines,
                confidence=str(row.get("confidence", "n/a")).strip() or "n/a",
                automated_check=str(row.get("automated_check", "")).strip(),
                manual_check=manual_check,
            )
        )

    # Stable WCAG order (1.1.1 < 1.4.10 < 2.1.2): sort by numeric tuple.
    out.sort(key=lambda c: tuple(int(p) for p in c.sc.split(".")))
    return tuple(out)


def by_sc(sc: str) -> Criterion | None:
    """Look up one criterion by dotted number, or None."""
    for c in load_matrix():
        if c.sc == sc:
            return c
    return None


def summary() -> CoverageSummary:
    """Counts by method and by level for headlines + legends."""
    crit = load_matrix()
    by_method = dict.fromkeys(METHODS, 0)
    by_level: dict[str, dict[str, int]] = {lvl: dict.fromkeys(METHODS, 0) for lvl in LEVELS}
    for c in crit:
        by_method[c.method] += 1
        by_level[c.level][c.method] += 1
    return CoverageSummary(total=len(crit), by_method=by_method, by_level=by_level)
