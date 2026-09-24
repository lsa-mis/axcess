#!/usr/bin/env python3
"""Generate the Axcess public site (``site/**/index.html``).

The site is written for people who are *not* engineers: accessibility leads,
content editors, managers, and IT reviewers deciding whether to use Axcess.

Every coverage number and every WCAG criterion card is rendered from the same
source of truth the product uses (``src/audit/rules/wcag_coverage.yaml`` via
``audit.coverage_matrix`` and ``audit.web.coverage_status``), so the public
site can never claim coverage the code does not have.

Run from the repo root::

    uv run python site/build.py

Pages are static HTML; ``assets/site.css`` and ``assets/site.js`` are shared.
Everything works without JavaScript.
"""

from __future__ import annotations

import html
import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"
sys.path.insert(0, str(ROOT / "src"))

BASE_URL = "https://lsa-mis.github.io/axcess/"
REPO = "https://github.com/lsa-mis/axcess"
RELEASES = f"{REPO}/releases"
LATEST_RELEASE = f"{RELEASES}/latest"
# Version-less asset names are uploaded by .github/workflows/desktop-build.yml
# so these links always fetch the newest build without a GitHub sign-in.
DOWNLOAD_MACOS = f"{LATEST_RELEASE}/download/Axcess-macOS-AppleSilicon.dmg"
DOWNLOAD_WINDOWS = f"{LATEST_RELEASE}/download/Axcess-Windows-x64-Setup.exe"
WHITEPAPER = f"{REPO}/blob/main/whitepaper/AXCESS-WHITE-PAPER.md"
DOCS = f"{REPO}/tree/main/docs"
PORTFOLIO = "https://reganmaharjan.com.np/"
# Pixel sizes of the diagram PNGs in site/assets/diagrams/ (copied from
# docs/images/diagrams/), so each <img> reserves its space before it loads.
DIAGRAM_SIZES = {
    "report-groups": (3200, 1800),
    "login-scan-flow": (3200, 1800),
    "privacy-boundary": (3200, 1800),
}
REPORT_GROUPS_ALT = (
    "Diagram of the three report groups. Barrier holds rule-engine failures from axe-core and Siteimprove Alfa, "
    "including problems found after clicking or after a configured search; confirm them on the page, fix, and rescan. "
    "Needs review holds browser checks, the keyboard trap check, motion checks, text in images whose alt text is "
    "missing or does not match, AI checks, and Alfa &quot;cannot tell&quot; results; a person tests and records a "
    "decision. Informational holds images whose alt text already matches and older records kept for history; no "
    "action is needed."
)


def e(s: object) -> str:
    return html.escape(str(s), quote=True)


# ---------------------------------------------------------------------------
# Site map
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Page:
    slug: str  # "" for the home page
    nav: str
    title: str
    description: str


PAGES: tuple[Page, ...] = (
    Page(
        "",
        "Home",
        "Axcess",
        "A free accessibility scanner that runs on your computer. Sign in yourself, including two-factor steps, and Axcess tests the pages behind the sign-in, opens menus and dialogs, and keeps the evidence on your machine.",
    ),
    Page(
        "how-it-works",
        "How it works",
        "How Axcess works",
        "Six plain-language steps from a web address to a verified fix, and what each Axcess check actually looks at.",
    ),
    Page(
        "coverage",
        "Coverage",
        "What Axcess checks",
        "What Axcess checks, which report group each result lands in, how it compares with Siteimprove and axe DevTools, and a searchable map of every WCAG 2.2 A and AA success criterion with what a person still needs to test.",
    ),
    Page(
        "who-its-for",
        "Who it's for",
        "Who Axcess is for",
        "Accessibility leads, the editors and developers who fix things, leadership, and IT reviewers: what each of them gets from Axcess.",
    ),
    Page(
        "privacy",
        "Privacy",
        "Privacy and trust",
        "What stays on your computer, what Axcess connects to, and how it scans sites behind a login without ever seeing your password.",
    ),
    Page(
        "get-started",
        "Get started",
        "Get started with Axcess",
        "Install the desktop preview or run from source, then complete your first scan and read your first report.",
    ),
    Page(
        "faq",
        "FAQ",
        "Questions and glossary",
        "Straight answers to common questions about Axcess, plus the plain-language glossary of the words you'll see in a report.",
    ),
    Page(
        "volume",
        "Coverage by volume",
        "Coverage by volume",
        "What completed Axcess scans actually produced, in aggregate: detected occurrences by WCAG criterion, coverage method, and check. A development sample, kept for reference and not linked from the site.",
    ),
    Page(
        "about",
        "About",
        "About Axcess",
        "Why Axcess exists, how it grew from a single problem into an evidence workbench, and where it is heading.",
    ),
)
BY_SLUG = {p.slug: p for p in PAGES}
NAV_ORDER = ("how-it-works", "coverage", "who-its-for", "privacy", "get-started", "faq")
JOURNEY = ("", "how-it-works", "coverage", "who-its-for", "privacy", "get-started", "faq", "about")


# ---------------------------------------------------------------------------
# Icons (inline SVG, decorative unless labelled)
# ---------------------------------------------------------------------------

_I = 'xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"'
ICONS = {
    "scope": f'<svg {_I}><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/><path d="M11 8v6M8 11h6"/></svg>',
    "eye": f'<svg {_I}><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12Z"/><circle cx="12" cy="12" r="3"/></svg>',
    "table": f'<svg {_I}><rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 10h18M9 4v16"/></svg>',
    "pin": f'<svg {_I}><path d="M12 21s7-6.2 7-11a7 7 0 0 0-14 0c0 4.8 7 11 7 11Z"/><circle cx="12" cy="10" r="2.5"/></svg>',
    "download": f'<svg {_I}><path d="M12 3v12m0 0 4-4m-4 4-4-4"/><path d="M4 17v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2"/></svg>',
    "refresh": f'<svg {_I}><path d="M21 12a9 9 0 1 1-2.6-6.4"/><path d="M21 3v6h-6"/></svg>',
    "lock": f'<svg {_I}><rect x="4" y="11" width="16" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/></svg>',
    "shield": f'<svg {_I}><path d="M12 3 4 6v6c0 5 3.5 8 8 9 4.5-1 8-4 8-9V6l-8-3Z"/><path d="m9 12 2 2 4-4"/></svg>',
    "cpu": f'<svg {_I}><rect x="6" y="6" width="12" height="12" rx="2"/><path d="M9 2v4M15 2v4M9 18v4M15 18v4M2 9h4M2 15h4M18 9h4M18 15h4"/></svg>',
    "person": f'<svg {_I}><circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/></svg>',
    "people": f'<svg {_I}><circle cx="9" cy="8" r="3.5"/><path d="M2 20a7 7 0 0 1 14 0"/><circle cx="17" cy="9" r="2.5"/><path d="M15.5 14.5A5 5 0 0 1 22 19"/></svg>',
    "chart": f'<svg {_I}><path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/></svg>',
    "server": f'<svg {_I}><rect x="3" y="4" width="18" height="6" rx="2"/><rect x="3" y="14" width="18" height="6" rx="2"/><path d="M7 7h.01M7 17h.01"/></svg>',
    "check": f'<svg {_I}><path d="m5 12 4 4L19 6"/></svg>',
    "info": f'<svg {_I}><circle cx="12" cy="12" r="9"/><path d="M12 8h.01M11 12h1v4h1"/></svg>',
    "warn": f'<svg {_I}><path d="M12 3 2 20h20L12 3Z"/><path d="M12 10v4M12 17h.01"/></svg>',
    "home": f'<svg {_I}><path d="m3 11 9-8 9 8"/><path d="M5 10v10h14V10"/></svg>',
    "doc": f'<svg {_I}><path d="M6 3h8l4 4v14H6z"/><path d="M14 3v4h4M9 12h6M9 16h6"/></svg>',
    "sheet": f'<svg {_I}><rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18M3 15h18M9 3v18"/></svg>',
    "keyboard": f'<svg {_I}><rect x="2" y="6" width="20" height="12" rx="2"/><path d="M6 10h.01M10 10h.01M14 10h.01M18 10h.01M8 14h8"/></svg>',
    "phone": f'<svg {_I}><rect x="7" y="2" width="10" height="20" rx="2"/><path d="M11 18h2"/></svg>',
    "image": f'<svg {_I}><rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="9" cy="10" r="2"/><path d="m21 16-5-5-8 8"/></svg>',
    "click": f'<svg {_I}><path d="m8 8 12 5-5 2-2 5z"/><path d="M4 4l2 2M4 10h2M10 4v2"/></svg>',
    "text": f'<svg {_I}><path d="M4 6h16M4 12h10M4 18h14"/></svg>',
    "play": f'<svg {_I}><rect x="3" y="4" width="18" height="16" rx="2"/><path d="m10 9 5 3-5 3z"/></svg>',
    "layers": f'<svg {_I}><path d="m12 3 9 5-9 5-9-5z"/><path d="m3 13 9 5 9-5"/></svg>',
    # The A11y Crawler mark: an open scan path with a node on its leading edge,
    # closing on a rounded 'a' for Axcess.
    # Stroked in currentColor so it takes the header's text colour and flips
    # with the theme, which the old filled tile could not do.
    "mark": (
        '<svg class="mark" viewBox="0 0 32 32" role="img" aria-label="Axcess logo" focusable="false" '
        'fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round">'
        '<path d="M 20.31 4.16 A 12.6 12.6 0 1 0 26.45 8.95"/>'
        '<path d="M 17.438 21.016 C 16.989 21.141 16.515 21.208 16.026 21.208 C 13.135 21.208 10.792 18.865 10.792 15.974 C 10.792 13.083 13.135 10.74 16.026 10.74 C 18.917 10.74 21.26 13.083 21.26 15.974 C 21.26 17.37 21.26 18.97 21.26 21.016"/>'
        '<circle cx="20.31" cy="4.16" r="3.2" fill="currentColor" stroke="none"/></svg>'
    ),
}
CARET = f'<svg class="caret" {_I}><path d="m6 9 6 6 6-6"/></svg>'


def icon(name: str) -> str:
    return f'<span class="icon">{ICONS[name]}</span>'


# ---------------------------------------------------------------------------
# Shared shell
# ---------------------------------------------------------------------------


