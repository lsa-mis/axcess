#!/usr/bin/env python3
"""Generate the Axcess landing page (site/index.html) from the source of truth.

The "what's covered" section is rendered from
``src/audit/web/coverage_status.py`` — the same module that powers the in-app
Tracking page and ``docs/coverage-tracker.md`` — so the public landing page
can't claim coverage the code doesn't have. Pure standard library: it loads
that module directly by file path (no package install needed), which keeps the
GitHub Pages build fast and dependency-free.

Run from the repo root:  ``python site/build.py``
"""

from __future__ import annotations

import html
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "site" / "index.html"

# Import the real package so the page is generated from the same source of
# truth as the app. Run with ``uv run python site/build.py`` (needs PyYAML +
# the audit package, both in the dev env).
sys.path.insert(0, str(ROOT / "src"))

# Public destinations used by the generated landing page.
PORTFOLIO_URL = "https://reganmaharjan.com.np/"
REPOSITORY_URL = "https://github.com/lsa-mis/axcess"


def e(s: str) -> str:
    return html.escape(str(s))


def render() -> str:
    from audit import coverage_matrix
    from audit.web import coverage_status as cov

    shipped = cov.SHIPPED
    roadmap = cov.ROADMAP
    counts = cov.roadmap_counts()
    matrix = coverage_matrix.summary()

    pipeline_cards = "\n".join(
        f"""        <li class="card">
          <div class="card-top">
            <span class="dot {"ai" if p.needs_ai else "rule"}" aria-hidden="true"></span>
            <h3>{e(p.name)}</h3>
            <span class="badge {"badge-ai" if p.needs_ai else "badge-rule"}">{
            "AI" if p.needs_ai else "rule"
        }</span>
          </div>
          <p class="engine">{e(p.engine)}</p>
          <p class="scs"><strong>Covers:</strong> {e(p.scs)}</p>
        </li>"""
        for p in shipped
    )

    planned = [r for r in roadmap if r.status == "planned"]
    roadmap_chips = "\n".join(
        f'          <li><span class="wcag">{e(r.wcag)}</span> {e(r.issue)}</li>'
        for r in planned[:8]
    )

    # The covered criteria, grouped by method (the "what's covered" section).
    crit = coverage_matrix.load_matrix()
    groups = []
    for method in ("automated", "partial", "ai-assisted"):
        items = [c for c in crit if c.method == method]
        if not items:
            continue
        chips = "\n".join(
            f'          <li><span class="wcag">{e(c.sc)}</span> {e(c.name)}</li>' for c in items
        )
        label = coverage_matrix.METHOD_LABELS[method]
        groups.append(
            f'      <h3 class="cov-h"><span class="dot {method}"></span>{e(label)} '
            f'<span class="cov-n">{len(items)}</span></h3>\n'
            f'      <ul class="chips">\n{chips}\n      </ul>'
        )
    covered_criteria = "\n".join(groups)

    shipped_ct = sum(1 for p in shipped)
    ai_ct = sum(1 for p in shipped if p.needs_ai)

    return TEMPLATE.format(
        pipeline_cards=pipeline_cards,
        roadmap_chips=roadmap_chips,
        covered_criteria=covered_criteria,
        shipped_pipelines=shipped_ct,
        ai_pipelines=ai_ct,
        rule_pipelines=shipped_ct - ai_ct,
        planned_count=counts.planned,
        wcag_total=matrix.total,
        wcag_covered=matrix.covered,
        wcag_manual=matrix.manual_only,
        axcess_automated=matrix.by_method.get("automated", 0),
        axcess_partial=matrix.by_method.get("partial", 0),
        axcess_ai=matrix.by_method.get("ai-assisted", 0),
        portfolio=PORTFOLIO_URL,
        repository=REPOSITORY_URL,
    )


# The favicon mark, inlined so the page is fully self-contained.
MARK = (
    '<svg viewBox="0 0 32 32" width="36" height="36" role="img" '
    'aria-label="Axcess logo" focusable="false">'
    '<rect width="32" height="32" rx="7" fill="#00274C"/>'
    '<text x="16" y="22" text-anchor="middle" fill="#FFCB05" '
    'font-family="Arial, Helvetica, sans-serif" font-size="18" '
    'font-weight="800">Ax</text></svg>'
)

