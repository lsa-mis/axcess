"""Axe-core runner — full WCAG 2.x AA scan against an already-rendered page.

This module is the **second analyzer** in the codebase (after `ocr/` and
`vlm/` which feed the WCAG 1.4.5 image-of-text pipeline). It runs at a
different layer: instead of analyzing a *blob* (an image), it analyzes
the *DOM* of a page that Playwright already rendered. So it sits next
to the JS fetcher, not the VLM.

Why axe-core specifically:

* It's a Deque-maintained, open-source library that codifies most of the
  WCAG 2.x AA criteria that can be checked from the DOM alone. It
  catches the obvious-but-tedious failures — color contrast, missing
  form labels, ARIA misuse — that human auditors burn hours on.
* We already bundle ``axe.min.js`` (553 KB, served at
  ``/static/axe.min.js``) for our own UI's in-test baseline scan. Same
  bundle, used on the user's site instead of ours.

Important scope caveats — surface these in the UI:

* Axe auto-detects roughly **30-40% of WCAG 2.x AA SCs**. The remainder
  (SC 1.1.1 *meaningful* alt text, SC 2.4.6 *descriptive* headings,
  SC 3.3.2 *clear* labels, etc.) need human judgment. A clean axe scan
  is necessary, not sufficient.
* The product's existing WCAG 1.4.5 pipeline (image-of-text) catches
  things axe can't — axe flags ``image-alt`` (missing) but never
  "this image *contains text* and the alt is decorative." The two
  passes are complementary, not redundant.

Usage::

    from playwright.async_api import Page
    from audit.analyzer.axe import AxeAnalyzer, AxeViolation

    analyzer = AxeAnalyzer.from_bundled()
    violations: list[AxeViolation] = await analyzer.run(page, level="AA")
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from playwright.async_api import Page

log = logging.getLogger(__name__)


# Path to the axe-core bundle inside the repo. The web UI serves the same
# file at /static/axe.min.js — we just read it off disk for crawl-time
# injection so we don't depend on a running web server.
DEFAULT_AXE_BUNDLE = (
    Path(__file__).resolve().parents[1] / "web" / "static" / "axe.min.js"
)


Level = Literal["A", "AA", "AAA"]


# Axe tag → WCAG SC mapping. Axe annotates each rule with one or more
# tags like ``wcag2a``, ``wcag2aa``, ``wcag143``, ``wcag22aa``, etc. The
# ``wcagNNN`` tags encode the success criterion: ``wcag143`` = SC 1.4.3.
# We translate that back to dotted notation for human consumption.
#
# This is intentionally a table, not parsing logic. Axe occasionally
# coins a non-numeric tag (``EN-301-549``, ``ACT``, ``section508``) that
# we want to ignore. Explicit list = explicit policy.
_LEVEL_TAGS: dict[Level, frozenset[str]] = {
    "A": frozenset(
        # WCAG 2.0/2.1/2.2 Level A
        ["wcag2a", "wcag21a", "wcag22a"]
    ),
    "AA": frozenset(
        # Each higher level inherits the lower one's tag set.
        ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22a", "wcag22aa"]
    ),
    "AAA": frozenset(
        [
            "wcag2a",
            "wcag2aa",
            "wcag2aaa",
            "wcag21a",
            "wcag21aa",
            "wcag22a",
            "wcag22aa",
        ]
    ),
}


def tags_for_level(level: Level) -> list[str]:
    """Axe tag list to pass into ``axe.run`` for a given WCAG level.

    The list always includes ``best-practice`` — axe's own recommended
    rules that don't map cleanly to a single SC but catch real bugs
    (e.g. ``region`` — top-level content not in a landmark). Best-practice
    findings are tagged ``best-practice`` and we surface them with
    ``wcag_level = None`` in the DB so the user can filter them out.
    """
    return sorted(_LEVEL_TAGS[level] | {"best-practice"})


def _extract_wcag_scs(tags: list[str]) -> tuple[str | None, str | None, Level | None]:
    """Pull WCAG SC dotted strings out of axe's tag list.

    Returns ``(primary_sc, all_scs_csv, level)``. Picks the lowest-numbered
    SC as primary (so ``["wcag143","wcag146"]`` → primary ``"1.4.3"``)
    because the lower SC is usually the more universally-applicable one
    (1.4.3 is AA, 1.4.6 is AAA — fix the AA bar first).
    """
    scs: list[str] = []
    levels: set[Level] = set()
    for tag in tags:
        if not tag.startswith("wcag"):
            continue
        rest = tag.removeprefix("wcag")
        # Level tags like wcag2a, wcag21aa, wcag22aaa — distinguish from
        # SC tags like wcag143 by checking whether the suffix is purely
        # digits (SC) vs has letters (level).
        if not rest or not rest[0].isdigit():
            continue
        # Pull out the level suffix if present
        if rest.endswith("aaa"):
            levels.add("AAA")
            continue
        if rest.endswith("aa"):
            levels.add("AA")
            continue
        if rest.endswith("a"):
            levels.add("A")
            continue
        # Pure digits = SC like "143" → "1.4.3" or "1411" → "1.4.11"
        if rest.isdigit():
            sc = _digits_to_sc(rest)
            if sc:
                scs.append(sc)
    primary = sorted(scs, key=_sc_sort_key)[0] if scs else None
    csv = ",".join(sorted(set(scs), key=_sc_sort_key)) if scs else None
    # Pick the most strict level the rule maps to: AAA > AA > A.
    level: Level | None = (
        "AAA" if "AAA" in levels else "AA" if "AA" in levels else "A" if "A" in levels else None
    )
    return primary, csv, level


def _digits_to_sc(digits: str) -> str | None:
    """Convert axe's compact SC digits to dotted form.

    Examples:
        ``"143"`` → ``"1.4.3"``
        ``"1411"`` → ``"1.4.11"`` (the 1.4.11 non-text contrast SC)
        ``"2411"`` → ``"2.4.11"``

    Axe's scheme: first two digits are the principle and guideline
    (one digit each). Everything after is the success criterion number,
    which can be 1 or 2 digits. We disambiguate by length: 3-digit ⇒
    1-digit SC; 4-digit ⇒ 2-digit SC.
    """
    if len(digits) < 3 or len(digits) > 4 or not digits.isdigit():
        return None
    principle = digits[0]
    guideline = digits[1]
    sc = digits[2:]  # remaining 1 or 2 digits
    if not (principle and guideline and sc):
        return None
    return f"{principle}.{guideline}.{sc}"


def _sc_sort_key(sc: str) -> tuple[int, int, int]:
    """Numeric sort for SC strings — ``"1.4.11"`` should follow ``"1.4.3"``."""
    parts = sc.split(".")
    if len(parts) != 3:
        return (99, 99, 99)
    try:
        return (int(parts[0]), int(parts[1]), int(parts[2]))
    except ValueError:
        return (99, 99, 99)


@dataclass(slots=True, frozen=True)
class AxeViolation:
    """One axe rule failure against one DOM node.

    Multiple nodes on the same page failing the same rule become multiple
    ``AxeViolation`` instances — axe groups them under one rule in its
    raw output, but we flatten because the UI's natural unit is "one
    finding = one thing to fix in one place."
    """

    rule_id: str
    impact: str | None  # critical | serious | moderate | minor | None
    help: str
    help_url: str
    wcag_sc: str | None
    wcag_scs: str | None
    wcag_level: Level | None
    target_selector: str
    failure_summary: str
    html_snippet: str

    @property
    def target_hash(self) -> str:
        """Stable hash for the (rule, target, snippet) tuple — dedupe key."""
        h = hashlib.sha256()
        h.update(self.rule_id.encode("utf-8", errors="replace"))
        h.update(b"\x00")
        h.update(self.target_selector.encode("utf-8", errors="replace"))
        h.update(b"\x00")
        h.update(self.html_snippet.encode("utf-8", errors="replace"))
        return h.hexdigest()


@dataclass(slots=True)
class AxeAnalyzer:
    """Reusable axe-core runner. Construct once per crawl, reuse per page."""

    axe_source: str
    _injected: bool = field(default=False, init=False)

    @classmethod
    def from_bundled(cls, path: Path | None = None) -> AxeAnalyzer:
        """Load the axe-core bundle from disk and return a ready analyzer."""
        bundle = path or DEFAULT_AXE_BUNDLE
        if not bundle.is_file():
            raise FileNotFoundError(
                f"axe bundle not found at {bundle} — run `make setup` to fetch it."
            )
        return cls(axe_source=bundle.read_text(encoding="utf-8"))

    async def run(self, page: Page, level: Level = "AA") -> list[AxeViolation]:
        """Inject axe into ``page`` and return the flattened violations.

        ``level`` controls the tag pack: ``"AA"`` (default) catches every
        rule axe knows for WCAG 2.0/2.1/2.2 Level A or AA, plus axe's
        ``best-practice`` set. ``"AAA"`` adds the AAA rules; ``"A"``
        narrows to Level A only.
        """
        await page.add_script_tag(content=self.axe_source)
        tags = tags_for_level(level)
        # axe.run returns the full result object; we only keep `violations`.
        # The `runOnly: {type: 'tag', values: tags}` filter is what gives
        # us the WCAG-tagged subset of axe's rule set.
        try:
            raw: list[dict[str, Any]] = await page.evaluate(
                """async (tags) => {
                    const r = await window.axe.run(document, {
                        runOnly: { type: 'tag', values: tags },
                    });
                    return r.violations;
                }""",
                tags,
            )
        except Exception as exc:
            # Don't kill the crawl on an axe failure — log and return empty.
            log.warning("axe.run failed on page: %s", exc)
            return []
        return list(_flatten(raw))


def _flatten(raw_violations: list[dict[str, Any]]) -> Iterator[AxeViolation]:
    """Expand axe's per-rule grouping into one row per (rule, node)."""
    for v in raw_violations:
        rule_id = str(v.get("id", "?"))
        impact = v.get("impact")
        if impact is not None and impact not in {"critical", "serious", "moderate", "minor"}:
            impact = None
        help_text = str(v.get("help", rule_id))
        help_url = str(v.get("helpUrl", ""))
        tags = [str(t) for t in v.get("tags", [])]
        wcag_sc, wcag_scs, wcag_level = _extract_wcag_scs(tags)
        nodes = v.get("nodes") or []
        for node in nodes:
            target = node.get("target") or []
            # axe target is a list of CSS selectors (one per iframe hop).
            # Most of our pages aren't iframed, so this is usually a
            # single-element list; we join with " > " when it isn't.
            target_selector = (
                " > ".join(str(t) for t in target) if target else "(unknown)"
            )
            failure_summary = str(node.get("failureSummary", "") or "")
            html_snippet = str(node.get("html", "") or "")[:4000]
            yield AxeViolation(
                rule_id=rule_id,
                impact=impact,
                help=help_text,
                help_url=help_url,
                wcag_sc=wcag_sc,
                wcag_scs=wcag_scs,
                wcag_level=wcag_level,
                target_selector=target_selector,
                failure_summary=failure_summary,
                html_snippet=html_snippet,
            )


def to_json(violations: list[AxeViolation]) -> str:
    """Serialize a list of violations for logging / debug dumps."""
    return json.dumps(
        [
            {
                "rule_id": v.rule_id,
                "impact": v.impact,
                "wcag_sc": v.wcag_sc,
                "wcag_level": v.wcag_level,
                "target_selector": v.target_selector,
            }
            for v in violations
        ],
        indent=2,
    )