def shell(page: Page, body: str) -> str:
    rel = "" if page.slug == "" else "../"
    home = rel or "./"

    def href(slug: str) -> str:
        return home if slug == "" else f"{rel}{slug}/"

    nav_items = "\n".join(
        f'        <li><a href="{href(s)}"{current}>{e(BY_SLUG[s].nav)}</a></li>'
        for s in NAV_ORDER
        for current in [' aria-current="page"' if s == page.slug else ""]
    )
    on_journey = page.slug in JOURNEY
    idx = JOURNEY.index(page.slug) if on_journey else -1
    prev_slug = JOURNEY[idx - 1] if on_journey and idx > 0 else None
    next_slug = JOURNEY[idx + 1] if on_journey and idx < len(JOURNEY) - 1 else None
    pager = ""
    if prev_slug is not None or next_slug is not None:
        parts = []
        if prev_slug is not None:
            p = BY_SLUG[prev_slug]
            parts.append(
                f'    <a class="prev" href="{href(prev_slug)}"><small>Previous</small><span>{e(p.nav if p.slug else "Home")}</span></a>'
            )
        if next_slug is not None:
            n = BY_SLUG[next_slug]
            parts.append(
                f'    <a class="next" href="{href(next_slug)}"><small>Next</small><span>{e(n.title)}</span></a>'
            )
        pager = (
            '<nav class="pager" aria-label="Read next">\n  <div class="wrap">\n'
            + "\n".join(parts)
            + "\n  </div>\n</nav>\n"
        )

    canonical = BASE_URL if page.slug == "" else f"{BASE_URL}{page.slug}/"
    full_title = (
        "Axcess: local-first accessibility testing"
        if page.slug == ""
        else f"{page.title} | Axcess"
    )
    return f"""<!doctype html>
<html lang="en" class="no-js">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(full_title)}</title>
<meta name="description" content="{e(page.description)}">
<link rel="canonical" href="{canonical}">
<meta property="og:type" content="website">
<meta property="og:site_name" content="Axcess">
<meta property="og:title" content="{e(full_title)}">
<meta property="og:description" content="{e(page.description)}">
<meta property="og:url" content="{canonical}">
<meta property="og:image" content="{BASE_URL}assets/diagrams/report-groups.png">
<meta name="twitter:card" content="summary_large_image">
<meta name="theme-color" content="#00274C">
{'<meta name="robots" content="noindex">' if page.slug not in JOURNEY else ""}
<link rel="icon" type="image/svg+xml" href="{rel}assets/favicon.svg">
<link rel="stylesheet" href="{rel}assets/site.css">
<script>document.documentElement.className = document.documentElement.className.replace('no-js', 'js');</script>
</head>
<body>
<a class="skip" href="#main">Skip to main content</a>

<header class="site-header">
  <div class="wrap">
    <a class="brand" href="{home}">{ICONS["mark"]}<span>Axcess<small>Accessibility evidence workbench</small></span></a>
    <button class="nav-toggle" type="button" aria-expanded="false" aria-controls="site-nav">Menu</button>
    <nav class="site-nav" id="site-nav" aria-label="Primary">
      <ul>
{nav_items}
        <li class="cta"><a href="{REPO}">GitHub</a></li>
      </ul>
    </nav>
  </div>
</header>

<main id="main" tabindex="-1">
{body}
</main>

{pager}<footer class="site-footer">
  <div class="wrap">
    <div class="cols">
      <div>
        <a class="brand" href="{home}">{ICONS["mark"]}<span>Axcess<small>Accessibility evidence workbench</small></span></a>
        <p style="margin-top:1rem;max-width:34ch">Local-first accessibility evidence for expert web audits. Free, open source, and built at the University of Michigan.</p>
      </div>
      <div>
        <h2>Learn</h2>
        <ul>
          <li><a href="{href("how-it-works")}">How it works</a></li>
          <li><a href="{href("coverage")}">What it checks</a></li>
          <li><a href="{href("who-its-for")}">Who it's for</a></li>
          <li><a href="{href("faq")}">Questions</a></li>
          <li><a href="{href("faq")}#glossary">Glossary</a></li>
        </ul>
      </div>
      <div>
        <h2>Use</h2>
        <ul>
          <li><a href="{href("get-started")}">Get started</a></li>
          <li><a href="{href("privacy")}">Privacy and trust</a></li>
          <li><a href="{REPO}/blob/main/docs/reading-your-report.md">Reading your report</a></li>
          <li><a href="{RELEASES}">Desktop releases</a></li>
          <li><a href="{DOCS}">Documentation</a></li>
        </ul>
      </div>
      <div>
        <h2>Project</h2>
        <ul>
          <li><a href="{href("about")}">About Axcess</a></li>
          <li><a href="{WHITEPAPER}">White paper</a></li>
          <li><a href="{REPO}">Source on GitHub</a></li>
          <li><a href="{REPO}/blob/main/LICENSE">MIT license</a></li>
        </ul>
      </div>
    </div>
    <div class="fine">
      <span>Axcess produces evidence for expert review. It does not certify WCAG conformance or legal compliance.</span>
      <span>Led by the College of Literature, Science, and the Arts Technology Services (LSA-TS) and Information and Technology Services (ITS) groups at the University of Michigan</span>
    </div>
  </div>
</footer>
<script src="{rel}assets/site.js" defer></script>
</body>
</html>
"""


def callout(text: str, kind: str = "", icon_name: str = "info") -> str:
    return f'<div class="callout {kind}">{ICONS[icon_name]}<p>{text}</p></div>'


HONESTY = (
    "<strong>Evidence, not a verdict.</strong> Axcess gives you evidence to review. Its results can't prove WCAG "
    "conformance, legal compliance, or that a whole site is accessible, and they don't replace testing with people "
    "who use assistive technology."
)


# ---------------------------------------------------------------------------
# Coverage data (from the product's own source of truth)
# ---------------------------------------------------------------------------

PIPE_NAMES = {
    "axe": "Rule engine (axe-core)",
    "keyboard": "Keyboard check",
    "responsive": "Zoom and reflow check",
    "focus": "Focus check",
    "visual": "Visual and motion check",
    "image": "Image text check",
    "semantic": "Meaning check (local AI)",
}
METHOD_PLAIN = {
    "automated": (
        "Automated",
        "Axcess checks this reliably on its own. A person confirms it applies and reviews any remaining states.",
    ),
    "partial": (
        "Partly automated",
        "Axcess catches the mechanical failures. A person tests the parts that need judgement.",
    ),
    "ai-assisted": (
        "AI-assisted lead",
        "A local AI model flags likely problems as leads. A person confirms each one before it counts.",
    ),
    "manual": (
        "Manual only",
        "Axcess has no check for this yet. The report gives you the steps to test it yourself.",
    ),
}
PRINCIPLES = {
    "1": (
        "Perceivable",
        "Can everyone perceive the content? Text alternatives for images, captions, contrast, zoom, and layouts that reflow on small screens.",
    ),
    "2": (
        "Operable",
        "Can everyone operate the site? Keyboard access, enough time, nothing that flashes, and clear ways to navigate and find things.",
    ),
    "3": (
        "Understandable",
        "Can everyone understand it? Readable language, predictable behaviour, and forms that help people avoid and fix mistakes.",
    ),
    "4": (
        "Robust",
        "Does it work with assistive technology? Names, roles, and status messages that screen readers can rely on.",
    ),
}


def coverage_data():
    from audit import coverage_matrix
    from audit.web import coverage_status as cov

    crit = coverage_matrix.load_matrix()
    summ = coverage_matrix.summary()
    return crit, summ, cov


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------


def home(summ) -> str:
    total, covered, manual = summ.total, summ.covered, summ.manual_only
    return f"""
<section class="hero">
  <div class="wrap hero-grid">
    <div>
      <span class="eyebrow">Local-first, WCAG 2.2 A and AA, free and open source</span>
      <h1>Test the pages behind the sign-in, <span class="hl">and keep the evidence at home.</span></h1>
      <p class="lede">Axcess is a free accessibility scanner that runs on your computer. You sign in to the site yourself, including single sign-on and two-factor steps, and Axcess scans from there. The pages, screenshots, and findings stay on your machine.</p>
      <div class="cta">
        <a class="btn btn-maize" href="get-started/">Get started</a>
        <a class="btn btn-ghost" href="coverage/">See what Axcess checks</a>
      </div>
      <p class="meta">Works on public sites too. Runs with <strong>no AI at all</strong>, or add a local model for judgement calls. <strong>Nothing is uploaded.</strong></p>
    </div>
    <div aria-hidden="true">
      <div class="issue-card">
        <div class="chips">
          <span class="chip chip-plain"><span class="sc">1.4.3</span>&nbsp;Contrast (Minimum)</span>
          <span class="chip chip-level">Level AA</span>
          <span class="chip chip-automated">Barrier</span>
        </div>
        <p style="color:var(--navy);font-size:1.08rem;font-weight:800;margin:0 0 .4rem">Body text is too light to read against its background</p>
        <dl>
          <dt>What</dt><dd>Grey paragraph text on 14 pages measures 3.1:1 against white. The minimum is 4.5:1.</dd>
          <dt>Why it matters</dt><dd>People with low vision, and anyone reading on a phone in sunlight, may not be able to read it.</dd>
          <dt>Expected fix</dt><dd>Darken the text colour in the article stylesheet. One change fixes all 14 pages.</dd>
          <dt>Where</dt><dd><span class="loc">/news/2026/welcome-week/ · .article-body p</span></dd>
        </dl>
      </div>
    </div>
  </div>
</section>

<section>
  <div class="wrap">
    <div class="section-head">
      <span class="eyebrow">The problem</span>
      <h2>The pages that matter most are often the hardest to test</h2>
      <p class="sub">Course sites, application portals, and department tools often sit behind a university sign-in with two-factor authentication. Much of their content only appears after someone opens a menu, a tab, or a dialog. Hosted crawlers usually need extra setup to sign in, and content behind a click is often missed by rule-based checkers.</p>
    </div>
    <ol class="steps steps-flow">
      <li>
        <h3>Sign in yourself</h3>
        <p>Axcess opens a normal browser window. You sign in directly with the site, and Axcess never sees your password or code.</p>
      </li>
      <li>
        <h3>Axcess scans from there</h3>
        <p>It visits the pages in the scope you set, opens menus, tabs, and dialogs, and runs its checks on every page it reaches.</p>
      </li>
      <li>
        <h3>You get clear, local evidence</h3>
        <p>Each issue shows what was found and exactly where, with fix guidance and rule documentation where they exist.</p>
      </li>
    </ol>
  </div>
</section>

<section class="soft">
  <div class="wrap">
    <div class="section-head">
      <span class="eyebrow">What makes it different</span>
      <h2>Built for the gaps other tools find hard to reach</h2>
    </div>
    <div class="grid grid-2">
      <article class="card">{icon("lock")}<h3>Scans behind a sign-in</h3><p>The signed-in session lives only in memory and ends with the scan. No password or reusable login is saved.</p></article>
      <article class="card">{icon("click")}<h3>Opens what visitors open</h3><p>Axcess clicks through menus, tabs, and dialogs, tests what appears, and tells you which button revealed each problem.</p></article>
      <article class="card">{icon("phone")}<h3>Checks rule-based tools rarely automate</h3><p>It measures reflow at phone width, text cut off at 200% zoom or with wider text spacing, and keyboard traps, and it finds text inside images.</p></article>
      <article class="card">{icon("shield")}<h3>Honest about certainty</h3><p>Every result is a Barrier, Needs review, or Informational, so you know what to fix now and what a person should confirm first. <a href="faq/#glossary">What the groups mean.</a></p></article>
      <article class="card">{icon("server")}<h3>A documented data boundary</h3><p>The privacy page lists what stays on your computer and the few things Axcess connects to. <a href="privacy/">Read what stays local.</a></p></article>
      <article class="card">{icon("layers")}<h3>Works alongside your other tools</h3><p>We use and like Siteimprove and axe DevTools. Axcess covers what is hard for them to reach. <a href="coverage/#compare">See the side-by-side comparison.</a></p></article>
    </div>
  </div>
</section>

<section>
  <div class="wrap">
    <div class="section-head">
      <span class="eyebrow">The workbench</span>
      <h2>An evidence workbench, not a scorecard</h2>
      <p class="sub">One score hides the details that make accessibility work actionable. Axcess keeps the page, the element, the screenshot, the rule, and the level of certainty together, so anyone can check a result for themselves.</p>
    </div>
    <div class="shot-frame">
      <img class="shot" src="assets/diagrams/report-groups.png" width="{DIAGRAM_SIZES["report-groups"][0]}" height="{DIAGRAM_SIZES["report-groups"][1]}"
        alt="{REPORT_GROUPS_ALT}">
    </div>
    <p class="caption">The three report groups and the checks that feed each one. <a href="coverage/#groups">Read more about the report groups.</a></p>
    <div class="stats" role="list" style="margin-top:1.75rem">
      <div class="stat" role="listitem"><b>{covered}<small> of {total}</small></b><span>WCAG 2.2 A and AA success criteria where Axcess contributes evidence. The other {manual} need a person, and each one comes with test steps.</span></div>
      <div class="stat" role="listitem"><b>0</b><span>Bytes of scan data sent to a cloud service. There is no telemetry and no account.</span></div>
      <div class="stat" role="listitem"><b>AAA</b><span>The level of axe-core rules that Axcess tests its own interface against.</span></div>
    </div>
  </div>
</section>

<section class="soft">
  <div class="wrap">
    <div class="section-head">
      <span class="eyebrow">Who it's for</span>
      <h2>Made for the people who do the work</h2>
    </div>
    <div class="grid grid-4">
      <a class="card card-accent" href="who-its-for/#accessibility-lead" style="text-decoration:none">{icon("person")}<h3>Accessibility analysts</h3><p>Triage findings with evidence, pair them with manual testing, and verify fixes on a rescan.</p></a>
      <a class="card card-accent" href="who-its-for/#editors-and-developers" style="text-decoration:none">{icon("people")}<h3>Editors and developers</h3><p>See what to change, where it is, and how you will know it is done.</p></a>
      <a class="card card-accent" href="who-its-for/#leadership" style="text-decoration:none">{icon("chart")}<h3>Leadership</h3><p>See how thoroughly a site was checked and what to fix first, without a misleading score.</p></a>
      <a class="card card-accent" href="who-its-for/#it-and-security" style="text-decoration:none">{icon("server")}<h3>IT and security</h3><p>Review a tool with no cloud dependency, no telemetry, and a documented data boundary.</p></a>
    </div>
  </div>
</section>

<section>
  <div class="wrap">
    {callout(HONESTY, "callout-maize", "warn")}
    <div style="display:flex;gap:.8rem;flex-wrap:wrap;margin-top:2rem;align-items:center">
      <a class="btn btn-primary" href="get-started/">Get started</a>
      <a class="btn btn-ghost" href="coverage/">See what Axcess checks</a>
      <a class="btn btn-ghost" href="faq/#glossary">Read the glossary</a>
    </div>
  </div>
</section>
"""