TEMPLATE = (
    """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Axcess — local-first, AI-augmented accessibility auditor</title>
<meta name="description" content="Axcess crawls a site, renders every page, and runs {shipped_pipelines} detection pipelines — a rule engine, behavioural probes, and local AI models — covering {wcag_covered} of {wcag_total} WCAG 2.2 A/AA criteria. Runs entirely on your machine.">
<link rel="icon" type="image/svg+xml" href="data:image/svg+xml,"""
    + "%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' rx='7' fill='%2300274C'/%3E%3Ctext x='16' y='22' text-anchor='middle' fill='%23FFCB05' font-family='Arial' font-size='18' font-weight='800'%3EAx%3C/text%3E%3C/svg%3E"
    + """">
<style>
  :root {{
    --blue: #00274C; --maize: #FFCB05;
    --ink: #14181f; --muted: #4a5568; --line: #e2e8f0;
    --bg: #ffffff; --bg-soft: #f6f8fb;
    --ai: #6b3a00; --rule: #0f5132;
  }}
  * {{ box-sizing: border-box; }}
  html {{ scroll-behavior: smooth; }}
  body {{
    margin: 0; background: var(--bg); color: var(--ink);
    font: 17px/1.65 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    -webkit-font-smoothing: antialiased;
  }}
  a {{ color: #003f75; }}
  .skip {{ position: absolute; left: -999px; top: 0; background: var(--blue); color: #fff; padding: .6rem 1rem; z-index: 100; }}
  .skip:focus {{ left: .5rem; top: .5rem; }}
  .wrap {{ max-width: 1040px; margin: 0 auto; padding: 0 1.25rem; }}

  header.site {{ border-bottom: 1px solid var(--line); position: sticky; top: 0; background: rgba(255,255,255,.92); backdrop-filter: blur(8px); z-index: 50; }}
  header.site .wrap {{ display: flex; align-items: center; gap: .75rem; height: 64px; }}
  .brand {{ display: flex; align-items: center; gap: .6rem; font-weight: 800; font-size: 1.15rem; letter-spacing: -.01em; color: var(--ink); text-decoration: none; }}
  header nav {{ margin-left: auto; display: flex; gap: 1.25rem; align-items: center; }}
  header nav a {{ text-decoration: none; font-weight: 600; font-size: .95rem; }}
  .btn {{ display: inline-block; padding: .6rem 1.1rem; border-radius: 8px; font-weight: 700; text-decoration: none; }}
  .btn-primary {{ background: var(--blue); color: #fff; }}
  .btn-primary:hover {{ background: #013a6b; }}
  .btn-ghost {{ border: 1.5px solid var(--blue); color: var(--blue); }}

  .hero {{ background: var(--blue); color: #fff; padding: 4.5rem 0 4rem; }}
  .hero .tag {{ display: inline-block; color: var(--blue); background: var(--maize); font-weight: 800; font-size: .78rem; letter-spacing: .04em; text-transform: uppercase; padding: .25rem .6rem; border-radius: 999px; }}
  .hero h1 {{ font-size: clamp(2.1rem, 5vw, 3.2rem); line-height: 1.08; margin: 1rem 0 .75rem; letter-spacing: -.02em; max-width: 16ch; }}
  .hero h1 .hl {{ color: var(--maize); }}
  .hero p.lede {{ font-size: 1.2rem; color: #d7e3f0; max-width: 60ch; margin: 0 0 1.75rem; }}
  .hero .cta {{ display: flex; gap: .75rem; flex-wrap: wrap; }}
  .hero .cta .btn-primary {{ background: var(--maize); color: var(--blue); }}
  .hero .cta .btn-primary:hover {{ background: #ffd633; }}
  .hero .cta .btn-ghost {{ border-color: #6f8aa6; color: #fff; }}
  .hero .meta {{ margin-top: 1.5rem; color: #aebfd2; font-size: .9rem; }}
  .hero .meta strong {{ color: #fff; }}

  .product-shot {{ display: block; width: 100%; border: 1px solid var(--line); border-radius: 14px; box-shadow: 0 18px 48px rgba(0,39,76,.14); }}
  .caption {{ color: var(--muted); font-size: .9rem; margin: .75rem 0 0; }}

  section {{ padding: 3.75rem 0; border-bottom: 1px solid var(--line); }}
  section.soft {{ background: var(--bg-soft); }}
  h2 {{ font-size: 1.9rem; letter-spacing: -.02em; margin: 0 0 .4rem; }}
  .sub {{ color: var(--muted); max-width: 62ch; margin: 0 0 2rem; font-size: 1.05rem; }}

  ul.cards {{ list-style: none; margin: 0; padding: 0; display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 1rem; }}
  .card {{ background: var(--bg); border: 1px solid var(--line); border-radius: 12px; padding: 1.2rem 1.25rem; }}
  .card-top {{ display: flex; align-items: center; gap: .55rem; margin-bottom: .5rem; }}
  .card-top h3 {{ margin: 0; font-size: 1.1rem; flex: 1; }}
  .dot {{ width: 10px; height: 10px; border-radius: 50%; flex: none; }}
  .dot.ai {{ background: var(--ai); }} .dot.rule {{ background: var(--rule); }}
  .dot.automated {{ background: var(--rule); }} .dot.partial {{ background: #0b4f6c; }}
  .dot.ai-assisted {{ background: var(--ai); }}
  .cov-title {{ margin: 2rem 0 .25rem; font-size: 1.15rem; }}
  .cov-h {{ display: flex; align-items: center; gap: .5rem; margin: 1.25rem 0 .25rem; font-size: 1rem; }}
  .cov-h .dot {{ width: 10px; height: 10px; border-radius: 50%; }}
  .cov-n {{ background: var(--blue); color: #fff; border-radius: 999px; font-size: .72rem; font-weight: 800; padding: .05rem .5rem; }}
  .badge {{ font-size: .68rem; font-weight: 800; letter-spacing: .03em; padding: .12rem .45rem; border-radius: 5px; color: #fff; }}
  .badge-ai {{ background: var(--ai); }} .badge-rule {{ background: var(--rule); }}
  .engine {{ color: var(--muted); margin: 0 0 .55rem; font-size: .95rem; }}
  .scs {{ margin: 0; font-size: .92rem; }}
  .legend {{ display: flex; gap: 1.25rem; margin-top: 1.25rem; color: var(--muted); font-size: .9rem; flex-wrap: wrap; }}
  .legend span {{ display: inline-flex; align-items: center; gap: .4rem; }}

  .stats {{ display: flex; gap: 2.5rem; flex-wrap: wrap; margin: 0 0 1.5rem; }}
  .stat b {{ display: block; font-size: 2.4rem; line-height: 1; color: var(--blue); letter-spacing: -.02em; }}
  .stat span {{ color: var(--muted); font-size: .92rem; }}
  ul.chips {{ list-style: none; margin: 1rem 0 0; padding: 0; display: flex; flex-wrap: wrap; gap: .5rem; }}
  ul.chips li {{ background: var(--bg); border: 1px solid var(--line); border-radius: 999px; padding: .35rem .8rem; font-size: .9rem; }}
  .chips .wcag {{ font-family: ui-monospace, Menlo, monospace; font-size: .82rem; color: var(--blue); font-weight: 700; }}
  table.cmp {{ width: 100%; border-collapse: collapse; margin: .25rem 0 1.25rem; }}
  table.cmp th, table.cmp td {{ text-align: left; padding: .7rem .8rem; border-bottom: 1px solid var(--line); vertical-align: top; font-size: .98rem; }}
  table.cmp th {{ font-size: .72rem; text-transform: uppercase; letter-spacing: .04em; color: var(--muted); font-weight: 700; }}
  table.cmp td b {{ color: var(--blue); }}
  table.cmp tr.me td {{ background: #fff7d6; border-bottom-color: var(--maize); }}
  table.cmp tr.me td:first-child {{ border-left: 3px solid var(--maize); }}
  table.cmp .dim {{ color: var(--muted); font-weight: 400; }}
  /* On the maize-tinted Axcess row, muted text drops below AAA 7:1 — use ink. */
  table.cmp tr.me .dim {{ color: var(--ink); }}
  table.cmp sup {{ color: var(--muted); font-size: .7rem; }}
  .sub.small {{ font-size: .96rem; max-width: 74ch; margin-bottom: 1rem; }}
  .src {{ color: var(--muted); font-size: .82rem; max-width: 74ch; line-height: 1.6; }}
  .src a {{ color: var(--muted); }}
  @media (max-width: 560px) {{ table.cmp td, table.cmp th {{ padding: .5rem .4rem; font-size: .86rem; }} }}

  pre {{ background: #0d1b2a; color: #e6edf3; padding: 1.25rem 1.4rem; border-radius: 12px; overflow-x: auto; font: .92rem/1.6 ui-monospace, Menlo, monospace; }}
  pre .c {{ color: #b8c6d8; }} pre .m {{ color: var(--maize); }}  /* comment colour at ~9.7:1 on the dark block — clears AAA */

  .pillars {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(240px,1fr)); gap: 1.5rem; }}
  .pillar h3 {{ margin: 0 0 .35rem; font-size: 1.1rem; }}
  .pillar p {{ margin: 0; color: var(--muted); font-size: .98rem; }}

  footer {{ padding: 2.5rem 0; color: var(--muted); font-size: .92rem; }}
  footer .wrap {{ display: flex; justify-content: space-between; gap: 1rem; flex-wrap: wrap; align-items: center; }}
  @media (max-width: 760px) {{
    header.site .wrap {{ height: auto; min-height: 64px; flex-wrap: wrap; padding-top: .65rem; padding-bottom: .65rem; }}
    header nav {{ width: 100%; margin-left: 0; gap: .85rem; overflow-x: auto; padding-bottom: .2rem; }}
    header nav a {{ white-space: nowrap; }}
  }}
  @media (prefers-reduced-motion: reduce) {{ html {{ scroll-behavior: auto; }} }}
</style>
</head>
<body>
<a class="skip" href="#main">Skip to content</a>

<header class="site">
  <div class="wrap">
    <a class="brand" href="./">"""
    + MARK
    + """ Axcess</a>
    <nav aria-label="Primary">
      <a href="about/">About</a>
      <a href="#pipelines">What it checks</a>
      <a href="#compare">Compare</a>
      <a href="#start">How it works</a>
      <a class="btn btn-primary" href="{repository}">GitHub</a>
    </nav>
  </div>
</header>

<main id="main">
<section class="hero" id="top" style="border:0">
  <div class="wrap">
    <span class="tag">Local-first · WCAG 2.2 A/AA evidence · MIT</span>
    <h1>Find the accessibility failures rule engines <span class="hl">miss</span>.</h1>
    <p class="lede">Axcess crawls your site, renders every page in a real browser, and runs
      <strong>{shipped_pipelines} detection pipelines</strong> — a rule engine, behavioural probes,
      and local AI models — covering <strong>{wcag_covered} of {wcag_total}</strong> WCAG 2.2 A/AA
      success criteria. It all runs on your machine. No cloud, no telemetry.</p>
    <div class="cta">
      <a class="btn btn-primary" href="#pipelines">See what it checks ↓</a>
      <a class="btn btn-ghost" href="about/">About Axcess</a>
    </div>
    <p class="meta">Runs with <strong>zero AI</strong> on just a browser, or add a local
      <strong>Ollama</strong> model for the judgment calls — your content never leaves the machine.</p>
  </div>
</section>

<section id="workbench">
  <div class="wrap">
    <h2>An evidence workbench, not a scorecard</h2>
    <p class="sub">Review grouped issues, follow every claim back to a page and selector,
      and keep route coverage and click-discovered DOM states visible instead of hiding them
      behind a single score.</p>
    <img class="product-shot" src="assets/axcess-dashboard-redacted.png"
      alt="Axcess dashboard showing scan totals, issue groups, and workflow guidance. Recent scan details are blurred."
      width="1487" height="1058">
    <p class="caption">Recent scan targets are intentionally blurred in this product preview.</p>
  </div>
</section>

<section id="pipelines">
  <div class="wrap">
    <h2>{shipped_pipelines} pipelines, one crawl</h2>
    <p class="sub">{rule_pipelines} pipelines need only a browser. {ai_pipelines} add a local AI
      model for the criteria a rule engine can't decide — <em>is this image really text?</em>,
      <em>does this link make sense out of context?</em>, <em>does the reading order match the
      visual layout?</em></p>
    <ul class="cards">
{pipeline_cards}
    </ul>
    <div class="legend">
      <span><span class="dot rule" aria-hidden="true"></span> deterministic — browser only, no model</span>
      <span><span class="dot ai" aria-hidden="true"></span> AI — local Ollama model</span>
    </div>
  </div>
</section>

<section class="soft" id="coverage">
  <div class="wrap">
    <h2>Honest about coverage</h2>
    <p class="sub">Axcess never claims coverage it doesn't have. Of all {wcag_total} WCAG 2.2
      Level A/AA success criteria, it's upfront about exactly which ones it checks for you and
      which still need a human — and tells you what to test for each. These numbers come straight
      from the code, so this page, the in-app Tracking view, and the docs can't drift apart.</p>
    <div class="stats">
      <div class="stat"><b>{wcag_covered}/{wcag_total}</b><span>A/AA criteria with<br>automated or AI coverage</span></div>
      <div class="stat"><b>{wcag_manual}</b><span>criteria flagged for<br>manual testing (with guidance)</span></div>
      <div class="stat"><b>{shipped_pipelines}</b><span>detection pipelines<br>({rule_pipelines} browser · {ai_pipelines} AI)</span></div>
      <div class="stat"><b>AAA</b><span>the tool audits itself at<br>WCAG 2.2 AAA</span></div>
    </div>
    <h3 class="cov-title">What Axcess checks for you</h3>
    <p class="sub">The {wcag_covered} criteria with automated or AI coverage today, grouped by how
      Axcess detects them. Generated straight from the code.</p>
{covered_criteria}

    <h3 class="cov-title">Next up — on the roadmap</h3>
    <ul class="chips">
{roadmap_chips}
    </ul>
    <p style="margin-top:1.25rem; color:var(--muted); font-size:.95rem;">Every surface — this page, the in-app Tracking view, and the docs — is generated from one source of truth, so the coverage above always matches the code.</p>
  </div>
</section>

<section id="compare">
  <div class="wrap">
    <h2>How Axcess compares</h2>
    <p class="sub">Rule engines like <strong>axe-core</strong>, <strong>Alfa</strong>, and
      <strong>Siteimprove</strong> are fast and high-confidence — but they can only check what's
      <em>mechanically decidable</em>. Axcess runs a rule engine too, then adds behavioural probes
      and local AI to reach the judgment criteria a rule engine structurally can't. The numbers
      below count WCAG 2.2 Level A/AA success criteria a tool gives you an automated signal on.</p>
    <table class="cmp">
      <thead>
        <tr><th>Tool</th><th>Approach</th><th>A/AA criteria<br>with a signal</th><th>Judgment<br>criteria?</th></tr>
      </thead>
      <tbody>
        <tr><td>axe-core</td><td>DOM rule engine</td><td><b>21</b> <span class="dim">/ 55</span><sup>1</sup></td><td>No</td></tr>
        <tr><td>Alfa <span class="dim">(Siteimprove OSS)</span></td><td>ACT-rules engine</td><td><span class="dim">not published</span><sup>2</sup></td><td>No</td></tr>
        <tr><td>Siteimprove</td><td>ACT-rules engine</td><td><span class="dim">not published</span><sup>3</sup></td><td>No</td></tr>
        <tr class="me"><td><b>Axcess</b></td><td>Rule engine + 3 behavioural probes + 3 local-AI analyzers</td><td><b>{wcag_covered}</b> <span class="dim">/ {wcag_total}</span></td><td><b>Yes</b></td></tr>
      </tbody>
    </table>
    <p class="sub small">Axcess's {wcag_covered} break down as <strong>{axcess_automated} deterministic</strong> ·
      <strong>{axcess_partial} partly automated</strong> · <strong>{axcess_ai} AI-assisted</strong> (leads a human
      confirms). It runs axe-core as its rule engine, so it covers that deterministic baseline and then
      reaches criteria no pure rule engine can — <em>“is this image really text?”</em> (1.4.5),
      <em>“does this link make sense out of context?”</em> (2.4.4), <em>“does the reading order match the
      layout?”</em> (1.3.2). The trade-off is stated plainly: AI-assisted findings are strong leads, not
      certainties, so every finding carries a confidence label and {wcag_manual} criteria are flagged
      manual-only with guidance.</p>
    <p class="src">Sources, June 2026: <a href="https://github.com/dequelabs/axe-core/blob/develop/doc/rule-descriptions.md">axe-core 4.12 rule map</a>
      (21 distinct A/AA criteria, counted from source) ·
      <a href="https://www.w3.org/WAI/standards-guidelines/act/implementations/alfa/">Alfa ACT implementation</a>
      (40 automated / 54 semi-automated ACT <em>rules</em>) ·
      <a href="https://help.siteimprove.com/support/solutions/articles/80000448514-a-guide-to-the-siteimprove-accessibility-checks">Siteimprove checks guide</a>.
      <sup>2,3</sup> Alfa and Siteimprove publish <em>rule</em> counts (and span Level AAA too), not a
      deduplicated A/AA success-criterion count — so a like-for-like SC number isn't available for them;
      both share the same structural ceiling as any rule engine.</p>
  </div>
</section>

<section id="start">
  <div class="wrap">
    <h2>Up and running in three commands</h2>
    <p class="sub">macOS or Linux · Python 3.11+ · a browser. Ollama is optional — skip it and
      the browser-only pipelines still run.</p>
    <pre><span class="c"># install (uv + chromium + data dirs), then the DB schema</span>
make setup &amp;&amp; make migrate

<span class="c"># crawl a site — renders every page, runs axe + keyboard + responsive</span>
uv run audit crawl <span class="m">https://example.com</span> --max-pages 50

<span class="c"># open the review UI (React SPA, audits itself at AAA)</span>
make frontend-build &amp;&amp; uv run audit serve   <span class="c"># → /app/</span></pre>
  </div>
</section>

<section class="soft" id="why">
  <div class="wrap">
    <h2>Built for trust</h2>
    <div class="pillars">
      <div class="pillar"><h3>Private by design</h3><p>Everything runs locally — the crawler, the
        browser probes, and the AI models via a loopback Ollama daemon. Your pages and findings
        never leave the machine.</p></div>
      <div class="pillar"><h3>Eats its own dog food</h3><p>The review UI is held to WCAG 2.2 AAA,
        with axe-core tests in the AAA tag pack that fail the build on any violation.</p></div>
      <div class="pillar"><h3>Resumable &amp; deterministic</h3><p>A queue-driven crawl resumes after
        a crash. Exports are pinned by golden-file tests, so every change is explicit.</p></div>
      <div class="pillar"><h3>Team-ready</h3><p>Host it on an always-on machine over your LAN or
        Tailscale behind an opt-in shared-token gate — without giving up local-first.</p></div>
    </div>
  </div>
</section>
</main>

<footer>
  <div class="wrap">
    <span>"""
    + MARK
    + """ <strong>Axcess</strong> · MIT licensed · built at the University of Michigan 〽️</span>
    <span><a href="about/">About</a> · <a href="{repository}">Source on GitHub</a> · A project by <a href="{portfolio}">Regan Maharjan</a></span>
  </div>
</footer>
</body>
</html>
"""
)


def main() -> None:
    OUT.write_text(render(), encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)} ({OUT.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
