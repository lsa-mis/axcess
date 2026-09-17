"""Build the GDS corpus in the format `bakeoff.py` expects.

`tools/gds_run.py` measured the GDS cases with a hand-written harness, which is
the reimplementation that had to be retracted. This instead turns the same 8
cases into a corpus the real bakeoff can score with all 38 detectors, so the
numbers come from the frozen detector code rather than from a restatement of it.

The 6 IAF-matching cases carry `violation`; the 2 correctly-built controls carry
`ok`. Both sets were verified behaviourally before any detector saw them: each
violation is mouse-operable and not keyboard-operable, each control is operable
both ways. Labels come from the GDS case list, not from any Axcess output.

Reference published by GDS for these 6 cases: **all 13 audited tools score 0/6**
(`tests.json`, the `results` field per case).

Usage:
    uv run --offline --no-sync python -m tools.build_gds_corpus
"""

from __future__ import annotations

import asyncio
import json
import pathlib
import sys

from playwright.async_api import async_playwright

HERE = pathlib.Path(__file__).resolve().parent.parent
SOURCE = HERE / "artifacts" / "gds"
OUT = HERE / "artifacts" / "gds-corpus"

# The six cases matching KAFE's IAF construct, and the two negatives. Selectors
# and labels are lifted from `tools/gds_run.py`, which read them off the GDS
# case list -- they are not derived from any detector's output.
CASES = {
    "gds-fake-button": ("#webchat", "violation", "div with a click handler, not focusable"),
    "gds-concertina": (".concertina dt", "violation", "dt toggles on click only"),
    "gds-tooltip": (
        ".tooltips-not-focusable .tooltip-icon",
        "violation",
        "tooltip icon never receives focus",
    ),
    "gds-dropdown": (
        ".dropdown-nav .submenu a",
        "violation",
        "submenu link hidden until hover, unreachable by Tab",
    ),
    "gds-lightbox-close": (
        ".lightbox.close-button .close-button",
        "violation",
        "lightbox close button does not receive focus",
    ),
    "gds-role-button": (
        "a.button[role='button']",
        "violation",
        "a[role=button] does not activate on Space",
    ),
    "gds-real-button": ("button:not([class])", "ok", "correctly-built button"),
    "gds-real-link": ("a[href='swift.html']", "ok", "correctly-built link"),
}

TAG_JS = """
(pairs) => {
    const out = {};
    for (const [probe, sel] of pairs) {
        const el = document.querySelector(sel);
        if (el) { el.setAttribute('data-probe', probe); out[probe] = true; }
        else out[probe] = false;
    }
    return out;
}
"""


async def main() -> int:
    page_file = SOURCE / "test-cases.html"
    if not page_file.exists():
        print(f"missing {page_file}", file=sys.stderr)
        return 1

    pairs = [[probe, sel] for probe, (sel, _, _) in CASES.items()]

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1920, "height": 1080})
        page = await context.new_page()
        await page.goto(page_file.as_uri(), wait_until="load")
        await page.wait_for_timeout(600)
        tagged = await page.evaluate(TAG_JS, pairs)
        html = await page.content()
        await browser.close()

    missing = [p for p, ok in tagged.items() if not ok]
    if missing:
        # A selector that matches nothing would silently shrink the corpus and
        # make every detector look better than it is.
        print(f"selectors matched nothing: {missing}", file=sys.stderr)
        return 1

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "pages").mkdir(exist_ok=True)
    (OUT / "pages" / "test-cases.html").write_text(html)

    # The page pulls jQuery and two stylesheets by relative path; copy them so
    # the corpus is self-contained and the served page behaves as measured.
    for asset in ("assets/javascript/jquery-1.12.0.min.js",
                  "assets/javascript/main.js",
                  "assets/stylesheets/application.css",
                  "assets/stylesheets/tests.css"):
        src = SOURCE / asset
        dst = OUT / "pages" / asset
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.exists():
            dst.write_bytes(src.read_bytes())

    truth = {
        "version": 1,
        "description": (
            "GDS Accessibility Tool Audit test cases (alphagov/accessibility-tool-audit, "
            "MIT, Crown Copyright 2017). Six cases matching KAFE's IAF construct plus "
            "two correctly-built controls. Published reference: all 13 audited tools "
            "score 0/6 on the six."
        ),
        "viewports": {"desktop": {"width": 1920, "height": 1080}},
        "pages": {"pages/test-cases.html": sorted(CASES)},
        "probes": {
            probe: {"label": label, "note": note, "cohort": "gds-published"}
            for probe, (_, label, note) in CASES.items()
        },
    }
    (OUT / "truth.json").write_text(json.dumps(truth, indent=2) + "\n")

    print(
        json.dumps(
            {
                "pages": 1,
                "probes": len(CASES),
                "violations": sum(1 for _, (_, l, _) in CASES.items() if l == "violation"),
                "ok": sum(1 for _, (_, l, _) in CASES.items() if l == "ok"),
                "corpus": str(OUT),
            },
            indent=1,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