def how_it_works(summ) -> str:
    return f"""
<section class="hero hero-compact">
  <div class="wrap">
    <span class="eyebrow">How it works</span>
    <h1>From a web address to a <span class="hl">verified fix</span></h1>
    <p class="lede">Axcess follows the way an accessibility expert already works. Here is each step in plain language, followed by what the checks actually look at and how sure each one is.</p>
  </div>
</section>

<section>
  <div class="wrap">
    <div class="section-head">
      <span class="eyebrow">The workflow</span>
      <h2>Six steps, one scan</h2>
    </div>
    <ol class="steps">
      <li>
        <h3>Choose the site</h3>
        <p>Pick a public website, or choose <em>Site with a login or 2FA</em> for a site that needs a sign-in. For a protected site, Axcess opens a visible browser window and you sign in yourself, with your password, passkey, or one-time code. Axcess never asks for any of them.</p>
        <p class="tip">Only scan sites you are authorized to test.</p>
      </li>
      <li>
        <h3>Set the scope</h3>
        <p>Decide which part of the site to cover: a single section such as <code>/admissions/</code> or the whole site. Set a page limit, how deep to follow links, and how gently to crawl. A live preview shows what the scope means before you start.</p>
      </li>
      <li>
        <h3>Watch the scan</h3>
        <p>You see the current page, how many pages were discovered, loaded, and tested, which checks ran and which were skipped, and an estimated finish time. Live updates never steal your keyboard focus or jump the page.</p>
      </li>
      <li>
        <h3>Read the report</h3>
        <p>One table lists every issue and answers four questions:</p>
        <ul style="margin:.4rem 0 .6rem 1.25rem;color:var(--muted)">
          <li>What is the issue?</li>
          <li>Why does it matter?</li>
          <li>What is the expected fix?</li>
          <li>Where exactly is it?</li>
        </ul>
        <p>Axcess groups repeated occurrences of the same check into one row, so you can look for a shared cause.</p>
      </li>
      <li>
        <h3>Open the evidence</h3>
        <p>Follow any issue to the page, the element, the snippet, the rule, or the screenshot that produced it. Everything is stored with the scan, so a claim can be checked months later.</p>
      </li>
      <li>
        <h3>Export and verify</h3>
        <p>Record your decisions, export the workbook or report, assign the work, and rescan when fixes land. The comparison shows what is new, still detected, changed, or no longer detected.</p>
      </li>
    </ol>
  </div>
</section>

<section class="soft">
  <div class="wrap">
    <div class="section-head">
      <span class="eyebrow">Under the hood, in plain words</span>
      <h2>What each check looks at</h2>
      <p class="sub">A scan runs several independent checks. Each result keeps the name of the check that produced it, so two methods are never blended into one unexplained verdict.</p>
    </div>
    <div class="grid grid-3">
      <article class="card">{icon("table")}<h3>Rule engine</h3><p>The widely used axe-core engine inspects each rendered page for machine-testable problems: missing image descriptions, broken headings, form fields without names, low contrast, and more.</p><p><span class="chip chip-automated">Deterministic</span></p></article>
      <article class="card">{icon("layers")}<h3>Second opinion</h3><p>Optionally, Siteimprove's independent Alfa engine takes its own look. Each result keeps the name of the engine that found it, so you can compare them yourself.</p><p><span class="chip chip-automated">Deterministic</span></p></article>
      <article class="card">{icon("keyboard")}<h3>Keyboard check</h3><p>Axcess presses Tab and Shift+Tab through each page looking for places where keyboard users get stuck. It is deliberately cautious: ordinary focus loops and dialogs are not reported as traps.</p><p><span class="chip chip-partial">Browser-observed</span></p></article>
      <article class="card">{icon("phone")}<h3>Zoom and reflow check</h3><p>Each page is squeezed to a phone-width view, zoomed to about 200%, and given wider text spacing to see whether anything is cut off or overlaps.</p><p><span class="chip chip-partial">Browser-observed</span></p></article>
      <article class="card">{icon("eye")}<h3>Focus check</h3><p>Finds keyboard focus hidden behind sticky headers or banners, and tab orders that were forced out of sequence.</p><p><span class="chip chip-partial">Browser-observed</span></p></article>
      <article class="card">{icon("click")}<h3>Click through states</h3><p>Axcess can open menus, tabs, and dialogs and re-run the rule engine on what appears. <a href="../faq/#will-it-break-anything">What it will and will not click.</a></p><p><span class="chip chip-automated">Deterministic</span></p></article>
      <article class="card">{icon("image")}<h3>Image text check</h3><p>Built-in text recognition (OCR) finds <a href="../faq/#image-of-text">text inside images</a> and compares it with the alt text. An optional local vision model judges what the text is for.</p><p><span class="chip chip-partial">Mixed</span></p></article>
      <article class="card">{icon("play")}<h3>Visual and motion check</h3><p>Measures video and audio that autoplay without controls, records scrolling text, and, with a local vision model, compares the visual reading order to the order a screen reader would hear.</p><p><span class="chip chip-partial">Mixed</span></p></article>
      <article class="card">{icon("text")}<h3>Meaning check</h3><p>With a local language model, asks judgement questions a rule engine cannot: does this link make sense out of context? Does this heading describe its section? Is this form field explained well enough?</p><p><span class="chip chip-ai">AI-assisted lead</span></p></article>
    </div>
    <p class="small" style="margin-top:1.25rem">Every AI-assisted check is optional and runs on a local model you install yourself. Without one, the browser-only checks still run in full. <a href="../coverage/">See exactly which WCAG criteria each check covers.</a></p>
  </div>
</section>

<section>
  <div class="wrap">
    <div class="section-head">
      <span class="eyebrow">Evidence before verdicts</span>
      <h2>How sure is each result?</h2>
      <p class="sub">Not all findings are equally certain, and Axcess never pretends they are. Every result lands in one of three report groups, and only rule-engine failures become Barriers. <a href="../faq/#glossary">The glossary defines each group</a>, and <a href="../coverage/#groups">What Axcess checks shows which checks feed each one</a>.</p>
    </div>
    <div>{callout("<strong>Decisions are recorded, not just made.</strong> You can mark each finding in progress, remediated, accepted risk, or false positive. Each of those decisions needs a short written reason.", "", "check")}</div>
  </div>
</section>

<section class="soft">
  <div class="wrap">
    <div class="section-head">
      <span class="eyebrow">Modern websites</span>
      <h2>Works with apps, not just pages</h2>
      <p class="sub">Many sites today are applications built with React, Vue, Angular, or similar frameworks. A traditional crawler sees an empty shell. By default, Axcess renders every page in a real browser first.</p>
    </div>
    <div class="grid grid-2">
      <article class="card"><h3>Routes are discovered by following real links</h3><p>Axcess follows links it can see on rendered pages, including app-style routes, and stays inside the scope you set. It does not guess private addresses or read application code.</p></article>
      <article class="card"><h3>States are counted separately from pages</h3><p>When Axcess opens a menu or dialog and tests what appears, it reports that as a DOM state alongside the page count, not folded into it. A page count alone would undersell an app; counting states as pages would oversell the crawl.</p></article>
      <article class="card"><h3>Interaction is bounded and safe</h3><p>The probe never follows links to other addresses, and it refuses risky controls such as sign out or delete. It stops at 100 clicks per page, 20 of any repeated control, and five levels of newly revealed controls. <a href="../faq/#will-it-break-anything">See every safety rule.</a></p></article>
      <article class="card"><h3>Some things still need a person</h3><p>Hover-only content, gestures, operating-system menus, embedded third-party widgets, and states without a visible change on the page are outside what the probe can see. The report says so.</p></article>
    </div>
  </div>
</section>

<section>
  <div class="wrap">
    <div class="section-head">
      <span class="eyebrow">Follow-up</span>
      <h2>Rescan and compare</h2>
      <p class="sub">Run the same scope again and open <em>Verify changes</em> to line the two reports up, issue group by issue group.</p>
    </div>
    <p>When evidence is missing or the two scans covered different things, Axcess says it cannot compare reliably instead of guessing. "Not found this time" is not automatically "fixed". <a href="{REPO}/blob/main/docs/reading-your-report.md#verify-changes-after-a-fix">Read what each comparison result means.</a></p>
  </div>
</section>
"""


VOLUME_FILE = SITE / "data" / "volume.json"
METHOD_VOL_LABEL = {
    "automated": "Automated",
    "partial": "Partly automated",
    "ai-assisted": "AI-assisted lead",
    "manual": "Manual only",
    "best-practice": "Best practice",
}


def load_volume() -> dict | None:
    if not VOLUME_FILE.exists():
        return None
    import json

    return json.loads(VOLUME_FILE.read_text(encoding="utf-8"))


def volume_section(vol: dict | None) -> str:
    """Coverage by volume: what completed scans actually produced, in aggregate."""
    if not vol or not vol.get("occurrences"):
        return ""
    total = vol["occurrences"]
    pages = vol["pages"]
    rows = [r for r in vol["by_criterion"] if r["occurrences"] > 0]
    top = max(r["occurrences"] for r in rows)

    def row(r: dict) -> str:
        share = r["occurrences"] / total * 100
        page_pct = r["pages"] / pages * 100 if pages else 0
        width = max(r["occurrences"] / top * 100, 0.6)
        method = r["method"]
        chip_cls = "chip-plain" if method == "best-practice" else f"chip-{method}"
        sc = f'<span class="sc">{e(r["sc"])}</span> ' if r["sc"] else ""
        return (
            f'<tr><th scope="row" class="label">{sc}{e(r["name"])}'
            f'<span class="chip {chip_cls}">{e(METHOD_VOL_LABEL.get(method, method))}</span></th>'
            f'<td class="barcell"><span class="bar{" bp" if method == "best-practice" else ""}" style="width:{width:.1f}%"></span></td>'
            f'<td class="n">{r["occurrences"]:,}</td>'
            f'<td class="n">{share:.0f}%</td>'
            f'<td class="n"><span class="pct">{page_pct:.0f}% of pages</span></td></tr>'
        )

    table = "".join(row(r) for r in rows)

    order = ("automated", "partial", "ai-assisted", "best-practice")
    bm = vol["by_method"]
    segs = "".join(
        f'<span class="{m}" style="width:{bm[m] / total * 100:.1f}%"></span>'
        for m in order
        if bm.get(m)
    )
    legend = "".join(
        f'<span><i style="background:{ {"automated": "var(--m-automated)", "partial": "var(--m-partial)", "ai-assisted": "var(--m-ai)", "best-practice": "#7b8794"}[m] }"></i>'
        f"{e(METHOD_VOL_LABEL[m])}: {bm[m]:,} ({bm[m] / total * 100:.0f}%)</span>"
        for m in order
        if bm.get(m)
    )
    label = "; ".join(
        f"{METHOD_VOL_LABEL[m]} {bm[m] / total * 100:.0f}%" for m in order if bm.get(m)
    )

    rules = "".join(
        f'<tr><th scope="row">{e(r["name"])}<br><span class="small">{e(PIPE_NAMES.get(r["pipeline"], r["pipeline"]))}'
        f"{' · ' + e(r['sc']) if r['sc'] else ''}</span></th>"
        f'<td class="n">{r["occurrences"]:,}</td><td class="n">{r["pages"]:,}</td></tr>'
        for r in vol["by_rule"][:8]
    )
    per_page = total / pages if pages else 0

    return f"""
<section class="soft" id="volume">
  <div class="wrap">
    <div class="section-head">
      <span class="eyebrow">Coverage by volume</span>
      <h2>What a scan actually produces</h2>
      <p class="sub">Counting criteria says what Axcess can look for. Counting what it found says where the work is. These figures are aggregated from the completed scans on the development machine, with no page addresses or site names, and are refreshed with the site.</p>
    </div>
    <div class="stats" role="list">
      <div class="stat" role="listitem"><b>{total:,}</b><span>detected occurrences across all completed scans</span></div>
      <div class="stat" role="listitem"><b>{pages:,}</b><span>pages tested in {vol["scans"]} scans of {vol["hosts"]} websites</span></div>
      <div class="stat" role="listitem"><b>{per_page:.1f}</b><span>occurrences per page on average, before grouping by cause</span></div>
      <div class="stat" role="listitem"><b>{len(rows) - (1 if any(not r["sc"] for r in rows) else 0)}</b><span>success criteria with at least one detected occurrence</span></div>
    </div>

    <h3 style="margin-top:2.25rem">Where the volume comes from</h3>
    <p class="sub" style="margin-bottom:1rem">Occurrences by success criterion. The last column shows how many of the tested pages had at least one occurrence, which is often the more useful number: a problem on half the pages usually has one cause.</p>
    <div class="table-wrap" tabindex="0">
      <table class="bars">
        <caption class="vis-hidden">Detected occurrences by WCAG success criterion, with share of all occurrences and share of tested pages affected</caption>
        <thead><tr><th scope="col">Criterion</th><th scope="col"><span class="vis-hidden">Bar</span></th><th scope="col" class="n">Occurrences</th><th scope="col" class="n">Share</th><th scope="col" class="n">Pages affected</th></tr></thead>
        <tbody>{table}</tbody>
      </table>
    </div>

    <h3 style="margin-top:2.25rem">Share of volume by coverage method</h3>
    <p class="sub" style="margin-bottom:.5rem">By criteria count, most of WCAG needs a person. By volume of what a scan detects, almost everything so far came from the deterministic checks, which is exactly what they are for: the mechanical, repeated failures that nobody should find by hand.</p>
    <div class="volbar" role="img" aria-label="Of {total:,} occurrences: {label}.">{segs}</div>
    <div class="legend" aria-hidden="true">{legend}</div>

    <h3 style="margin-top:2.25rem">The checks that fired most</h3>
    <div class="table-wrap" tabindex="0">
      <table>
        <caption class="vis-hidden">Individual checks ranked by detected occurrences</caption>
        <thead><tr><th scope="col">Check</th><th scope="col" class="n" style="text-align:right">Occurrences</th><th scope="col" class="n" style="text-align:right">Pages</th></tr></thead>
        <tbody>{rules}</tbody>
      </table>
    </div>

    <p class="vol-note"><strong>Read this carefully.</strong> This is a small development sample of {vol["hosts"]} websites, not a picture of the web, and none of these occurrences has been through expert review yet, so they are <em>detected</em>, not <em>confirmed</em>. The local-AI checks (meaning, visual, and vision-model image judgement) were switched off for every one of these scans, so their volume is zero by configuration, not by ability; the OCR-only image check produced {vol["image_findings"]} findings, kept separately. Snapshot generated {e(vol["generated"])}.</p>
  </div>
</section>
"""


