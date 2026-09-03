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
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"
sys.path.insert(0, str(ROOT / "src"))

BASE_URL = "https://lsa-mis.github.io/axcess/"
REPO = "https://github.com/lsa-mis/axcess"
DESKTOP_BUILDS = (
    "https://github.com/lsa-mis/axcess/actions/workflows/desktop-build.yml"
    "?query=branch%3Afeature%2Felectron-desktop"
)
WHITEPAPER = f"{REPO}/blob/main/whitepaper/AXCESS-WHITE-PAPER.md"
DOCS = f"{REPO}/tree/main/docs"
PORTFOLIO = "https://reganmaharjan.com.np/"


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
        "Local-first accessibility evidence for websites. Scan a site you're authorized to test, see what was found and why it matters, and hand your team a clear list of fixes. Everything stays on your computer.",
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
        "An honest, searchable map of all 55 WCAG 2.2 A and AA success criteria: what Axcess checks for you and what a person still needs to test.",
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
        "Straight answers to common questions about Axcess, plus a plain-language glossary of the words you'll see in a report.",
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
    "mark": (
        '<svg class="mark" viewBox="0 0 32 32" role="img" aria-label="Axcess logo" focusable="false">'
        '<rect width="32" height="32" rx="7" fill="#00274C"/>'
        '<text x="16" y="22" text-anchor="middle" fill="#FFCB05" font-family="Arial, Helvetica, sans-serif" font-size="18" font-weight="800">Ax</text></svg>'
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
    idx = JOURNEY.index(page.slug)
    prev_slug = JOURNEY[idx - 1] if idx > 0 else None
    next_slug = JOURNEY[idx + 1] if idx < len(JOURNEY) - 1 else None
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
        "Axcess — local-first accessibility evidence"
        if page.slug == ""
        else f"{page.title} — Axcess"
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
<meta property="og:image" content="{BASE_URL}assets/axcess-dashboard-redacted.png">
<meta name="twitter:card" content="summary_large_image">
<meta name="theme-color" content="#00274C">
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
          <li><a href="{href("faq")}">Questions and glossary</a></li>
        </ul>
      </div>
      <div>
        <h2>Use</h2>
        <ul>
          <li><a href="{href("get-started")}">Get started</a></li>
          <li><a href="{href("privacy")}">Privacy and trust</a></li>
          <li><a href="{DESKTOP_BUILDS}">Desktop preview builds</a></li>
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
      <span>A project by <a href="{PORTFOLIO}">Regan Maharjan</a> at U-M LSA</span>
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
    "<strong>What Axcess is not.</strong> Axcess produces accessibility evidence for a qualified person to review. "
    "Automated and AI-assisted results do not prove WCAG conformance, legal compliance, or the accessibility of an "
    "entire website, and they do not replace testing with people who use assistive technology."
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


def home(summ, shipped_ct: int, ai_ct: int) -> str:
    total, covered, manual = summ.total, summ.covered, summ.manual_only
    return f"""
<section class="hero">
  <div class="wrap hero-grid">
    <div>
      <span class="eyebrow">Local-first · WCAG 2.2 A/AA evidence · Free and open source</span>
      <h1>Find accessibility barriers. <span class="hl">Keep the evidence.</span> Fix what matters.</h1>
      <p class="lede">Axcess scans a website you're authorized to test, shows you exactly what it found and why it matters, and gives your team a clear list of fixes. Everything stays on your computer.</p>
      <div class="cta">
        <a class="btn btn-maize" href="how-it-works/">See how it works</a>
        <a class="btn btn-ghost" href="get-started/">Get started</a>
      </div>
      <p class="meta">Works with public sites and sites behind a login. Runs with <strong>no AI at all</strong>, or add a local model for the judgement calls. <strong>Nothing is uploaded.</strong></p>
    </div>
    <div aria-hidden="true">
      <div class="issue-card">
        <div class="chips">
          <span class="chip chip-plain"><span class="sc">1.4.3</span>&nbsp;Contrast (Minimum)</span>
          <span class="chip chip-level">Level AA</span>
          <span class="chip chip-automated">Rule engine</span>
        </div>
        <h3>Body text is too light to read against its background</h3>
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
      <span class="eyebrow">In one minute</span>
      <h2>Scan. Review. Fix and verify.</h2>
      <p class="sub">Axcess is organised around the way an accessibility professional actually works, from the first web address to the follow-up scan that proves a fix landed.</p>
    </div>
    <ol class="steps steps-flow">
      <li>
        <h3>Scan a site</h3>
        <p>Paste a web address, set how many pages to visit, and watch the scan run in a real browser. Sign in yourself if the site is behind a login.</p>
      </li>
      <li>
        <h3>Review clear issues</h3>
        <p>Every issue answers four questions: what is wrong, why it matters, what the fix looks like, and exactly where it is. Repeated problems are grouped so you fix the cause once.</p>
      </li>
      <li>
        <h3>Hand off and verify</h3>
        <p>Export an Excel workbook, a stakeholder report, or Jira tickets. Rescan later to see what is new, what is resolved, and what is still open.</p>
      </li>
    </ol>
  </div>
</section>

<section class="soft">
  <div class="wrap">
    <div class="section-head">
      <span class="eyebrow">The workbench</span>
      <h2>An evidence workbench, not a scorecard</h2>
      <p class="sub">One score hides the details that make accessibility work actionable. Axcess keeps the page, the element, the screenshot, the rule, and the confidence level connected so anyone can check a claim for themselves.</p>
    </div>
    <div class="shot-frame">
      <img class="shot" src="assets/axcess-dashboard-redacted.png" width="1487" height="1058"
        alt="The Axcess dashboard. A navy banner reads 'View 5 accessibility issue groups' with an 'Open issue table' button. Below are counters for completed scans, pages crawled, and image evidence, a list of recent scans (blurred), and a panel titled 'How Axcess works' listing: understand the issue, apply the expected fix, open the exact location.">
    </div>
    <p class="caption">The dashboard of the desktop app. Recent scan targets are blurred in this preview.</p>
  </div>
</section>

<section>
  <div class="wrap">
    <div class="section-head">
      <span class="eyebrow">Why teams trust it</span>
      <h2>Honest by design</h2>
      <p class="sub">Accessibility tools are easy to over-trust. Axcess is built to tell you what it saw, how sure it is, and what it could not check.</p>
    </div>
    <div class="stats" role="list">
      <div class="stat" role="listitem"><b>{covered}<small> of {total}</small></b><span>WCAG 2.2 A/AA criteria where Axcess contributes evidence. The other {manual} are labelled manual, with instructions.</span></div>
      <div class="stat" role="listitem"><b>0</b><span>Bytes of scan data sent to a cloud service. There is no telemetry and no account.</span></div>
      <div class="stat" role="listitem"><b>AAA</b><span>The level Axcess holds its own interface to. Every screen is tested for keyboard, screen reader, zoom, and contrast.</span></div>
      <div class="stat" role="listitem"><b>{shipped_ct}</b><span>Independent checks per scan. {shipped_ct - ai_ct} need only a browser; {ai_ct} can add a local AI model.</span></div>
    </div>
    <div class="grid grid-2" style="margin-top:1.5rem">
      <article class="card">{icon("pin")}<h3>Evidence you can inspect</h3><p>Every finding links back to the page, the element, a snippet, and often a screenshot, stored locally with the scan. Nothing is a bare number.</p></article>
      <article class="card">{icon("shield")}<h3>Clear about certainty</h3><p>A deterministic rule failure, a behaviour the browser observed, and an AI suggestion are never mixed. Each result says which method produced it and whether a person still needs to confirm it.</p></article>
      <article class="card">{icon("lock")}<h3>Private by default</h3><p>Scans, screenshots, and reports live in a local database on your computer. Sites behind a login are scanned after you sign in yourself; Axcess never sees your password.</p></article>
      <article class="card">{icon("click")}<h3>Built for real, modern websites</h3><p>Pages are rendered in a real browser, so single-page apps work. Axcess can also open menus, tabs, and dialogs to test the states a plain page load never shows.</p></article>
    </div>
  </div>
</section>

<section class="band">
  <div class="wrap">
    <div class="section-head">
      <span class="eyebrow">What you get</span>
      <h2>Reports people can actually use</h2>
      <p class="sub">The same local evidence becomes whatever your audience needs, from a triage table for you to a ticket for a developer to a summary for a director.</p>
    </div>
    <div class="grid grid-3">
      <article class="card">{icon("table")}<h3>Issue table</h3><p>One scan-scoped table that groups repeated problems and states both numbers plainly, for example 19 issue groups across 965 occurrences.</p></article>
      <article class="card">{icon("sheet")}<h3>Excel workbook</h3><p>The hand-off file: Summary, Issues, Page Hotspots, Who's Affected, Coverage, Test Tracking, and Manual Evidence sheets with clickable links.</p></article>
      <article class="card">{icon("doc")}<h3>Stakeholder report</h3><p>Scope, methods, limitations, results, recommended actions, and verification steps, written for readers who will never open the tool.</p></article>
      <article class="card">{icon("download")}<h3>Tickets and data</h3><p>Jira-ready CSV, plain CSV, and JSON so findings drop straight into the tools your team already uses.</p></article>
      <article class="card">{icon("refresh")}<h3>Rescan comparison</h3><p>Scan the same scope again and see what is new, what is resolved, and what is still open, instead of starting from zero.</p></article>
      <article class="card">{icon("check")}<h3>Draft protection</h3><p>A report exported before expert review is complete is clearly labelled DRAFT, so an unfinished list is never mistaken for a final audit.</p></article>
    </div>
  </div>
</section>

<section>
  <div class="wrap">
    <div class="section-head">
      <span class="eyebrow">Who it's for</span>
      <h2>Made for the people who do the work</h2>
    </div>
    <div class="grid grid-4">
      <a class="card card-accent" href="who-its-for/#accessibility-lead" style="text-decoration:none">{icon("person")}<h3>Accessibility leads</h3><p>Triage hundreds of findings in one sitting, defend every verdict, and verify fixes on rescan.</p></a>
      <a class="card card-accent" href="who-its-for/#editors-and-developers" style="text-decoration:none">{icon("people")}<h3>Editors and developers</h3><p>Get a ticket that says what to change, where, and how you'll know it's done.</p></a>
      <a class="card card-accent" href="who-its-for/#leadership" style="text-decoration:none">{icon("chart")}<h3>Leadership</h3><p>See how thoroughly a site was evaluated and what to fix first, without a misleading score.</p></a>
      <a class="card card-accent" href="who-its-for/#it-and-security" style="text-decoration:none">{icon("server")}<h3>IT and security</h3><p>Review a tool with no cloud dependency, no telemetry, and a documented data boundary.</p></a>
    </div>
  </div>
</section>

<section class="soft">
  <div class="wrap">
    {callout(HONESTY, "callout-maize", "warn")}
    <div style="display:flex;gap:.8rem;flex-wrap:wrap;margin-top:2rem;align-items:center">
      <a class="btn btn-primary" href="get-started/">Get started</a>
      <a class="btn btn-ghost" href="coverage/">Explore what it checks</a>
      <a class="btn btn-ghost" href="about/">Read the story</a>
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
        <p>Pick a public website, or choose <em>Login or 2FA website</em> for a site that needs a sign-in. For a protected site, Axcess opens a visible browser window and you sign in yourself, with your password, passkey, or one-time code. Axcess never asks for any of them.</p>
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
        <p>One table lists every issue and answers four questions: <strong>What is the issue? Why does it matter? What is the expected fix? Where exactly is it?</strong> Repeated occurrences are grouped so a single cause is fixed once.</p>
      </li>
      <li>
        <h3>Open the evidence</h3>
        <p>Follow any issue to the page, the element, the snippet, the rule, or the screenshot that produced it. Everything is stored with the scan, so a claim can be checked months later.</p>
      </li>
      <li>
        <h3>Export and verify</h3>
        <p>Record your decisions, export the workbook or report, assign the work, and rescan when fixes land. The comparison shows what is new, resolved, and still open.</p>
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
      <article class="card">{icon("layers")}<h3>Second opinion</h3><p>Optionally, Siteimprove's independent Alfa engine takes its own look. Where the two engines agree or disagree is visible, which helps you judge how solid a result is.</p><p><span class="chip chip-automated">Deterministic</span></p></article>
      <article class="card">{icon("keyboard")}<h3>Keyboard check</h3><p>Axcess presses Tab and Shift+Tab through each page looking for places where keyboard users get stuck. It is deliberately cautious: ordinary focus loops and dialogs are not reported as traps.</p><p><span class="chip chip-partial">Browser-observed</span></p></article>
      <article class="card">{icon("phone")}<h3>Zoom and reflow check</h3><p>Each page is squeezed to a phone-width view, zoomed to about 200%, and given wider text spacing to see whether anything is cut off or overlaps.</p><p><span class="chip chip-partial">Browser-observed</span></p></article>
      <article class="card">{icon("eye")}<h3>Focus check</h3><p>Finds keyboard focus hidden behind sticky headers or banners, and tab orders that were forced out of sequence.</p><p><span class="chip chip-partial">Browser-observed</span></p></article>
      <article class="card">{icon("click")}<h3>Click through states</h3><p>Axcess can open menus, tabs, and dialogs and re-run the rule engine on what appears. It never clicks links, never presses anything named sign out, delete, or unsubscribe, and stops after a bounded number of clicks per page.</p><p><span class="chip chip-automated">Deterministic</span></p></article>
      <article class="card">{icon("image")}<h3>Image text check</h3><p>Text hidden inside pictures is invisible to screen readers and cannot be resized. Built-in text recognition finds it; an optional local vision model judges whether the image is really just text.</p><p><span class="chip chip-ai">AI-assisted lead</span></p></article>
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
      <p class="sub">Not all findings are equally certain, and Axcess never pretends they are. Results travel in three separate lanes, and a lead can never silently become a confirmed barrier.</p>
    </div>
    <div class="lanes">
      <div class="lane lane-automated">
        <span class="chip chip-automated">Likely barrier</span>
        <h3>Deterministic rule failures</h3>
        <p>A rule engine measured something on the rendered page and it failed. High confidence, though a person still verifies the fix.</p>
      </div>
      <div class="lane lane-observed">
        <span class="chip chip-partial">Review lead</span>
        <h3>Browser-observed behaviour</h3>
        <p>Axcess operated the page and saw something suspicious, such as focus that would not leave an element. The evidence is real; the interpretation needs an expert.</p>
      </div>
      <div class="lane lane-ai">
        <span class="chip chip-ai">Needs confirmation</span>
        <h3>AI-assisted suggestions</h3>
        <p>A local model made a judgement call. These are strong leads, clearly labelled, and always confirmed or rejected by a person before they count.</p>
      </div>
    </div>
    <div style="margin-top:1.5rem">{callout("<strong>Decisions are recorded, not just made.</strong> Each issue group can be accepted, rejected as a false positive, marked remediated, or kept open as an accepted risk, with a written rationale and a history of who decided what and when.", "", "check")}</div>
  </div>
</section>

<section class="soft">
  <div class="wrap">
    <div class="section-head">
      <span class="eyebrow">Modern websites</span>
      <h2>Works with apps, not just pages</h2>
      <p class="sub">Many sites today are applications built with React, Vue, Angular, or similar frameworks. A traditional crawler sees an empty shell. Axcess renders every page in a real browser first.</p>
    </div>
    <div class="grid grid-2">
      <article class="card"><h3>Routes are discovered by following real links</h3><p>Axcess follows links it can see on rendered pages, including app-style routes, and stays inside the scope you set. It does not guess private addresses or read application code.</p></article>
      <article class="card"><h3>States are counted separately from pages</h3><p>When Axcess opens a menu or dialog and tests what appears, it reports that as a DOM state alongside the page count, not folded into it. A page count alone would undersell an app; counting states as pages would oversell the crawl.</p></article>
      <article class="card"><h3>Interaction is bounded and safe</h3><p>Links are never clicked by the probe. Controls named sign out, delete, remove, unsubscribe, or deactivate are refused. Each page is capped at 40 clicks and two levels of newly revealed controls.</p></article>
      <article class="card"><h3>Some things still need a person</h3><p>Hover-only content, gestures, operating-system menus, embedded third-party widgets, and states without a visible change on the page are outside what the probe can see. The report says so.</p></article>
    </div>
  </div>
</section>

<section>
  <div class="wrap">
    <div class="section-head">
      <span class="eyebrow">Follow-up</span>
      <h2>Rescan and compare</h2>
      <p class="sub">A fix is only real when a later scan shows it. Run the same scope again and Axcess lines the two reports up.</p>
    </div>
    <div class="grid grid-3">
      <article class="card"><h3>New</h3><p>Barriers seen now that were not in the earlier scan.</p></article>
      <article class="card"><h3>Resolved</h3><p>Barriers from the earlier scan that are no longer observed under the same scope and checks.</p></article>
      <article class="card"><h3>Still open</h3><p>Barriers present in both scans, so the work is not finished yet.</p></article>
    </div>
    <p class="small" style="margin-top:1.25rem">"Not found this time" is not automatically "fixed". Axcess compares the same scope and methods, and a confirmed fix should still pass a retest or a human check.</p>
  </div>
</section>

<section class="soft">
  <div class="wrap">
    {callout(HONESTY, "callout-maize", "warn")}
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
            pipes_html = (
                '<div class="pipes"><span>Checks involved:</span>'
                + "".join(
                    f'<span class="chip chip-plain">{e(PIPE_NAMES.get(p, p))}</span>'
                    for p in c.pipelines
                )
                + f"<span>· Confidence: {e(c.confidence)}</span></div>"
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
        f"<tr><td><b>Level {lvl}</b></td><td>{sum(by_level[lvl].values())}</td><td>{by_level[lvl]['automated']}</td><td>{by_level[lvl]['partial']}</td><td>{by_level[lvl]['ai-assisted']}</td><td>{by_level[lvl]['manual']}</td><td><b>{sum(by_level[lvl].values()) - by_level[lvl]['manual']}</b></td></tr>"
        for lvl in ("A", "AA")
    )

    return f"""
<section class="hero hero-compact">
  <div class="wrap">
    <span class="eyebrow">Coverage</span>
    <h1>What Axcess checks, and what it <span class="hl">honestly can't</span></h1>
    <p class="lede">The Web Content Accessibility Guidelines (WCAG) 2.2 define {total} Level A and AA success criteria. Axcess contributes evidence to {summ.covered} of them today. Every one of the {total} is listed below, including the {summ.manual_only} a person must test by hand, with the steps to do it.</p>
  </div>
</section>

<section>
  <div class="wrap">
    <div class="section-head">
      <span class="eyebrow">At a glance</span>
      <h2>{summ.covered} of {total} criteria with Axcess evidence</h2>
      <p class="sub">These numbers are generated from the same file the product reads, so this page, the in-app Tracking screen, and the documentation can never disagree.</p>
    </div>
    <div class="covbar" role="img" aria-label="Of {total} criteria: {bm["automated"]} automated, {bm["partial"]} partly automated, {bm["ai-assisted"]} AI-assisted, {bm["manual"]} manual only.">{bar}</div>
    <div class="legend" aria-hidden="true">{legend}</div>
    <div class="lanes lanes-4">{buckets}</div>
    <div class="table-wrap" style="margin-top:1.75rem" tabindex="0">
      <table>
        <caption class="vis-hidden">Coverage by WCAG conformance level</caption>
        <thead><tr><th scope="col">Level</th><th scope="col">Criteria</th><th scope="col">Automated</th><th scope="col">Partly automated</th><th scope="col">AI-assisted</th><th scope="col">Manual only</th><th scope="col">With Axcess evidence</th></tr></thead>
        <tbody>{level_rows}<tr><td><b>A + AA</b></td><td>{total}</td><td>{bm["automated"]}</td><td>{bm["partial"]}</td><td>{bm["ai-assisted"]}</td><td>{bm["manual"]}</td><td><b>{summ.covered}</b></td></tr></tbody>
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
    <div class="boundary">
      <span class="tag">Stays on your computer</span>
      <div class="inner">
        <div><strong>Scan evidence</strong><span>Pages, elements, snippets, screenshots, and image files, stored in a local database.</span></div>
        <div><strong>Your decisions</strong><span>Every review outcome, rationale, and status change, with its history.</span></div>
        <div><strong>Reports and exports</strong><span>Workbooks, reports, and ticket files are written to your disk and go only where you send them.</span></div>
        <div><strong>The browser</strong><span>A bundled Chromium renders pages locally, including the visible window you sign in with.</span></div>
        <div><strong>Text recognition</strong><span>Bundled OCR reads text inside images on your machine.</span></div>
        <div><strong>Optional AI</strong><span>If you choose to install a local model through Ollama, it runs on this computer too.</span></div>
      </div>
    </div>
    <div class="outside">
      <div><strong>Connects to: the website you are scanning</strong><span>Axcess necessarily loads pages from the target site, at the rate you set, respecting robots.txt unless you say otherwise.</span></div>
      <div><strong>Connects to: nothing else</strong><span>No telemetry, no usage analytics, no update checks that carry data, no cloud AI. Any external integration would require an explicit administrator decision.</span></div>
    </div>
  </div>
</section>

<section class="soft">
  <div class="wrap">
    <div class="section-head">
      <span class="eyebrow">Protected sites</span>
      <h2>Scanning behind a login without sharing your password</h2>
      <p class="sub">Many of the pages that matter most are behind a sign-in. Axcess handles this the safe way: you sign in, it watches.</p>
    </div>
    <ol class="steps">
      <li><h3>Choose "Login or 2FA website"</h3><p>Enter the application address you are authorized to test and, if needed, the sign-in addresses it uses.</p></li>
      <li><h3>Axcess opens a visible browser window</h3><p>This is a normal Chromium window on your screen.</p></li>
      <li><h3>You sign in directly with the website</h3><p>Password, passkey, push notification, one-time code, whatever the site requires. Nothing is typed into Axcess.</p></li>
      <li><h3>Navigate to the approved page and confirm</h3><p>Select <em>I have signed in</em>. Axcess checks the page is inside the agreed scope.</p></li>
      <li><h3>The scan uses that live session</h3><p>The session exists only in memory and ends with the scan. Login and identity-provider pages are not stored as evidence.</p></li>
    </ol>
    <div style="margin-top:1.5rem">{callout("<strong>This is not a way around authentication.</strong> Axcess only continues where you have already signed in, with accounts and sites you are explicitly authorized to test.", "callout-maize", "lock")}</div>
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
    <div class="table-wrap" tabindex="0">
      <table>
        <caption class="vis-hidden">Data locations by operating system</caption>
        <thead><tr><th scope="col">Operating system</th><th scope="col">Data folder</th></tr></thead>
        <tbody>
          <tr><td><b>macOS</b></td><td><code>~/Library/Application Support/Axcess/data/</code></td></tr>
          <tr><td><b>Windows</b></td><td><code>%APPDATA%/Axcess/data/</code></td></tr>
          <tr><td><b>Linux</b></td><td><code>~/.config/Axcess/data/</code></td></tr>
        </tbody>
      </table>
    </div>
    <p class="small" style="margin-top:1rem">Inside: a single SQLite database that is the source of truth, an <code>blobs</code> folder of image evidence, and local logs. Exported files are snapshots, not the record.</p>
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
      <article class="card"><h3>Managed protected scans</h3><p>For sensitive institutional targets the project includes a stricter design: identity-aware access, a scan-bound companion, managed-key encryption, redaction, seven-day retention, and controlled exports. It requires institutional infrastructure and is disabled by default.</p></article>
    </div>
  </div>
</section>

<section class="soft">
  <div class="wrap">
    <div class="section-head">
      <span class="eyebrow">Accuracy</span>
      <h2>What Axcess claims about its own accuracy</h2>
    </div>
    <div class="grid grid-2">
      <article class="card"><h3>A regression gate, not a marketing number</h3><p>A versioned, labelled test corpus requires fewer than 5% false discoveries and at least 80% recall for every detection layer before a change can ship. That stops a known detector from getting worse.</p></article>
      <article class="card"><h3>What that does not mean</h3><p>It is not a claim that every real website will see the same rate. A public real-world accuracy figure would need a representative held-out set reviewed independently by at least two accessibility experts, and the project says so in writing.</p></article>
    </div>
    <div style="margin-top:1.5rem">{callout(HONESTY, "callout-maize", "warn")}</div>
  </div>
</section>
"""


def get_started() -> str:
    return f"""
<section class="hero hero-compact">
  <div class="wrap">
    <span class="eyebrow">Get started</span>
    <h1>Your first scan in <span class="hl">about ten minutes</span></h1>
    <p class="lede">Choose how to install, run one small scan, and read your first report. If you are not a developer, the desktop app is the path for you.</p>
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
        <p>One macOS app that bundles everything: the workbench, the browser, the two rule engines, and text recognition. No Python, Node, or other developer tools needed.</p>
        <ul class="checks" style="margin:1rem 0">
          <li>Apple Silicon Macs (M1 and later)</li>
          <li>Development preview, updated from the project's build system</li>
          <li>Free; requires a GitHub sign-in to download</li>
        </ul>
        <p><a class="btn btn-primary" href="{DESKTOP_BUILDS}">Open the desktop builds</a></p>
        <p class="small" style="margin-top:1rem">On the builds page, open the most recent successful run and download <strong>axcess-macos-apple-silicon</strong>. Each build is kept for 14 days. The preview is not yet Apple-notarized, so on first launch right-click <strong>Axcess</strong> and choose <strong>Open</strong>. An Intel Mac build is not available yet.</p>
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
        <p class="small">Full instructions, hosting for a small team, and troubleshooting are in <a href="{DOCS}">the documentation</a>.</p>
      </article>
    </div>
    <div style="margin-top:1.5rem">{callout("<strong>Optional AI checks</strong> need a separately installed local Ollama service and downloaded models. Skip this at first; every browser-based check runs without it. <a href='../privacy/'>How the optional AI is kept local.</a>", "", "info")}</div>
  </div>
</section>

<section class="soft">
  <div class="wrap">
    <div class="section-head">
      <span class="eyebrow">Step 2</span>
      <h2>Run a small first scan</h2>
      <p class="sub">Start with a public site you are authorized to test and a low page limit. You will have a report in a few minutes and a feel for the tool.</p>
    </div>
    <ol class="steps">
      <li><h3>Open Axcess and choose "Public scan"</h3><p>The dashboard has two buttons at the top: <em>Public scan</em> and <em>2FA / login scan</em>. Choose the public one for now.</p></li>
      <li><h3>Paste the address of one section</h3><p>Something like <code>https://www.example.edu/admissions/</code>. The scope preview will show that only pages under <em>/admissions/</em> will be visited. Leave <em>Crawl the entire host</em> unchecked.</p></li>
      <li><h3>Set "Max pages" to about 25</h3><p>The other defaults are conservative and fine. Under <em>Included tests</em>, leave everything on; the browser-based checks do not need any AI.</p>
        <p class="tip">Want to see it work? Turn on "Show the scanning browser window" in advanced settings.</p></li>
      <li><h3>Start the scan and watch</h3><p>You will see the current page, counts of pages discovered and tested, which checks ran, and an estimated finish time. You can stop at any point.</p></li>
    </ol>
  </div>
</section>

<section>
  <div class="wrap">
    <div class="section-head">
      <span class="eyebrow">Step 3</span>
      <h2>Read your first report</h2>
    </div>
    <div class="grid grid-2">
      <article class="card">{icon("table")}<h3>Start at the issue table</h3><p>Issues are grouped by cause and sorted by impact. Each row tells you what was detected, why it is an issue, the expected fix, and where exactly. Filter by the evidence lane if you want only deterministic failures first.</p></article>
      <article class="card">{icon("pin")}<h3>Open the evidence</h3><p>Click through to Page Evidence to see the element on the page, the snippet, and any screenshot. For findings revealed by clicking, it says which control revealed them.</p></article>
      <article class="card">{icon("check")}<h3>Record decisions</h3><p>Accept, reject as a false positive, mark remediated, or accept the risk, with a short rationale. Decisions are kept with the report and travel into exports.</p></article>
      <article class="card">{icon("doc")}<h3>Check the manual list</h3><p>The WCAG 2.2 A/AA review matrix shows which criteria still need a person, with the procedure for each. This is the honest half of the report.</p></article>
      <article class="card">{icon("sheet")}<h3>Export when ready</h3><p>Download the Excel workbook or the audit report from the handoff screen. If expert review is unfinished, the export is labelled DRAFT and you are told what is missing.</p></article>
      <article class="card">{icon("refresh")}<h3>Rescan later</h3><p>After fixes land, scan the same address again. The comparison shows what is new, resolved, and still open.</p></article>
    </div>
  </div>
</section>

<section class="soft">
  <div class="wrap">
    <div class="section-head">
      <span class="eyebrow">Good to know</span>
      <h2>Before you scan</h2>
    </div>
    <div class="grid grid-3">
      <article class="card"><h3>Authorization</h3><p>Only scan sites and accounts you are explicitly permitted to test. Axcess records when robots.txt is ignored, and refuses controls named sign out, delete, or unsubscribe.</p></article>
      <article class="card"><h3>One scan at a time</h3><p>Axcess runs one crawl per app at a time, matching its local single-writer database. Start the next scan when the first finishes.</p></article>
      <article class="card"><h3>Time per page</h3><p>Rendering pages in a real browser and running several checks takes a few seconds per page. Advanced settings let you skip individual checks when speed matters more than coverage, and say what you lose.</p></article>
    </div>
  </div>
</section>
"""


def faq() -> str:
    def q(question: str, answer: str) -> str:
        return f'<details><summary>{question}</summary><div class="a">{answer}</div></details>'

    faqs = "".join(
        [
            q(
                "Does Axcess certify that my website is accessible?",
                "<p>No. Axcess produces evidence for a qualified person to review. It does not certify WCAG conformance, prove legal compliance, or replace testing with people who use assistive technology. A qualified person can use Axcess evidence to complete a conformance report; Axcess will not generate one automatically.</p>",
            ),
            q(
                "Do I need AI to use it?",
                "<p>No. The rule engines and the keyboard, zoom, focus, and interaction checks run with just the bundled browser. AI-assisted checks are optional, run on a local model you install yourself, and are clearly labelled as leads that need confirmation.</p>",
            ),
            q(
                "Does any of my data go to the cloud?",
                '<p>No. There is no account, no telemetry, and no upload. Evidence is stored in a local database on your computer. The only outbound connection is to the website you are scanning, plus an optional local AI service on the same machine. <a href="../privacy/">Read the privacy page.</a></p>',
            ),
            q(
                "Can it scan pages behind a login or two-factor sign-in?",
                "<p>Yes. Axcess opens a visible browser window, you sign in directly with the website, and the scan continues using that live session. Axcess never asks for your password or code, and login pages are not stored as evidence. Use only accounts and sites you are authorized to test.</p>",
            ),
            q(
                'What does "29 of 55 criteria" mean?',
                '<p>WCAG 2.2 has 55 Level A and AA success criteria. Axcess has at least one check that contributes evidence for 29 of them. That does not mean those 29 are decided without a person, and it does not mean a site that passes them conforms. The remaining 26 are listed as manual, with the steps to test each one. <a href="../coverage/">See all 55.</a></p>',
            ),
            q(
                "What is the difference between an issue group and an occurrence?",
                "<p>An occurrence is one problem on one page, for example a missing image description on the home page. An issue group collects occurrences that share a cause and probably share a fix, for example the same broken template across 40 pages. The report shows both numbers so a large raw count never stands alone.</p>",
            ),
            q(
                "How accurate is it?",
                "<p>A labelled test corpus requires fewer than 5% false discoveries and at least 80% recall for every detection layer before a change ships. That is a regression gate, not a real-world guarantee; the project states plainly that a public accuracy claim would need an independently reviewed corpus. Every finding also carries a confidence and a method, and you can reject any of them as a false positive with a recorded reason.</p>",
            ),
            q(
                "How long does a scan take?",
                "<p>It depends on the number of pages and which checks you enable. Rendering each page in a real browser and running several checks takes a few seconds per page. A 25-page first scan usually finishes in a few minutes. Advanced settings let you skip individual checks and say exactly what coverage you lose.</p>",
            ),
            q(
                "Will it break anything on the site?",
                "<p>Axcess only reads pages and, if you enable it, operates visible controls such as menus and tabs. It never clicks links during that probe, refuses anything named sign out, delete, remove, unsubscribe, or deactivate, reverses navigations, and caps clicks per page. Crawl speed is conservative by default and robots.txt is respected unless you choose otherwise.</p>",
            ),
            q(
                "Does it work on single-page apps built with React, Vue, or Angular?",
                "<p>Yes. Pages are rendered in a real browser before testing, app-style routes are followed as separate pages, and the click-through probe can test menus and dialogs that only appear after interaction. Routes must be reachable by real links inside your scope; Axcess does not read application code to guess private addresses.</p>",
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
                "<p>The desktop preview is for Apple Silicon Macs. From source, Axcess runs on macOS, Linux, and Windows with WSL. Windows and Linux desktop installers are part of the build system but are not yet released as previews.</p>",
            ),
        ]
    )

    terms = [
        (
            "WCAG",
            "The Web Content Accessibility Guidelines, the international standard for accessible websites. Version 2.2 is current. Levels A and AA are the usual legal and policy target.",
        ),
        (
            "Success criterion",
            "One testable requirement in WCAG, numbered like 1.4.3. There are 55 at Levels A and AA.",
        ),
        (
            "Evidence",
            "What a check actually observed: the page, the element, a snippet, a screenshot, the rule, and the method. Axcess keeps evidence attached to every result.",
        ),
        (
            "Issue group",
            "Occurrences that share a cause and probably share a fix, presented as one row in the issue table.",
        ),
        ("Occurrence", "One instance of a problem on one page, or in one DOM state."),
        (
            "Review lead",
            "A result that needs a person to confirm it before it counts, such as a keyboard-trap observation or an AI suggestion.",
        ),
        (
            "False positive",
            "A result the reviewer has judged not to be a real barrier. Marking one records the reason and keeps the history.",
        ),
        (
            "Rule engine",
            "Software that checks a page against a fixed list of machine-testable rules. Axcess uses axe-core and, optionally, Siteimprove Alfa.",
        ),
        (
            "axe-core",
            "The most widely used open-source accessibility rule engine, made by Deque. It runs inside the rendered page.",
        ),
        (
            "Alfa",
            "Siteimprove's open-source rule engine, based on the W3C's ACT rule format. An independent second opinion.",
        ),
        (
            "ACT rule",
            "A W3C-standardised, precisely written accessibility test that different tools can implement the same way.",
        ),
        (
            "Rendered page",
            "A page after the browser has run its scripts and drawn it, which is what visitors actually see. Axcess tests rendered pages.",
        ),
        (
            "DOM state",
            "What the page looks like after a control is operated, for example after a menu opens. Axcess can test these states and counts them separately from pages.",
        ),
        (
            "Scope",
            "The part of a site a scan is allowed to visit, defined by the host and a path such as /admissions/, plus page and depth limits.",
        ),
        (
            "OCR",
            "Optical character recognition: software that reads text inside images. Axcess bundles Tesseract for this.",
        ),
        (
            "Local AI model",
            "A language or vision model that runs on your own computer through a service called Ollama. Optional, and never installed silently.",
        ),
        (
            "Ollama",
            "A free program for running AI models locally. Axcess talks to it only on the same machine.",
        ),
        (
            "Images of text",
            "WCAG 1.4.5. Text baked into a picture cannot be resized, restyled, or read by a screen reader. Finding these at scale was the original reason Axcess was built.",
        ),
        (
            "Keyboard trap",
            "WCAG 2.1.2. A place where keyboard focus enters a component and cannot leave, stranding people who do not use a mouse.",
        ),
        (
            "Reflow",
            "WCAG 1.4.10. Content should rearrange to fit a narrow screen without sideways scrolling.",
        ),
        (
            "Rescan comparison",
            "Running the same scope again and lining up the two reports: new, resolved, and still open.",
        ),
        (
            "Local-first",
            "The design principle that your data lives on your computer by default and only leaves it when you deliberately send it somewhere.",
        ),
    ]
    glossary = "".join(f"<div><dt>{e(t)}</dt><dd>{e(d)}</dd></div>" for t, d in terms)

    return f"""
<section class="hero hero-compact">
  <div class="wrap">
    <span class="eyebrow">Questions and glossary</span>
    <h1>Straight answers, <span class="hl">plain words</span></h1>
    <p class="lede">The questions people ask before they trust a tool, and the vocabulary you will meet in an Axcess report.</p>
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
    </div>
    <dl class="glossary">{glossary}</dl>
  </div>
</section>
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
    shipped_ct = len(cov.SHIPPED)
    ai_ct = sum(1 for p in cov.SHIPPED if p.needs_ai)
    bodies = {
        "": home(summ, shipped_ct, ai_ct),
        "how-it-works": how_it_works(summ),
        "coverage": coverage(crit, summ, cov),
        "who-its-for": who_its_for(),
        "privacy": privacy(),
        "get-started": get_started(),
        "faq": faq(),
        "about": about(summ),
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
