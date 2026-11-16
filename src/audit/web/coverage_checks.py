"""What Axcess checks: the Coverage page's per-criterion view, built from the code.

Everything here describes Axcess itself, never a scan, so it is the same for
every site and holds no report data:

* the coverage list (``rules/wcag_coverage.yaml`` via :mod:`audit.coverage_matrix`),
  which is WCAG 2.2; WCAG 2.1 is derived from it (the six 2.2 additions
  dropped, 4.1.1 Parsing added back as "no longer needed");
* the axe-core rules a scan runs, from ``rules/axe_rules.json``, which
  ``scripts/build_axe_rule_catalog.mjs`` writes from the bundled
  ``web/static/axe.min.js`` (a unit test pins the two versions together);
* plain wording for each criterion, for the interface (``docs/plain-language.md``);
* two published studies, labelled as such wherever they are shown: Deque's
  "Automated Accessibility Coverage Report" (table 1) for how often each kind
  of problem occurs and how much axe-core finds, and the WebAIM Million 2026
  for the most common problems on home pages.

The "other checks" figures in :data:`STUDY` are judgments from what each check's
code does, not measurements; the page says so beside them.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from importlib import resources
from typing import Literal

from pydantic import BaseModel

from audit import coverage_matrix
from audit.wcag_version import DEFAULT_WCAG_VERSION, WcagVersion

Method = Literal["automated", "partial", "ai-assisted", "manual", "not_needed"]
METHOD_ORDER: tuple[Method, ...] = ("automated", "partial", "ai-assisted", "manual", "not_needed")

#: The version a scan uses unless its settings say otherwise.
SCAN_DEFAULT_VERSION: WcagVersion = DEFAULT_WCAG_VERSION

#: Criteria WCAG 2.2 added; a WCAG 2.1 view leaves them out.
WCAG22_ADDED = frozenset({"2.4.11", "2.5.7", "2.5.8", "3.2.6", "3.3.7", "3.3.8"})

#: Assumed share of the problems a check is built for that it really finds,
#: for the "other checks" estimate. The lowest recall Axcess's own detector
#: benchmark accepts (``make quality-gate``).
OTHER_CHECKS_HIT_RATE = 0.8

STUDY_SOURCE_URL = "https://www.deque.com/automated-accessibility-coverage-report/"
COMMON_SOURCE_URL = "https://webaim.org/projects/million/"

PRINCIPLES = {"1": "Perceivable", "2": "Operable", "3": "Understandable", "4": "Robust"}
GUIDELINES = {
    "1.1": "Text Alternatives",
    "1.2": "Time-based Media",
    "1.3": "Adaptable",
    "1.4": "Distinguishable",
    "2.1": "Keyboard Accessible",
    "2.2": "Enough Time",
    "2.3": "Seizures and Physical Reactions",
    "2.4": "Navigable",
    "2.5": "Input Modalities",
    "3.1": "Readable",
    "3.2": "Predictable",
    "3.3": "Input Assistance",
    "4.1": "Compatible",
}

# Plain wording for each criterion: (what Axcess does, what you still check).
# "" for what Axcess does means it does not check the criterion. Kept short on
# purpose (docs/plain-language.md, W3C COGA "Making Content Usable"); the
# coverage list's own developer wording is sent alongside as ``technical``.
PLAIN: dict[str, tuple[str, str]] = {
    "1.1.1": (
        "Finds images and icons with no alt text. Flags pictures of text.",
        "Alt text says what each image means. Decorative images are hidden.",
    ),
    "1.2.1": (
        "AI looks for a transcript near each audio player.",
        "Transcripts match the audio. Silent video has a description.",
    ),
    "1.2.2": ("Finds videos with no captions file.", "Captions are present, correct and in time."),
    "1.2.3": ("", "Each video has an audio description or a text version."),
    "1.2.4": ("", "Live video has live captions."),
    "1.2.5": ("", "Each video has an audio description."),
    "1.3.1": (
        "Finds lists, tables and headings built wrongly in the page code.",
        "Anything shown by layout, such as grouped fields, is also in the page code.",
    ),
    "1.3.2": (
        "AI compares the on-screen order with the page-code order.",
        "The order makes sense with a screen reader.",
    ),
    "1.3.3": ("", "Instructions don't rely only on shape, size, place or sound."),
    "1.3.4": ("", "The page works in both portrait and landscape."),
    "1.3.5": (
        "Checks autocomplete values are valid.",
        "Fields for the user's own details have autocomplete.",
    ),
    "1.4.1": ("Finds links shown only by colour.", "Colour is never the only way to show meaning."),
    "1.4.2": (
        "Finds sound that plays on its own over 3 seconds with no control.",
        "All sound that plays on its own can be paused or muted.",
    ),
    "1.4.3": ("Measures text contrast.", "Text over pictures, in images, and on hover or focus."),
    "1.4.4": (
        "Finds text cut off at a 200% zoom size.",
        "Nothing is lost at 200% zoom in your browsers.",
    ),
    "1.4.5": (
        "Reads text in images. AI judges if it is a picture of text.",
        "Flagged images aren't logos or allowed exceptions.",
    ),
    "1.4.10": (
        "Finds pages that scroll sideways at 320 pixels wide.",
        "Nothing is lost or hard to use at that width.",
    ),
    "1.4.11": ("", "Field borders, focus outlines and key graphics have enough contrast."),
    "1.4.12": ("Finds text cut off when spacing is increased.", "No text overlaps or is cut off."),
    "1.4.13": ("", "Hover and focus pop-ups can be closed and stay open."),
    "2.1.1": (
        "Finds some controls the keyboard can't reach.",
        "Every control works with the keyboard alone.",
    ),
    "2.1.2": (
        "Finds places where Tab and Shift+Tab can't move focus.",
        "Each lead, and parts that open after a click.",
    ),
    "2.1.4": ("", "One-key shortcuts can be turned off or changed."),
    "2.2.1": (
        "Finds pages that reload or redirect on a timer.",
        "Every time limit can be turned off or extended.",
    ),
    "2.2.2": (
        "Finds video that plays over 5 seconds with no pause, and scrolling text.",
        "Carousels and animations can be paused.",
    ),
    "2.3.1": ("", "Nothing flashes more than three times a second."),
    "2.4.1": (
        "Checks for a skip link, landmarks or headings.",
        "The skip link works with the keyboard.",
    ),
    "2.4.2": ("Checks every page has a title.", "Each title says what the page is."),
    "2.4.3": ("Finds elements that change the normal Tab order.", "The Tab order makes sense."),
    "2.4.4": (
        "Finds links with no text. AI judges unclear link text.",
        "AI leads such as “Read more” and icon links.",
    ),
    "2.4.5": ("", "There are two ways to find pages, such as a menu and search."),
    "2.4.6": (
        "Finds empty headings. AI judges unclear headings.",
        "AI leads, and that form labels are clear.",
    ),
    "2.4.7": ("", "You can always see where keyboard focus is."),
    "2.4.11": (
        "Finds controls hidden behind sticky bars when focused.",
        "Controls that are partly hidden.",
    ),
    "2.5.1": ("", "Swipes and pinches have a single-tap way too."),
    "2.5.2": ("", "Actions happen on release, so they can be cancelled."),
    "2.5.3": ("", "Each control's spoken name includes its visible text."),
    "2.5.4": ("", "Anything done by shaking or tilting has a button too."),
    "2.5.7": ("", "Anything you can drag also works with taps."),
    "2.5.8": (
        "Finds targets smaller than 24 by 24 pixels.",
        "The allowed exceptions, such as links in a sentence.",
    ),
    "3.1.1": ("Checks the page states its language.", "The stated language is right."),
    "3.1.2": (
        "Checks language codes on parts of the page are valid.",
        "Text in another language has a language code.",
    ),
    "3.2.1": ("", "Focus alone never opens a new page or form."),
    "3.2.2": ("", "Changing a setting never does something big without warning."),
    "3.2.3": ("", "Repeated menus stay in the same order."),
    "3.2.4": ("", "Things that do the same job have the same name."),
    "3.2.6": ("", "Help is in the same place on every page."),
    # The form error check runs here but is not yet proved on enough real
    # forms to count (AGENTS.md, "Building a check: real pages first"), so
    # the criterion stays "You check" and says what the check does.
    "3.3.1": (
        "A trial check sends each form empty and flags fields marked in error"
        " with no words saying what is wrong. Not yet proven, so it does not count.",
        "Form errors are described in words.",
    ),
    "3.3.2": (
        "Checks fields have labels. AI judges unclear labels.",
        "AI leads, and real form submissions.",
    ),
    "3.3.3": ("", "Error messages say how to fix the mistake."),
    "3.3.4": ("", "Legal, money and data forms can be reviewed or undone."),
    "3.3.7": ("", "Multi-step forms don't ask for the same thing twice."),
    "3.3.8": ("", "Sign-in has no memory test or puzzle."),
    "4.1.2": (
        "Checks controls have a name and a role.",
        "Custom controls announce changes, such as open or selected.",
    ),
    "4.1.3": ("", "Updates like “Added to cart” are announced."),
}

_APG = "https://www.w3.org/WAI/ARIA/apg/"
_APG_PAGES: dict[str, tuple[str, str]] = {
    "names": ("Providing Accessible Names and Descriptions", "practices/names-and-descriptions/"),
    "keyboard": ("Developing a Keyboard Interface", "practices/keyboard-interface/"),
    "landmarks": ("Landmark Regions", "practices/landmark-regions/"),
    "structure": ("Structural Roles", "practices/structural-roles/"),
    "tables": ("Grid and Table Properties", "practices/grid-and-table-properties/"),
    "hiding": ("Hiding Semantics with the presentation Role", "practices/hiding-semantics/"),
    "patterns": ("Patterns", "patterns/"),
    "dialog": ("Dialog (Modal) Pattern", "patterns/dialog-modal/"),
    "alert": ("Alert Pattern", "patterns/alert/"),
    "tooltip": ("Tooltip Pattern", "patterns/tooltip/"),
    "carousel": ("Carousel Pattern", "patterns/carousel/"),
}
#: WAI-ARIA Authoring Practices Guide pages for the criteria they clearly help
#: with. The APG is organised by widget, not by criterion, so most criteria
#: have none; a criterion is listed only where the page is about meeting it.
APG_GUIDANCE: dict[str, tuple[str, ...]] = {
    "1.1.1": ("names", "hiding"),
    "1.3.1": ("structure", "landmarks", "tables"),
    "1.4.13": ("tooltip",),
    "2.1.1": ("keyboard", "patterns"),
    "2.1.2": ("keyboard", "dialog"),
    "2.2.2": ("carousel",),
    "2.4.1": ("landmarks",),
    "2.4.3": ("keyboard", "dialog"),
    "2.4.6": ("names",),
    "2.4.7": ("keyboard",),
    "2.5.3": ("names",),
    "3.3.2": ("names",),
    "4.1.2": ("patterns", "names"),
    "4.1.3": ("alert",),
}

StudyCheck = Literal[
    "click_through", "image", "focus", "keyboard", "visual", "semantic", "responsive"
]


@dataclass(frozen=True)
class StudyRow:
    """One row of Deque's table 1, with Axcess's other checks beside it."""

    sc: str  # WCAG number, or "other" for the remainder
    share: float  # share of all audit issues, percent
    axe_rate: float  # share of those axe-core found, percent
    reach: float  # share of the rest Axcess's other checks are built to find, percent
    checks: tuple[StudyCheck, ...]


#: Deque's table 1, less 4.1.1 Parsing (Axcess does not test it, and WCAG 2.2
#: removed it), so every share below is of the remaining issues.
STUDY: tuple[StudyRow, ...] = (
    StudyRow("1.4.3", 30.08, 83.11, 15, ("click_through",)),
    StudyRow("4.1.2", 16.37, 54.42, 15, ("click_through",)),
    StudyRow("1.3.1", 12.33, 45.17, 10, ("click_through",)),
    StudyRow("1.1.1", 8.04, 67.57, 25, ("image", "click_through")),
    StudyRow("2.4.3", 3.24, 0.0, 10, ("focus",)),
    StudyRow("2.1.1", 3.19, 2.49, 5, ("keyboard",)),
    StudyRow("2.4.7", 2.48, 0.0, 0, ()),
    StudyRow("1.4.11", 1.54, 0.0, 0, ()),
    StudyRow("1.4.1", 1.26, 12.17, 0, ()),
    StudyRow("1.3.2", 1.12, 0.0, 30, ("visual",)),
    StudyRow("3.3.2", 0.86, 20.42, 40, ("semantic",)),
    StudyRow("2.4.1", 0.86, 79.0, 0, ()),
    StudyRow("2.4.2", 0.75, 11.26, 0, ()),
    StudyRow("3.1.1", 0.74, 91.81, 0, ()),
    StudyRow("other", 5.46, 1.25, 25, ("responsive", "keyboard", "visual", "semantic", "image")),
)
STUDY_SHARE_TOTAL = sum(row.share for row in STUDY)

#: The WebAIM Million 2026: share of home pages with each detected problem.
COMMON_PROBLEMS: tuple[tuple[str, float, str, str], ...] = (
    ("Low-contrast text", 83.9, "color-contrast", "1.4.3"),
    ("Images with no alt text", 53.1, "image-alt", "1.1.1"),
    ("Form fields with no label", 51.0, "label", "4.1.2"),
    ("Links with no text", 46.3, "link-name", "2.4.4"),
    ("Buttons with no text", 30.6, "button-name", "4.1.2"),
    ("Page language not set", 13.5, "html-has-lang", "3.1.1"),
)


# --- Response models ---------------------------------------------------


class StudyFigures(BaseModel):
    """One study row as shares of all problems (4.1.1 left out), each 0-1."""

    sc: str
    share: float
    rule_check: float  # of this criterion's problems, the share axe-core finds
    other_checks: float  # of them, the share Axcess's other checks add (an estimate)
    checks: list[StudyCheck]


class Guidance(BaseModel):
    title: str
    url: str


class RuleInfo(BaseModel):
    """One axe-core rule a scan runs for a criterion."""

    id: str
    help: str
    description: str
    url: str


class CheckCriterion(BaseModel):
    sc: str
    name: str
    understanding_url: str  # the W3C's "Understanding" page for this version
    apg: list[Guidance]  # WAI-ARIA Authoring Practices pages, where one helps
    level: str
    principle: str
    guideline: str
    method: Method
    checks: list[str]  # page_a11y_findings pipeline names
    rules: list[RuleInfo]  # axe-core rules the scan runs for this criterion
    confidence: str
    does: str
    you: str
    technical: str  # the coverage list's own wording of what the check does ("" if none)
    study: StudyFigures | None


class CommonProblem(BaseModel):
    label: str
    share_of_sites: float  # 0-1
    rule: str
    sc: str


class CoverageChecksResponse(BaseModel):
    wcag_version: WcagVersion
    scan_default_version: WcagVersion
    axe_version: str
    criteria: list[CheckCriterion]
    study: list[StudyFigures]  # every row, "other" included, for the whole-page totals
    study_source_url: str
    other_checks_hit_rate: float
    common_problems: list[CommonProblem]
    common_source_url: str


# --- Building it -------------------------------------------------------


@dataclass(frozen=True)
class AxeRule:
    id: str
    help: str
    description: str  # what the rule checks, in axe-core's own words
    help_url: str  # Deque's page for the rule
    category: str  # axe-core's own kind of problem, from its ``cat.*`` tag
    criteria: tuple[str, ...]
    tags: frozenset[str]


@dataclass(frozen=True)
class AxeCatalog:
    version: str
    rules: tuple[AxeRule, ...]

    def by_id(self) -> dict[str, AxeRule]:
        return {rule.id: rule for rule in self.rules}


@lru_cache(maxsize=1)
def axe_catalog() -> AxeCatalog:
    """The axe-core rule list the bundle ships (``rules/axe_rules.json``)."""
    text = (resources.files("audit.rules") / "axe_rules.json").read_text(encoding="utf-8")
    data = json.loads(text)
    return AxeCatalog(
        version=str(data["axe_version"]),
        rules=tuple(
            AxeRule(
                id=str(r["id"]),
                help=str(r["help"]),
                description=str(r["description"]),
                help_url=str(r["help_url"]),
                category=str(r["category"]),
                criteria=tuple(str(sc) for sc in r["criteria"]),
                tags=frozenset(str(t) for t in r["tags"]),
            )
            for r in data["rules"]
        ),
    )


_VERSION_TAGS: dict[WcagVersion, frozenset[str]] = {
    "2.1": frozenset({"wcag2a", "wcag2aa", "wcag21a", "wcag21aa"}),
    "2.2": frozenset({"wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22a", "wcag22aa"}),
}


def rules_by_criterion(version: WcagVersion) -> dict[str, list[str]]:
    """Rule ids a Level AA scan of ``version`` runs, by the criteria each is tagged with.

    Experimental and deprecated rules are left out: axe-core does not run them
    unless asked, and Axcess never asks.
    """
    out: dict[str, list[str]] = {}
    for rule in axe_catalog().rules:
        tags = rule.tags
        if tags & {"experimental", "deprecated"} or not tags & _VERSION_TAGS[version]:
            continue
        for sc in rule.criteria:
            out.setdefault(sc, []).append(rule.id)
    return out


def understanding_url(name: str, version: WcagVersion) -> str:
    """The W3C's "Understanding WCAG" page for a criterion, named as the W3C names it.

    "Contrast (Minimum)" -> .../WCAG21/Understanding/contrast-minimum.html
    """
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return f"https://www.w3.org/WAI/WCAG{version.replace('.', '')}/Understanding/{slug}.html"


def apg_guidance(sc: str) -> list[Guidance]:
    return [
        Guidance(title=_APG_PAGES[key][0], url=_APG + _APG_PAGES[key][1])
        for key in APG_GUIDANCE.get(sc, ())
    ]


def study_figures(row: StudyRow) -> StudyFigures:
    rule_check = row.axe_rate / 100
    return StudyFigures(
        sc=row.sc,
        share=row.share / STUDY_SHARE_TOTAL,
        rule_check=rule_check,
        other_checks=(1 - rule_check) * row.reach / 100 * OTHER_CHECKS_HIT_RATE,
        checks=list(row.checks),
    )


def coverage_checks(version: WcagVersion = SCAN_DEFAULT_VERSION) -> CoverageChecksResponse:
    """Every WCAG ``version`` Level A and AA criterion and how Axcess checks it."""
    rules = rules_by_criterion(version)
    catalog = axe_catalog().by_id()
    study = {row.sc: study_figures(row) for row in STUDY}
    criteria: list[CheckCriterion] = []
    for c in coverage_matrix.load_matrix():
        if version == "2.1" and c.sc in WCAG22_ADDED:
            continue
        does, you = PLAIN[c.sc]
        criteria.append(
            CheckCriterion(
                sc=c.sc,
                name=c.name,
                understanding_url=understanding_url(c.name, version),
                apg=apg_guidance(c.sc),
                level=c.level,
                principle=PRINCIPLES[c.sc[0]],
                guideline=f"{c.sc.rsplit('.', 1)[0]} {GUIDELINES[c.sc.rsplit('.', 1)[0]]}",
                method=c.method,  # type: ignore[arg-type]  # validated by coverage_matrix
                checks=list(c.pipelines),
                rules=[
                    RuleInfo(id=r.id, help=r.help, description=r.description, url=r.help_url)
                    for rule_id in rules.get(c.sc, [])
                    for r in (catalog[rule_id],)
                ],
                confidence=c.confidence,
                does=does,
                you=you,
                technical=c.automated_check,
                study=study.get(c.sc),
            )
        )
    if version == "2.1":
        criteria.append(
            CheckCriterion(
                sc="4.1.1",
                name="Parsing",
                understanding_url=understanding_url("Parsing", version),
                apg=[],
                level="A",
                principle="Robust",
                guideline="4.1 Compatible",
                method="not_needed",
                checks=[],
                rules=[],
                confidence="n/a",
                does="",
                you="",
                technical="",
                study=None,
            )
        )
        criteria.sort(key=lambda row: tuple(int(part) for part in row.sc.split(".")))
    return CoverageChecksResponse(
        wcag_version=version,
        scan_default_version=SCAN_DEFAULT_VERSION,
        axe_version=axe_catalog().version,
        criteria=criteria,
        study=list(study.values()),
        study_source_url=STUDY_SOURCE_URL,
        other_checks_hit_rate=OTHER_CHECKS_HIT_RATE,
        common_problems=[
            CommonProblem(label=label, share_of_sites=pct / 100, rule=rule, sc=sc)
            for label, pct, rule, sc in COMMON_PROBLEMS
        ],
        common_source_url=COMMON_SOURCE_URL,
    )