# ---------------------------------------------------------------------------
# Glossary (single source: docs/glossary.md)
# ---------------------------------------------------------------------------

GLOSSARY_FILE = ROOT / "docs" / "glossary.md"
GLOSSARY_URL = f"{REPO}/blob/main/docs/glossary.md"
_INLINE_MD = re.compile(r"\[([^\]]+)\]\(([^)]+)\)|\*\*([^*]+)\*\*|`([^`]+)`")


def _slug(text: str) -> str:
    """GitHub's heading-anchor rule, so ``glossary.md#needs-review`` links work here too."""
    return re.sub(r"[^\w\- ]", "", text.strip().lower()).replace(" ", "-")


def _inline_md(text: str) -> str:
    """Render the small Markdown subset the glossary uses: links, bold, and code."""
    out: list[str] = []
    pos = 0
    for m in _INLINE_MD.finditer(text):
        out.append(e(text[pos : m.start()]))
        if m.group(1) is not None:
            target = m.group(2)
            if not target.startswith(("#", "http://", "https://")):
                target = f"{REPO}/blob/main/docs/{target}"
            out.append(f'<a href="{e(target)}">{e(m.group(1))}</a>')
        elif m.group(3) is not None:
            out.append(f"<strong>{e(m.group(3))}</strong>")
        else:
            out.append(f"<code>{e(m.group(4))}</code>")
        pos = m.end()
    out.append(e(text[pos:]))
    return "".join(out)


def load_glossary() -> list[tuple[str, list[tuple[str, str]]]]:
    """Read docs/glossary.md as ``[(section, [(term, definition_html), ...]), ...]``.

    ``## Section`` headings group ``### Term`` headings, and each term's
    definition is the paragraph that follows it. The site renders this file
    instead of keeping its own copy, so the two cannot disagree.
    """
    sections: list[tuple[str, list[tuple[str, str]]]] = []
    term: str | None = None
    lines: list[str] = []

    def flush() -> None:
        if term is not None and sections and lines:
            sections[-1][1].append((term, _inline_md(" ".join(lines))))

    for raw in GLOSSARY_FILE.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line.startswith("### "):
            flush()
            term, lines = line[4:].strip(), []
        elif line.startswith("## "):
            flush()
            term, lines = None, []
            sections.append((line[3:].strip(), []))
        elif line and not line.startswith("#") and term is not None:
            lines.append(line)
    flush()
    return sections


# ---------------------------------------------------------------------------
# What Axcess checks, compared with Siteimprove and axe DevTools
# ---------------------------------------------------------------------------

# Checked against public Siteimprove and Deque documentation and the
# open-source axe-core and Alfa code in September 2026. "No automated check
# found" means the documentation showed none, not that none can exist.
# (check, what it catches, WCAG, report group, Siteimprove, axe DevTools)
CHECKS: tuple[tuple[str, str, str, str, str, str], ...] = (
    (
        "Rule engine (axe-core)",
        "Machine-testable problems on every rendered page, such as missing text alternatives, unlabeled form fields, low text contrast, and ARIA errors. About 90 rules run at Level AA.",
        "Many A and AA criteria, such as 1.1.1, 1.4.3, and 4.1.2",
        "Barrier",
        "Yes. Siteimprove checks the same kinds of problems with its own rule engine.",
        "Yes. axe DevTools runs these same axe-core rules.",
    ),
    (
        "Click through menus, tabs, and dialogs",
        "Problems that only appear after a control is used. Axcess operates each safe control, runs axe-core again on what appears, and records which control revealed each problem.",
        "The same criteria as axe-core",
        "Barrier",
        "Not automatically. Its crawler tests each page as it loads. A Dynamic Content Checker add-on lets you capture other states yourself.",
        "Not automatically. axe-core does not test closed menus or dialogs, so you open them and scan again. Paid guided tests help with dialogs.",
    ),
    (
        "Reflow at phone width",
        "Pages that need sideways scrolling at 320 CSS pixels wide.",
        "1.4.10 (AA)",
        "Needs review",
        "No automated check found.",
        "No automated check found.",
    ),
    (
        "Text cut off at 200% zoom",
        "Text that is clipped when the page is enlarged. Axcess approximates 200% zoom with a smaller browser window.",
        "1.4.4 (AA)",
        "Needs review",
        "Partly. It flags pages that block zooming. It has also documented a “Text is clipped when resized” rule, but its open-source engine deprecated that rule in 2026, so ask Siteimprove whether it still runs.",
        "Partly. axe-core flags pages that block zooming, not clipped text.",
    ),
    (
        "Text spacing",
        "Text that is clipped after line, letter, word, and paragraph spacing are raised to the WCAG values.",
        "1.4.12 (AA)",
        "Needs review",
        "Partly. It flags inline styles that lock spacing with !important. No check found that applies the spacing and looks for clipping.",
        "Partly. The same inline-style check.",
    ),
    (
        "Keyboard traps",
        "Places where Tab and Shift+Tab both fail to move focus away. Reported at most once per page.",
        "2.1.2 (A)",
        "Needs review",
        "No automated check found.",
        "Only in the paid Keyboard guided test. No axe-core rule.",
    ),
    (
        "Focus checks",
        "A focused control hidden behind a sticky or fixed header, footer, or banner, and elements that force the tab order with a positive tabindex.",
        "2.4.11 (AA), 2.4.3 (A)",
        "Needs review",
        "No automated check found.",
        "Partly. axe-core flags positive tabindex as a best practice, and the paid Keyboard guided test reviews tab order. No rule found for focus hidden behind other content.",
    ),
    (
        "Target size",
        "Buttons and links smaller than 24 by 24 CSS pixels without enough space around them.",
        "2.5.8 (AA)",
        "Barrier",
        "Yes, when WCAG 2.2 is selected. It also checks the stricter 44 pixel size (2.5.5, AAA), which Axcess checks only when Siteimprove Alfa runs at Level AAA.",
        "Only when WCAG 2.2 rules are turned on. The axe-core rule is off by default, and Axcess turns it on for Level AA scans.",
    ),
    (
        "Text inside images",
        "Images that contain words, found with OCR and compared with their alt text. An optional local vision model judges what the text is for and maps it to a WCAG criterion.",
        "1.4.5 (AA), 1.1.1 (A)",
        "Needs review (Informational when the alt text already matches)",
        "No automated images-of-text check found. Its open-source engine has an experimental rule that asks whether an image contains text. An on-demand AI check judges whether alt text matches the image.",
        "No automated check found. A paid guided test reviews image alternatives.",
    ),
    (
        "Motion and reading order (optional)",
        "Audio or video that plays on its own without controls, marquee text, and, with a local vision model, a visual reading order that differs from the code order.",
        "1.4.2, 2.2.2, 1.3.2 (A)",
        "Needs review",
        "Partly. Its open-source engine has an autoplaying audio rule that asks a person to confirm how long the audio plays, and a best-practice rule flags blink and marquee. No reading-order check found.",
        "Partly. axe-core covers autoplaying audio (for review), blink, and marquee. No reading-order check found.",
    ),
    (
        "AI language checks (optional)",
        "Vague link text, headings that do not describe their section, form fields without clear labels or instructions, and audio without a transcript, judged by a local AI model.",
        "2.4.4 (A), 2.4.6 (AA), 3.3.2 (A), 1.2.1 (A)",
        "Needs review",
        "Partly. It checks that links and fields have names, offers an opt-in AI rule for descriptive headings, and guides a review for transcripts.",
        "Partly. axe-core checks that links and fields have names. Paid guided tests cover link purpose, headings, and labels.",
    ),
)

LSA_WEB_RESOURCES = "https://accessibility.lsa.umich.edu/browse-resources/web-accessibility.html"
LSA_TRAINING = "https://accessibility.lsa.umich.edu/learn/training.html"


def checks_sections() -> str:
    """The report groups, the comparison table, and what still needs a person."""
    rows = "".join(
        f'<tr><th scope="row">{e(check)}</th><td>{e(what)}</td><td>{e(sc)}</td><td>{e(group)}</td><td>{e(si)}</td><td>{e(axe)}</td></tr>'
        for check, what, sc, group, si, axe in CHECKS
    )
    return f"""
<section class="soft" id="groups">
  <div class="wrap">
    <div class="section-head">
      <span class="eyebrow">Report groups</span>
      <h2>Every result lands in one of three groups</h2>
      <p class="sub">The group tells you how certain a result is and what to do next. <a href="../faq/#glossary">The glossary defines each group.</a></p>
    </div>
    <div class="shot-frame">
      <img class="shot" src="../assets/diagrams/report-groups.png" width="{DIAGRAM_SIZES["report-groups"][0]}" height="{DIAGRAM_SIZES["report-groups"][1]}"
        alt="{REPORT_GROUPS_ALT}">
    </div>
    <div class="lanes" style="margin-top:1.5rem">
      <div class="lane lane-automated">
        <span class="chip chip-automated">Barrier</span>
        <h3>Confirm it, then fix it</h3>
        <p>Comes from axe-core rule failures, including problems found after clicking, and from Siteimprove Alfa failures. Confirm it on the page, fix it, then rescan.</p>
      </div>
      <div class="lane lane-observed">
        <span class="chip chip-partial">Needs review</span>
        <h3>A person decides</h3>
        <p>Comes from browser checks, the keyboard check, text in images whose alt text is missing or does not match, local AI checks, and Alfa “cannot tell” results. Test it on the page and record your decision.</p>
      </div>
      <div class="lane" style="border-top-color:#c2cad6">
        <span class="chip chip-manual">Informational</span>
        <h3>Nothing to fix</h3>
        <p>Comes from image checks where the alt text already matches, and from older records kept for history. No action is needed.</p>
      </div>
    </div>
  </div>
</section>

<section id="compare">
  <div class="wrap">
    <div class="section-head">
      <span class="eyebrow">Compared with other tools</span>
      <h2>Where Axcess fits next to Siteimprove and axe DevTools</h2>
      <p class="sub">We use and like both. Siteimprove monitors whole sites from the cloud, and the axe DevTools browser extension checks the page in front of you. Axcess fills gaps: pages behind a sign-in, content behind a click, and checks that need a real browser or a person's judgement.</p>
    </div>
    <div class="table-wrap" tabindex="0" role="region" aria-label="Axcess checks compared with Siteimprove and axe DevTools">
      <table>
        <caption class="vis-hidden">Axcess checks, what they catch, and whether Siteimprove or axe DevTools also catch them</caption>
        <thead><tr><th scope="col">Check</th><th scope="col">What it catches</th><th scope="col">WCAG</th><th scope="col">Report group</th><th scope="col">Also caught by Siteimprove?</th><th scope="col">Also caught by axe DevTools?</th></tr></thead>
        <tbody>{rows}</tbody>
      </table>
    </div>
    <div class="grid grid-2" style="margin-top:1.5rem">
      <article class="card"><h3>Pages behind a sign-in</h3><p>Axcess scans them after you sign in yourself, including single sign-on and two-factor steps. Siteimprove's help center describes crawling behind a login through a setup done by its support team, and points to an add-on for sites that use multi-factor sign-in. Its free browser extension checks signed-in pages one at a time in your own browser, and so does the axe DevTools extension.</p></article>
      <article class="card"><h3>A second opinion from Siteimprove's engine</h3><p>Axcess can also run Siteimprove Alfa, the open-source engine behind Siteimprove's checks, on your computer. Each result keeps the name of the engine that found it, so you can compare them. Results can differ from what the Siteimprove platform reports, which adds its own reviews and settings.</p></article>
    </div>
    <p class="small" style="margin-top:1.25rem">Checked in September 2026 against public Siteimprove and Deque documentation and the open-source axe-core and Alfa code. “No automated check found” means we found none in their documentation, not that none can exist. Tools change quickly, so please <a href="{REPO}/issues">open an issue on GitHub</a> if something here is out of date.</p>
  </div>
</section>

<section class="soft" id="by-hand">
  <div class="wrap">
    <div class="section-head">
      <span class="eyebrow">Manual testing</span>
      <h2>What you still need to test by hand</h2>
      <p class="sub">These checks still need a person. See <a href="../faq/#axcess-and-manual-testing">Axcess and manual testing</a>.</p>
    </div>
    <div class="grid grid-3">
      <article class="card">{icon("keyboard")}<h3>Keyboard</h3><p>Use only the keyboard to reach and operate everything, with Tab, Shift+Tab, Enter, Space, the arrow keys, and Escape. Check that focus is always visible and moves in a sensible order. Axcess's keyboard check only looks for traps.</p></article>
      <article class="card">{icon("people")}<h3>Screen reader</h3><p>Listen to key pages and tasks with a screen reader such as NVDA, JAWS, or VoiceOver. Check that names, roles, headings, and announcements make sense in context.</p></article>
      <article class="card">{icon("check")}<h3>Real tasks</h3><p>Complete real tasks from start to finish, such as applying or registering, including error messages and time limits. Axcess does not submit forms or complete tasks on its own, apart from a search form you configure.</p></article>
    </div>
    <p style="margin-top:1.25rem">The criteria list below gives the manual steps for every WCAG success criterion. For guides and training, see <a href="{LSA_WEB_RESOURCES}">LSA Accessibility's web accessibility resources</a> and <a href="{LSA_TRAINING}">LSA Accessibility training</a>.</p>
  </div>
</section>
"""


def coverage(crit, summ, cov) -> str:
    total = summ.total
    bm = summ.by_method
    by_level = summ.by_level

    def pct(n: int) -> str:
        return f"{n / total * 100:.1f}%"

    bar = "".join(
        f'<span class="{m}" style="width:{pct(bm[m])}"></span>'
        for m in ("automated", "partial", "ai-assisted", "manual")
    )
    legend = (
        "".join(
            f'<span><i style="background:var(--m-{"ai" if m == "ai-assisted" else m})"></i>{e(METHOD_PLAIN[m][0])}: {bm[m]}</span>'
            for m in ("automated", "partial", "ai-assisted")
        )
        + f'<span><i style="background:#c2cad6"></i>Manual only: {bm["manual"]}</span>'
    )

    buckets = "".join(
        f'<article class="lane lane-{"ai" if m == "ai-assisted" else ("automated" if m == "automated" else "observed")}" style="{"border-top-color:#c2cad6" if m == "manual" else ""}">'
        f'<span class="chip chip-{m}">{e(METHOD_PLAIN[m][0])}</span><h3>{bm[m]} criteria</h3><p>{e(METHOD_PLAIN[m][1])}</p></article>'
        for m in ("automated", "partial", "ai-assisted", "manual")
    )

    # Criterion cards grouped by principle.
    groups = []
    for pnum, (pname, pblurb) in PRINCIPLES.items():
        items = [c for c in crit if c.sc.startswith(pnum + ".")]
        cards = []
        for c in items:
            label = METHOD_PLAIN[c.method][0]
            pipes = ", ".join(PIPE_NAMES.get(p, p) for p in c.pipelines)
            text = " ".join(
                [c.sc, c.name, c.level, label, c.automated_check, c.manual_check, pipes]
            ).lower()
            anchor = "sc-" + c.sc.replace(".", "-")
            automated = (
                f"<div><h4>What Axcess does</h4><p>{e(c.automated_check)}</p></div>"
                if c.automated_check
                else "<div><h4>What Axcess does</h4><p>No automated check yet. The report includes this criterion in the manual testing list with the steps below.</p></div>"
            )
            # The check names are a real list (role="list" on the existing
            # spans keeps the site.css chip layout), named by its visible label.
            pipes_html = (
                f'<div class="pipes"><span id="{anchor}-checks">Checks involved:</span>'
                f'<span role="list" aria-labelledby="{anchor}-checks" style="display:flex;flex-wrap:wrap;gap:.4rem">'
                + "".join(
                    f'<span role="listitem" class="chip chip-plain">{e(PIPE_NAMES.get(p, p))}</span>'
                    for p in c.pipelines
                )
                + f"</span><span>Confidence: {e(c.confidence)}</span></div>"
                if c.pipelines
                else ""
            )
            cards.append(
                f'''      <details class="crit" id="{anchor}" data-method="{e(c.method)}" data-level="{e(c.level)}" data-text="{e(text)}">
        <summary>
          <span class="sc">{e(c.sc)}</span>
          <span class="name">{e(c.name)}</span>
          <span class="tags"><span class="chip chip-level">Level {e(c.level)}</span><span class="chip chip-{e(c.method)}">{e(label)}</span></span>
          {CARET}
        </summary>
        <div class="crit-body">
          {automated}
          <div><h4>What a person still checks</h4><p>{e(c.manual_check)}</p></div>
          {pipes_html}
        </div>
      </details>'''
            )
        groups.append(
            f"""    <div class="principle" id="principle-{pnum}">
      <h3>{pnum}. {e(pname)} <small><span data-visible>{len(items)}</span> of {len(items)} criteria</small></h3>
      <p class="principle-blurb">{e(pblurb)}</p>
      <div class="crit-list">
{chr(10).join(cards)}
      </div>
    </div>"""
        )
    explorer = "\n".join(groups)

    planned = [r for r in cov.ROADMAP if r.status == "planned"]
    roadmap = "".join(
        f'<article class="card"><h3><span class="sc">{e(r.wcag)}</span> {e(r.issue)}</h3><p>{e(r.what)}</p></article>'
        for r in planned
    )

    level_rows = "".join(
        f"<tr><th scope=\"row\">Level {lvl}</th><td>{sum(by_level[lvl].values())}</td><td>{by_level[lvl]['automated']}</td><td>{by_level[lvl]['partial']}</td><td>{by_level[lvl]['ai-assisted']}</td><td>{by_level[lvl]['manual']}</td><td><b>{sum(by_level[lvl].values()) - by_level[lvl]['manual']}</b></td></tr>"
        for lvl in ("A", "AA")
    )

    return f"""
<section class="hero hero-compact">
  <div class="wrap">
    <span class="eyebrow">Coverage</span>
    <h1>What Axcess checks, and what it <span class="hl">honestly can't</span></h1>
    <p class="lede">The Web Content Accessibility Guidelines (WCAG) 2.2 define {total} Level A and AA success criteria. Axcess contributes evidence to {summ.covered} of them today. This page shows where each result lands and how Axcess compares with Siteimprove and axe DevTools. It then lists all {total} criteria, with test steps for the {summ.manual_only} that a person must test by hand.</p>
  </div>
</section>
{checks_sections()}

<section>
  <div class="wrap">
    <div class="section-head">
      <span class="eyebrow">At a glance</span>
      <h2>{summ.covered} of {total} criteria with Axcess evidence</h2>
      <p class="sub">These numbers are generated from the coverage file the product itself reads, so they cannot drift from the code.</p>
    </div>
    <div class="covbar" role="img" aria-label="Of {total} criteria: {bm["automated"]} automated, {bm["partial"]} partly automated, {bm["ai-assisted"]} AI-assisted, {bm["manual"]} manual only.">{bar}</div>
    <div class="legend" aria-hidden="true">{legend}</div>
    <div class="lanes lanes-4">{buckets}</div>
    <div class="table-wrap" style="margin-top:1.75rem" tabindex="0" role="region" aria-label="Coverage by WCAG conformance level">
      <table>
        <caption class="vis-hidden">Coverage by WCAG conformance level</caption>
        <thead><tr><th scope="col">Level</th><th scope="col">Criteria</th><th scope="col">Automated</th><th scope="col">Partly automated</th><th scope="col">AI-assisted</th><th scope="col">Manual only</th><th scope="col">With Axcess evidence</th></tr></thead>
        <tbody>{level_rows}<tr><th scope="row">A + AA</th><td>{total}</td><td>{bm["automated"]}</td><td>{bm["partial"]}</td><td>{bm["ai-assisted"]}</td><td>{bm["manual"]}</td><td><b>{summ.covered}</b></td></tr></tbody>
      </table>
    </div>
    <div style="margin-top:1.5rem">{callout("<strong>&quot;Contributes evidence&quot; is not &quot;proves conformance&quot;.</strong> Even a fully automated criterion leaves a residual human judgement, which is why every card below has a <em>What a person still checks</em> section.", "", "info")}</div>
  </div>
</section>

<section class="soft" id="explorer">
  <div class="wrap">
    <div class="section-head">
      <span class="eyebrow">Explore</span>
      <h2>All {total} success criteria</h2>
      <p class="sub">Filter by how Axcess covers a criterion or by conformance level, or search by number, name, or keyword. Open any criterion to read what Axcess does and what a person still checks.</p>
    </div>
    <div class="explorer-controls">
      <div class="filter-row" role="group" aria-label="Filter by coverage method">
        <span class="label">Coverage</span>
        <button class="pill" type="button" data-filter="method" data-value="all" aria-pressed="true">All</button>
        <button class="pill" type="button" data-filter="method" data-value="automated" aria-pressed="false">Automated</button>
        <button class="pill" type="button" data-filter="method" data-value="partial" aria-pressed="false">Partly automated</button>
        <button class="pill" type="button" data-filter="method" data-value="ai-assisted" aria-pressed="false">AI-assisted</button>
        <button class="pill" type="button" data-filter="method" data-value="manual" aria-pressed="false">Manual only</button>
      </div>
      <div class="filter-row" role="group" aria-label="Filter by conformance level">
        <span class="label">Level</span>
        <button class="pill" type="button" data-filter="level" data-value="all" aria-pressed="true">A and AA</button>
        <button class="pill" type="button" data-filter="level" data-value="A" aria-pressed="false">Level A</button>
        <button class="pill" type="button" data-filter="level" data-value="AA" aria-pressed="false">Level AA</button>
      </div>
      <div class="search">
        <label for="crit-search">Search</label>
        <input id="crit-search" type="search" placeholder="e.g. 2.4.4, captions, keyboard" autocomplete="off">
      </div>
      <div class="filter-row">
        <p class="result-count" id="result-count" role="status" aria-live="polite" style="margin:0">Showing all {total} success criteria</p>
        <span style="flex:1"></span>
        <button class="pill" type="button" id="expand-all">Expand all</button>
        <button class="pill" type="button" id="collapse-all">Collapse all</button>
      </div>
    </div>
{explorer}
  </div>
</section>

<section>
  <div class="wrap">
    <div class="section-head">
      <span class="eyebrow">Roadmap</span>
      <h2>Next on the list</h2>
      <p class="sub">Criteria the project has designed a check for but not yet shipped. They stay labelled manual until the code exists and has been validated.</p>
    </div>
    <div class="grid grid-3">{roadmap}</div>
    <p class="small" style="margin-top:1.25rem">Roadmap and coverage are reconciled against the code in <a href="{REPO}/blob/main/docs/coverage-tracker.md">the coverage tracker</a>.</p>
  </div>
</section>
"""


def who_its_for() -> str:
    return f"""
<section class="hero hero-compact">
  <div class="wrap">
    <span class="eyebrow">Who it's for</span>
    <h1>Made for the people who <span class="hl">do the work</span></h1>
    <p class="lede">Axcess was commissioned for an accessibility lead at a large university and designed around the people that lead hands work to. Find yourself below to see what you would actually get.</p>
  </div>
</section>

<section>
  <div class="wrap">
    <article class="persona" id="accessibility-lead">
      <div class="who">
        <div class="avatar">{ICONS["person"]}</div>
        <h2>The accessibility lead</h2>
        <p>In-house professional responsible for dozens of sites, triaging hundreds of findings in a sitting, often while screen-sharing with an editor who has never seen the tool.</p>
        <p class="job">"Find every barrier across this site before the next report cycle, hand a prioritised list to the content team, and verify the fixes."</p>
      </div>
      <div class="what">
        <h3>What you get</h3>
        <ul class="checks">
          <li>A prioritised, grouped issue table the moment a scan finishes, scoped to that scan only.</li>
          <li>A defensible verdict for every finding: the rule, the confidence, the affected users, and the evidence side by side.</li>
          <li>One-keystroke decisions with a required rationale, so the record shows who decided what and when.</li>
          <li>A manual review matrix for the criteria no tool can decide, with the procedure for each.</li>
          <li>Rescan comparison so you spend your time on what changed.</li>
        </ul>
        <h3>Designed for you, specifically</h3>
        <p>The interface is held to WCAG 2.2 AAA, works fully by keyboard, reflows to a phone width, and never conveys severity by colour alone. If you use a screen reader, magnification, or keyboard only, the tool was built with you in the room.</p>
      </div>
    </article>

    <article class="persona" id="editors-and-developers">
      <div class="who">
        <div class="avatar">{ICONS["people"]}</div>
        <h2>The editor or developer receiving the work</h2>
        <p>You never open Axcess. You open a Jira ticket, a spreadsheet row, or a report and need to know what to change.</p>
        <p class="job">"Take the finding, fix the page, mark it done, move on."</p>
      </div>
      <div class="what">
        <h3>What you get</h3>
        <ul class="checks">
          <li>Plain-language remediation hints written for you, not for the auditor: what to change and why it helps.</li>
          <li>The exact page, the exact element, and a snippet, so there is no hunting.</li>
          <li>A "done when" acceptance note so you know when the fix is complete.</li>
          <li>Jira import that uses Jira's own column names, and Excel with clickable links.</li>
          <li>Repeated problems grouped by cause, so one template fix can close hundreds of occurrences.</li>
        </ul>
      </div>
    </article>

    <article class="persona" id="leadership">
      <div class="who">
        <div class="avatar">{ICONS["chart"]}</div>
        <h2>Leadership and compliance owners</h2>
        <p>You need to know how exposed a site is, what to fund first, and whether last quarter's work made a difference.</p>
        <p class="job">"How thoroughly was this evaluated, what should we fix first, and is it getting better?"</p>
      </div>
      <div class="what">
        <h3>What you get</h3>
        <ul class="checks">
          <li>A stakeholder report that states scope, methods, and limitations before it states results.</li>
          <li>Issues ranked by impact on people, not by a single score that hides the reasoning.</li>
          <li>A "Who's Affected" view that shows which abilities each issue blocks.</li>
          <li>Honest coverage: which criteria were checked by a tool, which by a person, and which are still untested.</li>
          <li>Trend evidence across rescans instead of a fresh, incomparable number each time.</li>
        </ul>
        <h3>What you will not get</h3>
        <p>A certificate. Axcess never generates a conformance claim or an Accessibility Conformance Report automatically. A qualified person completes those, using Axcess evidence as input.</p>
      </div>
    </article>

    <article class="persona" id="it-and-security">
      <div class="who">
        <div class="avatar">{ICONS["server"]}</div>
        <h2>IT and security reviewers</h2>
        <p>You have to approve a tool that crawls institutional websites, some of them behind a login.</p>
        <p class="job">"Where does the data go, what does it connect to, and what happens with credentials?"</p>
      </div>
      <div class="what">
        <h3>What you get</h3>
        <ul class="checks">
          <li>No cloud service, no account, no telemetry. Evidence lives in a local database in the operating system's application-data folder.</li>
          <li>Outbound connections only to the site being scanned, plus an optional local AI service on the same machine.</li>
          <li>Credentials never enter Axcess. The auditor signs in inside a visible browser window; login pages are not stored as evidence.</li>
          <li>A sandboxed desktop app with a documented security boundary, and open source you can read.</li>
          <li>A stricter managed mode for sensitive institutional targets, with identity-aware access, encryption, redaction, and short retention. Disabled by default.</li>
        </ul>
        <p><a href="../privacy/">Read the full privacy and trust page.</a></p>
      </div>
    </article>
  </div>
</section>

<section class="soft">
  <div class="wrap">
    <div class="section-head">
      <span class="eyebrow">Not designed for</span>
      <h2>Where Axcess is the wrong tool</h2>
    </div>
    <div class="grid grid-3">
      <article class="card"><h3>Public scanning services</h3><p>Axcess is a local tool for one operator at a time. It is not a web service anyone can point at any site, and it should never be exposed to the open internet.</p></article>
      <article class="card"><h3>Nightly bulk monitoring</h3><p>The command line can be scheduled, but the interface is built for careful one-at-a-time review, not fleet-wide dashboards.</p></article>
      <article class="card"><h3>Automatic certification</h3><p>No scan proves a site conforms. Testing with people who use assistive technology remains essential.</p></article>
    </div>
  </div>
</section>
"""


def privacy() -> str:
    return f"""
<section class="hero hero-compact">
  <div class="wrap">
    <span class="eyebrow">Privacy and trust</span>
    <h1>Your evidence <span class="hl">never leaves</span> your computer</h1>
    <p class="lede">Local-first is not a slogan here. It is the reason Axcess exists: accessibility audits often involve private, sensitive, or login-protected pages, and those should not be uploaded to anyone's cloud.</p>
  </div>
</section>

<section>
  <div class="wrap">
    <div class="section-head">
      <span class="eyebrow">The boundary</span>
      <h2>What stays local and what connects out</h2>
    </div>
    <div class="shot-frame" style="margin-bottom:1.5rem">
      <img class="shot" src="../assets/diagrams/privacy-boundary.png" width="{DIAGRAM_SIZES["privacy-boundary"][0]}" height="{DIAGRAM_SIZES["privacy-boundary"][1]}"
        alt="Diagram of what stays on your computer. Reports, stored pages, screenshots, images, and logs stay in local files, and optional Ollama runs locally. Axcess connects to the website you scan and, in the desktop app, to GitHub once per launch to check for updates. Links such as &quot;Rule docs&quot; and &quot;Give feedback&quot; open in your browser only when you click them. It has no account, telemetry, or upload. Files are not encrypted, and deleting a report keeps its image and screenshot files.">
    </div>
    <div class="boundary">
      <span class="tag" id="stays-label">Stays on your computer</span>
      <div class="inner" role="list" aria-labelledby="stays-label">
        <div role="listitem"><strong>Scan evidence</strong><span>Pages, elements, snippets, screenshots, and image files, stored in a local database.</span></div>
        <div role="listitem"><strong>Your decisions</strong><span>Every review outcome, rationale, and status change, with its history.</span></div>
        <div role="listitem"><strong>Reports and exports</strong><span>Workbooks, reports, and ticket files are written to your disk and go only where you send them.</span></div>
        <div role="listitem"><strong>The browser</strong><span>Chromium renders pages locally, including the visible window you sign in with. The desktop app includes it.</span></div>
        <div role="listitem"><strong>Text recognition</strong><span>OCR reads text inside images on your machine. The desktop app includes it; a source install needs Tesseract installed separately.</span></div>
        <div role="listitem"><strong>Optional AI</strong><span>If you choose to install a local model through Ollama, it runs on this computer too.</span></div>
      </div>
    </div>
    <span class="vis-hidden" id="connects-label">Connects out</span>
    <div class="outside" role="list" aria-labelledby="connects-label">
      <div role="listitem"><strong>Connects to: the website you are scanning</strong><span>Axcess loads pages from the target site at the rate you set. Public scans respect robots.txt unless you say otherwise; login scans do not check it. Viewing a stored page later can also load that site's styles, fonts, and images.</span></div>
      <div role="listitem"><strong>Connects to: GitHub, for desktop updates</strong><span>Once per launch, the desktop app asks GitHub whether a newer version exists. That request carries no scan data, and setting <code>AXCESS_DISABLE_UPDATE_CHECK=1</code> turns it off.</span></div>
      <div role="listitem"><strong>Connects to: nothing else</strong><span>No telemetry, no usage analytics, no cloud AI. The <em>Give feedback</em> button opens a form in your browser only when you choose to click it, and carries nothing about your scan. Any other external integration would require an explicit administrator decision.</span></div>
    </div>
  </div>
</section>

<section class="soft">
  <div class="wrap">
    <div class="section-head">
      <span class="eyebrow">Protected sites</span>
      <h2>Scanning behind a login without sharing your password</h2>
      <p class="sub">Many of the pages that matter most are behind a sign-in. Axcess handles this the safe way: you sign in, and it scans with that session.</p>
    </div>
    <div class="shot-frame" style="margin-bottom:1.5rem">
      <img class="shot" src="../assets/diagrams/login-scan-flow.png" width="{DIAGRAM_SIZES["login-scan-flow"][0]}" height="{DIAGRAM_SIZES["login-scan-flow"][1]}"
        alt="Diagram of a login scan. You choose &quot;Site with a login or 2FA&quot;, Axcess opens a visible browser, you sign in directly with the site including any two-factor step, then select &quot;I'm signed in, start scan&quot;. Axcess moves the session in memory to its scanning browser, crawls from where you landed, and deletes the temporary browser profile when the scan ends. Login scans need an HTTPS site whose address resolves to a public IP address.">
    </div>
    <ul class="checks">
      <li>The sign-in window is a normal Chromium window with a fresh temporary profile.</li>
      <li>You type your password, passkey, or one-time code into the website, never into Axcess.</li>
      <li>The session stays in memory and ends with the scan, and the temporary profile is deleted. Rendered pages and screenshots of what you signed in to are saved in the local report unless you choose <em>Don’t store rendered pages</em>.</li>
    </ul>
    <p style="margin-top:1rem"><a href="../get-started/#sign-in">Step by step: scan a site behind a sign-in.</a></p>
    <div style="margin-top:1.5rem">{callout("<strong>You stay in control of sign-in.</strong> Axcess only continues after you sign in yourself, so use accounts and sites you have permission to test.", "callout-maize", "lock")}</div>
  </div>
</section>

<section>
  <div class="wrap">
    <div class="section-head">
      <span class="eyebrow">Optional AI</span>
      <h2>AI is opt-in, local, and labelled</h2>
    </div>
    <div class="grid grid-2">
      <article class="card">{icon("cpu")}<h3>You install it, or you don't</h3><p>AI-assisted checks need a separately installed local service called Ollama and models you download yourself. Axcess never installs or downloads them silently, and it works without them.</p></article>
      <article class="card">{icon("shield")}<h3>Every AI result is marked</h3><p>Model output is shown as a lead that needs confirmation, with the model's rationale beside the original evidence. It cannot become a confirmed barrier without a person.</p></article>
    </div>
  </div>
</section>

<section class="soft">
  <div class="wrap">
    <div class="section-head">
      <span class="eyebrow">Where your data lives</span>
      <h2>Plain folders you control</h2>
      <p class="sub">The desktop app keeps evidence in the operating system's application-data folder, never inside the app itself. Delete the folder and the evidence is gone.</p>
    </div>
    <div class="table-wrap" tabindex="0" role="region" aria-label="Data locations by operating system">
      <table>
        <caption class="vis-hidden">Data locations by operating system</caption>
        <thead><tr><th scope="col">Operating system</th><th scope="col">Data folder</th></tr></thead>
        <tbody>
          <tr><th scope="row">macOS</th><td><code>~/Library/Application Support/Axcess/data/</code></td></tr>
          <tr><th scope="row">Windows</th><td><code>%APPDATA%/Axcess/data/</code></td></tr>
          <tr><th scope="row">Linux</th><td><code>~/.config/Axcess/data/</code></td></tr>
        </tbody>
      </table>
    </div>
    <p class="small" style="margin-top:1rem">Inside: a single SQLite database that is the source of truth, a <code>blobs</code> folder of images and screenshots, and local logs. Logs include the addresses and titles of the pages scanned. Deleting a report keeps its image and screenshot files. Exported files are snapshots, not the record.</p>
  </div>
</section>

<section>
  <div class="wrap">
    <div class="section-head">
      <span class="eyebrow">Teams and institutions</span>
      <h2>Sharing without giving up local-first</h2>
    </div>
    <div class="grid grid-2">
      <article class="card"><h3>Small team on a private network</h3><p>Axcess can run on an always-on machine for a trusted team, over a LAN or a private mesh such as Tailscale, behind a shared access token. It must never be exposed as an open public service; anyone with access can point a crawler at any site.</p></article>
      <article class="card"><h3>Managed protected scans</h3><p>For sensitive university systems, there is a stricter setup that IT runs. People reach it only through an approved university sign-in, evidence is encrypted and deleted after seven days, and exports are controlled. It needs institutional infrastructure and is off by default.</p></article>
    </div>
  </div>
</section>

<section class="soft" id="accuracy">
  <div class="wrap">
    <div class="section-head">
      <span class="eyebrow">Accuracy</span>
      <h2>What Axcess claims about its own accuracy</h2>
    </div>
    <div class="grid grid-2">
      <article class="card"><h3>A guardrail, not a marketing number</h3><p>We keep a fixed set of made-up examples, each labelled with the right answer, and score recorded results against it. For every kind of check, fewer than 5% of the results it reports may be wrong, and it must find at least 80% of the real problems in the set. Because the examples are made up, this protects the rules for what counts as a Barrier; it does not measure accuracy on real sites.</p></article>
      <article class="card"><h3>What that does not mean</h3><p>It is not a claim that every real website will see the same rate. A real-world accuracy figure would need a fresh, representative sample of real pages, checked independently by at least two accessibility experts. The project says so in writing.</p></article>
    </div>
  </div>
</section>
"""


def get_started() -> str:
    return f"""
<section class="hero hero-compact">
  <div class="wrap">
    <span class="eyebrow">Get started</span>
    <h1>Install Axcess and run <span class="hl">your first scan</span></h1>
    <p class="lede">Install the desktop app, run a small scan of a public site, then try a site behind a sign-in. If you are not a developer, the desktop app is the path for you.</p>
  </div>
</section>

<section>
  <div class="wrap">
    <div class="section-head">
      <span class="eyebrow">Step 1</span>
      <h2>Choose how to install</h2>
    </div>
    <div class="grid grid-2">
      <article class="card card-accent">
        {icon("download")}
        <h3>Desktop app (recommended)</h3>
        <p>One app that bundles everything: the workbench, the browser, both rule engines, and text recognition. No Python, Node, or other developer tools needed.</p>
        <ul class="checks" style="margin:1rem 0">
          <li>macOS on Apple Silicon (M1 and later) and Windows 10 or 11 (64-bit)</li>
          <li>A development preview, published automatically when the app changes</li>
          <li>Free, with no account or sign-in needed to download</li>
        </ul>
        <p class="btn-row"><a class="btn btn-primary" href="{DOWNLOAD_MACOS}">Download for macOS</a> <a class="btn btn-primary" href="{DOWNLOAD_WINDOWS}">Download for Windows</a></p>
        <p class="small" id="latest-release" data-latest-release="{LATEST_RELEASE}">The buttons always fetch the newest build. Release notes and earlier builds are on <a href="{RELEASES}">the releases page</a>.</p>
        <div style="margin-top:1rem">{callout('<strong>Read <a href="#first-launch">the installation steps below</a> before you open the app.</strong> Both macOS and Windows show a warning on first launch that you need to approve.', "callout-maize", "warn")}</div>
      </article>
      <article class="card">
        {icon("cpu")}
        <h3>Run from source (technical)</h3>
        <p>For developers and IT staff on macOS, Linux, or Windows with WSL. Needs Python 3.11 or newer, uv, Node.js 22.22 or newer, and Tesseract.</p>
<pre tabindex="0"><code><span class="c"># clone, then from the repo root:</span>
make setup             <span class="c"># Python deps + Chromium</span>
make migrate           <span class="c"># local database</span>
make alfa-install      <span class="c"># optional second engine</span>
make frontend-build    <span class="c"># build the interface</span>
make run               <span class="c"># open http://127.0.0.1:8765/app/</span></code></pre>
        <p class="small">Contributor setup, quality checks, and team hosting are in <a href="{REPO}/blob/main/CONTRIBUTING.md">the contributing guide</a> and <a href="{DOCS}">the documentation</a>.</p>
      </article>
    </div>
    <h3 id="first-launch" style="margin:2rem 0 .4rem">Desktop app installation steps</h3>
    <p class="small" style="margin-bottom:1rem">The preview is not yet notarized by Apple or code-signed for Windows, so each system shows a warning the first time. The warning is expected for this build. You approve it once, and later launches open normally.</p>
    <div class="grid grid-2">
      <article class="card">
        <h4>On a Mac (Apple Silicon)</h4>
        <ol style="margin:.75rem 0 0;padding-left:1.25rem">
          <li>Select <strong>Download for macOS</strong> and wait for <code>Axcess-macOS-AppleSilicon.dmg</code> to finish downloading.</li>
          <li>Open the downloaded file, then drag <strong>Axcess</strong> into your <strong>Applications</strong> folder.</li>
          <li>Open <strong>Applications</strong> and double-click <strong>Axcess</strong>. macOS says it could not verify the app. Choose <strong>Done</strong>, not <em>Move to Trash</em>.</li>
          <li>Open <strong>System Settings</strong>, choose <strong>Privacy &amp; Security</strong>, and scroll down to the <strong>Security</strong> section.</li>
          <li>Next to the message that Axcess was blocked, choose <strong>Open Anyway</strong>, then confirm with your Mac password or Touch ID.</li>
          <li>Choose <strong>Open</strong> in the final dialog. Axcess starts, and from now on it opens like any other app.</li>
        </ol>
        <p class="small" style="margin-top:.75rem">On macOS 14 (Sonoma) or earlier there is a shortcut: in Applications, right-click <strong>Axcess</strong>, choose <strong>Open</strong>, then choose <strong>Open</strong> again in the dialog.</p>
      </article>
      <article class="card">
        <h4>On Windows 10 or 11</h4>
        <ol style="margin:.75rem 0 0;padding-left:1.25rem">
          <li>Select <strong>Download for Windows</strong> and wait for <code>Axcess-Windows-x64-Setup.exe</code> to finish downloading.</li>
          <li>If your browser says the file is not commonly downloaded, open the download's menu (the three dots) and choose <strong>Keep</strong>, then <strong>Keep anyway</strong>.</li>
          <li>Open the downloaded file. Windows shows a blue <em>Windows protected your PC</em> window.</li>
          <li>Choose <strong>More info</strong>. A <strong>Run anyway</strong> button appears; choose it.</li>
          <li>Wait while Axcess installs. There are no setup screens, and it opens by itself when it is done.</li>
          <li>Next time, open <strong>Axcess</strong> from the Start menu.</li>
        </ol>
        <p class="small" style="margin-top:.75rem">If <strong>Run anyway</strong> does not appear, your computer is managed by your organization and blocks unsigned apps. Ask your IT support to allow it.</p>
      </article>
    </div>
    <div style="margin-top:1.5rem">{callout("<strong>Optional AI checks</strong> need a separately installed local service called Ollama and models you download yourself. Skip this at first: every browser-based check runs without it. <a href='../privacy/'>How the optional AI stays local.</a>", "", "info")}</div>
  </div>
</section>

<section class="soft">
  <div class="wrap">
    <div class="section-head">
      <span class="eyebrow">Step 2</span>
      <h2>Run a small first scan</h2>
      <p class="sub">Start with a public site you are authorized to test and a low page limit. You will get a report quickly and a feel for the tool.</p>
    </div>
    <ol class="steps">
      <li><h3>Select "Create New Scan"</h3><p>It is in the top bar of every screen. Choose the <em>Public website</em> tab.</p></li>
      <li><h3>Paste the address of one section</h3><p>In <em>Site URL</em>, enter something like <code>https://www.example.edu/admissions/</code>. The scan stays inside <em>/admissions/</em>. Leave <em>Crawl the entire host</em>, under <em>Advanced settings</em>, unchecked.</p></li>
      <li><h3>Set "Max pages" to about 25</h3><p>You will find it under <em>Advanced settings</em>. The other defaults are fine, and the browser-based checks need no AI. The <em>Default scan settings</em> card lists exactly which checks will run.</p>
        <p class="tip">Want to watch it work? Turn on "Show the scanning browser window" under Advanced settings.</p></li>
      <li><h3>Start the scan</h3><p>Select <em>Start scan</em>. Progress updates as pages are discovered and tested, and you can select <em>Stop scan</em> at any time.</p></li>
    </ol>
  </div>
</section>

<section id="sign-in">
  <div class="wrap">
    <div class="section-head">
      <span class="eyebrow">Step 3</span>
      <h2>Scan a site behind a sign-in</h2>
      <p class="sub">When you are comfortable, try a site that needs a login. You sign in yourself, so single sign-on and two-factor steps work, and Axcess never sees your password.</p>
    </div>
    <ol class="steps">
      <li><h3>Choose the login tab</h3><p>Select <em>Create New Scan</em>, then the <em>Site with a login or 2FA</em> tab.</p></li>
      <li><h3>Enter where to start</h3><p>In <em>Page to scan after you sign in</em>, enter the HTTPS address of the page you want the scan to start from.</p></li>
      <li><h3>Sign in in the browser window</h3><p>Select <em>Open browser to sign in</em>. A browser window opens. Sign in directly with the site, including any two-factor step.</p></li>
      <li><h3>Start the scan</h3><p>Come back to Axcess and select <em>I’m signed in, start scan</em>. The scan starts from where you landed and stays inside the scope of the address you entered.</p></li>
    </ol>
    <div class="grid grid-3" style="margin-top:1.5rem">
      <article class="card"><h3>What it needs</h3><p>An HTTPS site whose address resolves to a public IP address. Sites on private network addresses cannot be scanned this way.</p></article>
      <article class="card"><h3>What is saved</h3><p>Rendered pages and screenshots of what you signed in to are saved in the local report, unless you choose <em>Don’t store rendered pages</em>. No password or reusable login is saved.</p></article>
      <article class="card"><h3>What is different</h3><p>Login scans do not check robots.txt. They can't run the AI language and motion checks. Image text checks are off unless you turn them on. If Axcess restarts during a scan, start a new login scan.</p></article>
    </div>
  </div>
</section>

<section class="soft">
  <div class="wrap">
    <div class="section-head">
      <span class="eyebrow">Step 4</span>
      <h2>Read your first report</h2>
      <p class="sub">Every result lands in one of three groups: <strong>Barrier</strong>, <strong>Needs review</strong>, or <strong>Informational</strong>. <a href="../faq/#glossary">The glossary explains each one.</a></p>
    </div>
    <div class="grid grid-2">
      <article class="card">{icon("table")}<h3>Start at the Issues tab</h3><p>Issues are sorted with Barriers first, then by priority. Filter by <em>Type</em> or <em>Level</em>, and open <em>About</em> on any row for a quick summary.</p></article>
      <article class="card">{icon("pin")}<h3>Open the evidence</h3><p>An issue's full evidence record shows the pages, the element, the code snippet, and screenshots. For problems found after a click, it names the control, for example "After clicking “Open menu”."</p></article>
      <article class="card">{icon("eye")}<h3>Check what actually ran</h3><p>The Overview tab shows which methods ran and which did not, so you know what the scan covered before you draw conclusions.</p></article>
      <article class="card">{icon("sheet")}<h3>Export and rescan</h3><p>The <em>Export</em> menu offers an Excel workbook, an audit report, CSV, and JSON. After fixes land, scan again and use <em>Verify changes</em> to compare.</p></article>
    </div>
    <p style="margin-top:1.25rem">The full walkthrough, including every column and export, is in <a href="{REPO}/blob/main/docs/reading-your-report.md">Reading your Axcess report</a>.</p>
  </div>
</section>

<section>
  <div class="wrap">
    <div class="section-head">
      <span class="eyebrow">Good to know</span>
      <h2>Before you scan</h2>
    </div>
    <div class="grid grid-3">
      <article class="card"><h3>Authorization</h3><p>Scan only the sites and accounts you have permission to test. If you choose to ignore robots.txt, that choice is saved with the scan. Axcess refuses to press controls named sign out, delete, or unsubscribe.</p></article>
      <article class="card"><h3>One scan at a time</h3><p>Axcess runs one scan at a time. Start the next scan when the first one finishes.</p></article>
      <article class="card" id="speed"><h3>Speed and coverage</h3><p>By default, Axcess renders each page in a real browser and checks it several ways, so large scans take a while. Advanced settings let you turn off individual checks when speed matters more.</p></article>
    </div>
  </div>
</section>
"""


def faq(summ) -> str:
    def q(question: str, answer: str, anchor: str = "") -> str:
        id_attr = f' id="{anchor}"' if anchor else ""
        return f'<details{id_attr}><summary>{question}</summary><div class="a">{answer}</div></details>'

    total, covered, manual = summ.total, summ.covered, summ.manual_only
    faqs = "".join(
        [
            q(
                "Does Axcess certify that my website is accessible?",
                "<p>No. Axcess gives you evidence to review. It can't certify WCAG conformance or prove legal compliance, and it doesn't replace testing with people who use assistive technology. An accessibility specialist can use its evidence when writing a conformance report.</p>",
            ),
            q(
                "What do Barrier, Needs review, and Informational mean?",
                '<p>They are the three report groups, and every result lands in one of them. The glossary below defines <a href="#barrier">Barrier</a>, <a href="#needs-review">Needs review</a>, and <a href="#informational">Informational</a>, and <a href="../coverage/#groups">What Axcess checks</a> shows which checks feed each group.</p>',
            ),
            q(
                "How is Axcess different from Siteimprove or axe DevTools?",
                '<p>We use and like both. Siteimprove monitors whole sites from the cloud, and the axe DevTools browser extension checks the page in front of you. Axcess runs on your computer, scans behind a sign-in including two-factor steps, opens menus and dialogs by itself, and adds browser checks such as reflow and text spacing. <a href="../coverage/#compare">See the side-by-side comparison.</a></p>',
            ),
            q(
                "Do I need AI to use it?",
                "<p>No. The rule engines and the keyboard, zoom, focus, and click-through checks need only a browser, which the desktop app includes. AI-assisted checks are optional, run on a local model you install yourself, and are never reported as Barriers.</p>",
            ),
            q(
                "Does any of my data go to the cloud?",
                '<p>No. There is no account, no telemetry, and no upload. Axcess connects to the website you are scanning and, if you install one, a local AI service on the same machine. The desktop app also checks GitHub once per launch for a newer version, and that request carries no scan data. <a href="../privacy/">Read the privacy page.</a></p>',
            ),
            q(
                "Can it scan pages behind a login or two-factor sign-in?",
                "<p>Yes. You sign in directly with the website in a browser window that Axcess opens, and the scan continues with that session. Axcess never sees your password or code. The site must use HTTPS and a public address, and you need permission to test it.</p>",
            ),
            q(
                f'What does "{covered} of {total} criteria" mean?',
                f'<p>Axcess has at least one check that gives evidence for {covered} of the {total} WCAG 2.2 Level A and AA success criteria. That does not mean those {covered} are decided without a person, and it does not mean a site that passes them conforms. The remaining {manual} are listed as manual, with the steps to test each one. <a href="../coverage/#explorer">See all {total} success criteria.</a></p>',
            ),
            q(
                "How accurate is it?",
                "<p>Every result carries its method and report group, so you can see how certain it is, and you can mark any result as a false positive with a reason. Only rule-engine failures are reported as Barriers; everything else waits for a person. The project also tests its checks against a set of made-up examples. That test is a safety rail, not a measure of accuracy on real sites. <a href=\"../privacy/#accuracy\">How we measure accuracy.</a></p>",
            ),
            q(
                "How long does a scan take?",
                "<p>It depends on how many pages you scan and which checks you turn on. Start with about 25 pages and grow from there. <a href=\"../get-started/#speed\">Speed and coverage tips.</a></p>",
            ),
            q(
                "Will it break anything on the site?",
                "<p>Axcess reads pages and, unless you turn it off, operates visible controls such as menus and tabs. While it clicks, the click-through:</p>"
                "<ul><li>never follows links to other addresses</li>"
                "<li>refuses controls named sign out, delete, remove, unsubscribe, submit, save, and similar words</li>"
                "<li>blocks form submissions and other changes</li>"
                "<li>undoes navigations</li>"
                "<li>stops after a fixed number of clicks per page</li></ul>"
                "<p>It is a safety net, not a guarantee, so use a test or staging copy of a site when you can. Public scans respect robots.txt by default.</p>",
                "will-it-break-anything",
            ),
            q(
                "Does it work on single-page apps built with React, Vue, or Angular?",
                "<p>Yes. By default, Axcess renders each page in a real browser before testing, follows app-style routes as separate pages, and can open menus and dialogs that only appear after a click. Routes must be reachable by real links inside your scope; Axcess does not read application code to guess private addresses.</p>",
            ),
            q(
                "Can several people use one Axcess?",
                "<p>A small trusted team can share one instance on an always-on machine over a private network with a shared access token. It runs one scan at a time and must not be exposed to the public internet. Larger, stricter institutional deployments are described in the documentation.</p>",
            ),
            q(
                "What does it cost, and who maintains it?",
                "<p>Axcess is free and open source under the MIT license. It was built at the University of Michigan's College of Literature, Science, and the Arts. The source, documentation, and white paper are on GitHub.</p>",
            ),
            q(
                "Which platforms are supported?",
                "<p>The desktop preview is available for Apple Silicon Macs and 64-bit Windows. From source, Axcess runs on macOS, Linux, and Windows with WSL. A Linux desktop installer is part of the build system but is not yet released as a preview.</p>",
            ),
        ]
    )

    glossary = "".join(
        f'<h3 style="margin:2rem 0 .75rem">{e(section)}</h3><dl class="glossary">'
        + "".join(f'<div id="{_slug(term)}"><dt>{e(term)}</dt><dd>{definition}</dd></div>' for term, definition in terms)
        + "</dl>"
        for section, terms in load_glossary()
    )

    return f"""
<section class="hero hero-compact">
  <div class="wrap">
    <span class="eyebrow">Questions and glossary</span>
    <h1>Straight answers, <span class="hl">plain words</span></h1>
    <p class="lede">The questions people ask before they trust a tool, and the words you will meet in an Axcess report.</p>
  </div>
</section>

<section id="questions">
  <div class="wrap">
    <div class="section-head">
      <span class="eyebrow">FAQ</span>
      <h2>Common questions</h2>
    </div>
    <div class="faq">{faqs}</div>
  </div>
</section>

<section class="soft" id="glossary">
  <div class="wrap">
    <div class="section-head">
      <span class="eyebrow">Glossary</span>
      <h2>Words you'll see in a report</h2>
      <p class="sub">These definitions come from <a href="{GLOSSARY_URL}">the Axcess glossary</a> in the project documentation, so the site and the documentation always say the same thing.</p>
    </div>
{glossary}
  </div>
</section>
"""


def volume_page() -> str:
    section = volume_section(load_volume())
    if not section:
        section = """
<section><div class="wrap"><p class="sub">No volume snapshot is available in this build. Run <code>uv run python site/volume.py</code> on a machine with scan data, then rebuild.</p></div></section>"""
    return f"""
<section class="hero hero-compact">
  <div class="wrap">
    <span class="eyebrow">Reference</span>
    <h1>Coverage by <span class="hl">volume</span></h1>
    <p class="lede">Counting criteria says what Axcess can look for. Counting what it found says where the work is. This page aggregates the completed scans on the development machine, with no page addresses or site names. It is a reference view and is not linked from the main site.</p>
  </div>
</section>
{section}
"""


def about(summ) -> str:
    return f"""
<section class="hero hero-compact">
  <div class="wrap">
    <span class="eyebrow">About Axcess</span>
    <h1>Evidence <span class="hl">before</span> verdicts</h1>
    <p class="lede">Axcess started with one hard problem and grew into a way of working. This is the story, the idea that guides it, and where it is heading.</p>
  </div>
</section>

<section>
  <div class="wrap narrow">
    <div class="section-head">
      <span class="eyebrow">The beginning</span>
      <h2>One problem nobody's scanner could solve</h2>
    </div>
    <p>An accessibility lead at the University of Michigan needed to find every image that was really just a picture of text, across an entire website, before the next reporting cycle. Text inside an image cannot be resized, restyled, or read aloud, and existing tools could not find it reliably at scale. Checking every page and image by hand was slow, repetitive, and easy to get wrong.</p>
    <p>The first version of Axcess did exactly that job. It crawled a site without sending anything to the cloud, found the images, read the text inside them, compared it with the alternative text on the page, and ranked the likely problems for a person to review. Then it could scan again to confirm the fixes.</p>
    <p>The intent was never to remove the expert. It was to take away the repetitive discovery work and hand the expert better evidence.</p>
  </div>
</section>

<section class="soft">
  <div class="wrap narrow">
    <div class="section-head">
      <span class="eyebrow">How it grew</span>
      <h2>Finding a problem is only the first question</h2>
    </div>
    <p>A raw result does not answer what people actually ask. What happened? Who is affected? Which pages? How certain is it? What should change? How will we know it is fixed?</p>
    <p>So Axcess became an evidence workbench. New checks were added for page structure, names and roles, keyboard behaviour, focus, small screens, media, and meaning. A manual evaluation workflow was added because many accessibility questions cannot honestly be answered by software. And the product became explicit about uncertainty: a rule failure, an observed behaviour, and an AI suggestion are never treated as equally certain, and each keeps the name of the method that produced it.</p>
    <p>The guiding idea is simple: <strong>preserve the evidence before presenting a verdict.</strong></p>
  </div>
</section>

<section>
  <div class="wrap">
    <div class="section-head">
      <span class="eyebrow">Principles</span>
      <h2>What the project holds itself to</h2>
    </div>
    <div class="grid grid-2">
      <article class="card">{icon("shield")}<h3>Honest coverage</h3><p>Axcess contributes evidence to {summ.covered} of {summ.total} WCAG 2.2 A/AA criteria, and says so. Every public number comes from the same file the product reads, so a claim can never drift from the code.</p></article>
      <article class="card">{icon("lock")}<h3>Private by default</h3><p>Evidence stays on the auditor's computer. No telemetry, no cloud AI, no account. Sensitive and login-protected pages deserve nothing less.</p></article>
      <article class="card">{icon("person")}<h3>Universal design first</h3><p>The tool's own interface is held to WCAG 2.2 AAA and designed around an accessibility professional who may use a screen reader, magnification, or keyboard only. When efficiency and universal design pull apart, universal design wins.</p></article>
      <article class="card">{icon("check")}<h3>Human decisions, recorded</h3><p>Automated results are input, not output. People confirm, reject, and remediate, with reasons and history, and the report says what was and was not evaluated.</p></article>
    </div>
  </div>
</section>

<section class="band">
  <div class="wrap">
    <div class="section-head">
      <span class="eyebrow">Direction</span>
      <h2>Where Axcess is heading</h2>
      <p class="sub">The project's white paper lays out its long-term direction: an offline, evidence-first accessibility quality system, grounded in the W3C's evaluation methodology and ACT rule format.</p>
    </div>
    <div class="grid grid-3">
      <article class="card"><h3>Truthful, inspectable coverage</h3><p>Record exactly what happened for every page, state, and method. "Found nothing", "skipped", and "unavailable" must never look the same.</p></article>
      <article class="card"><h3>Test experiences, not just URLs</h3><p>Safe, user-authorised journey recipes so the states after a click, a form error, or a sign-in are tested too.</p></article>
      <article class="card"><h3>Issues as durable work</h3><p>Separate what was observed, what people decided, what was remediated, and what a comparison showed.</p></article>
      <article class="card"><h3>The report as the product</h3><p>A self-contained, accessible HTML report that works without Axcess running and answers what was evaluated, what was not, and what to fix first.</p></article>
      <article class="card"><h3>"Fully offline", defined</h3><p>A private live scan that touches only the target, and an air-gapped replay mode that touches nothing.</p></article>
      <article class="card"><h3>Validation before promotion</h3><p>Every new detector measured against expert-reviewed real-world examples before it is trusted.</p></article>
    </div>
    <p style="margin-top:1.5rem"><a class="btn btn-maize" href="{WHITEPAPER}">Read the white paper</a></p>
  </div>
</section>

<section>
  <div class="wrap">
    <div class="section-head">
      <span class="eyebrow">Open source</span>
      <h2>Built in the open at the University of Michigan</h2>
      <p class="sub">Axcess is MIT licensed and developed by the LSA Technology Services team at the University of Michigan's College of Literature, Science, and the Arts. The crawler, evidence store, interface, and exports are all public.</p>
    </div>
    <div style="display:flex;gap:.8rem;flex-wrap:wrap">
      <a class="btn btn-primary" href="{REPO}">Source on GitHub</a>
      <a class="btn btn-ghost" href="{DOCS}">Documentation</a>
      <a class="btn btn-ghost" href="../get-started/">Get started</a>
    </div>
  </div>
</section>
"""


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------


def render_all() -> dict[str, str]:
    crit, summ, cov = coverage_data()
    bodies = {
        "": home(summ),
        "how-it-works": how_it_works(summ),
        "coverage": coverage(crit, summ, cov),
        "who-its-for": who_its_for(),
        "privacy": privacy(),
        "get-started": get_started(),
        "faq": faq(summ),
        "about": about(summ),
        "volume": volume_page(),
    }
    return {slug: shell(BY_SLUG[slug], body) for slug, body in bodies.items()}


def main() -> None:
    for slug, doc in render_all().items():
        out = SITE / "index.html" if slug == "" else SITE / slug / "index.html"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(doc, encoding="utf-8")
        print(f"wrote {out.relative_to(ROOT)} ({out.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
