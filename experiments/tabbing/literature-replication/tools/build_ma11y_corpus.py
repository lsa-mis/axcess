"""Build the Ma11y mutant environment: generated IAF faults with known truth.

Arms 1 and 3 are both capped by how many labelled failures somebody else built
-- 6 for GDS, 36 positives across 60 pages for KAFE. Mutation analysis generates
them, so ground truth is known by construction and N is bounded by compute.

Operators are transcribed from Ma11y (`mahantaf/web-a11y-tool-analyzer`, MIT).
Harry chose the GDS test-cases page as the base: it is MIT-licensed, static,
self-contained, and its correctly-built controls are a known-good baseline to
mutate.

F59 is **not** implemented in Ma11y -- fetching it returns a 404 body of 14
bytes -- so this builds three operators, not the four originally planned:

  F42  replaces an <a href> with a <span onclick="location.href=...">, styled to
       look like a link. Mouse-operable, not keyboard-reachable.
  F54  moves an element's onclick handler to onmousedown. Mouse-only by
       construction; already validated in `tools/ma11y_probe.py`.
  F55  adds onfocus="this.blur()", so focus is thrown away the instant it
       lands. Reachable in principle, unusable in practice.

Each mutant is a standalone page carrying exactly one injected fault, plus a
`truth.json` in the corpus format `bakeoff.py` expects: the mutated element is
labelled `violation`, and the correctly-built controls the mutation did not
touch are labelled `ok` so the corpus has negatives. Without negatives a
detector that reports everything scores perfect recall.

Pre-registered before generation:
  H-gen: each operator produces a page whose mutated element is mouse-operable
  and not keyboard-operable.
  Falsified for an operator if its mutant still activates by keyboard, or if
  the mutation does not apply.
  Control: the unmutated base page, carried as `base.html` with every control
  labelled `ok`. A detector reporting anything there is producing a false
  positive on known-good markup.

Usage:
    uv run --offline --no-sync python -m tools.build_ma11y_corpus
"""

from __future__ import annotations

import asyncio
import json
import pathlib
import sys

from playwright.async_api import async_playwright

HERE = pathlib.Path(__file__).resolve().parent.parent
GDS = HERE / "artifacts" / "gds" / "test-cases.html"
OUT = HERE / "artifacts" / "ma11y"

# Correctly-built controls on the GDS page, used as negatives. These are the
# same elements arm 1 used as its negative controls.
NEGATIVES = {
    "real-button": "button:not([class])",
    "real-link": "a[href='swift.html']",
}

# One target per operator, chosen so the operator is applicable and the element
# is unambiguous. Targets must NOT collide with a negative: aiming F55 at
# `a[href='swift.html']` made one element both the violation and the `real-link`
# control, and the second `data-probe` write silently won.
TARGETS = {
    "F42": "a[href='sheeran.html']",
    "F54": "#webchat",
    "F55": "a.button[role='button']",
}

# Transcribed from Ma11y's operator sources in `arm2/`. Each returns true when
# the mutation applied, false when the operator was not applicable.
OPERATORS = {
    # F42: link emulated with script. The span keeps every attribute except
    # href, which becomes an onclick that navigates.
    #
    # Ma11y's own version emits `window.location.href=...`, but a navigation is
    # not observable to a harness that suppresses unload (and suppressing it is
    # necessary, or the trial's counters die with the page). The handler is
    # therefore given an observable in-page effect ALONGSIDE the navigation, so
    # "mouse-operable" is measurable. The fault under test -- a span carrying a
    # click handler, unreachable by Tab -- is unchanged.
    "F42": """
    (sel) => {
        const el = document.querySelector(sel);
        if (!el || el.tagName !== 'A') return false;
        const span = document.createElement('span');
        for (const {name, value} of el.attributes) {
            if (name !== 'href') span.setAttribute(name, value);
            else span.setAttribute(
                'onclick',
                `document.title='F42-activated'; window.location.href='${value}';`
            );
        }
        span.textContent = el.textContent;
        span.style.textDecoration = 'underline';
        span.style.cursor = 'pointer';
        span.style.color = 'blue';
        span.setAttribute('data-ma11y', 'F42');
        el.parentNode.replaceChild(span, el);
        return true;
    }
    """,
    # F54: mouse-only event handler. Ma11y's own `applicable()` requires an
    # element matching `[onclick]`, i.e. an INLINE onclick attribute. The GDS
    # page has zero of those -- its handlers are all bound by jQuery -- so F54
    # is genuinely inapplicable to this base page. That is a real property of
    # the operator meeting this corpus, not a defect, and it is recorded as an
    # inapplicable operator rather than worked around by injecting the very
    # attribute the operator looks for.
    "F54": """
    (sel) => {
        const el = document.querySelector(sel);
        if (!el) return false;
        const handler = el.getAttribute('onclick');
        if (!handler) return false;
        el.setAttribute('onmousedown', handler);
        el.removeAttribute('onclick');
        el.setAttribute('data-ma11y', 'F54');
        return true;
    }
    """,
    # F55: focus is discarded the moment it arrives.
    "F55": """
    (sel) => {
        const el = document.querySelector(sel);
        if (!el) return false;
        el.setAttribute('onfocus', 'this.blur();');
        el.setAttribute('data-ma11y', 'F55');
        return true;
    }
    """,
}

# Identity for the corpus: every labelled element carries a data-probe, which is
# what both `bakeoff.py` and the frozen detectors address elements by.
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


async def build_one(browser, name: str, operator: str | None) -> dict:
    """Produce one page: the base, or the base with a single fault injected."""
    context = await browser.new_context(viewport={"width": 1920, "height": 1080})
    page = await context.new_page()
    await page.goto(GDS.as_uri(), wait_until="load")
    await page.wait_for_timeout(500)

    applied = None
    probes: dict[str, str] = {}

    if operator is not None:
        applied = await page.evaluate(OPERATORS[operator], TARGETS[operator])
        if not applied:
            await context.close()
            return {"page": name, "operator": operator, "applied": False}
        # The mutated element is the positive. F42 replaces the node, so it is
        # located by the marker the operator wrote rather than the old selector.
        probes[f"{operator.lower()}-target"] = f"[data-ma11y='{operator}']"

    # Negatives are page-scoped. The same two controls appear on every page, but
    # a probe ID identifies one element on one page -- the bakeoff enforces that
    # ("truth must assign every labelled probe to exactly one page"), so reusing
    # a bare `real-button` across three pages aborts the whole corpus.
    probes.update({f"{name}-{probe}": sel for probe, sel in NEGATIVES.items()})
    # Tag only probes that truth will actually carry. An excluded mutant left
    # tagged in the HTML makes every detector "return a probe outside the page"
    # and the bakeoff suppresses all scores for the corpus -- an unverified
    # fault must be untagged, not merely unlabelled.
    #
    # The check is positive (is this target verified?) rather than a set
    # difference against the verification file. Once an excluded target is
    # dropped from truth, the next verification run stops mentioning it at all,
    # so `seen - verified` silently becomes empty and re-tags the fault.
    verification = HERE / "derived" / "ma11y_verification.json"
    if operator is not None and verification.exists():
        target_id = f"{operator.lower()}-target"
        verified_ids = {
            row["probe"]
            for row in json.loads(verification.read_text())
            if row.get("label") == "violation" and row.get("is_iaf")
        }
        if verified_ids and target_id not in verified_ids:
            probes.pop(target_id, None)

    pairs = [[p, s] for p, s in probes.items()]
    tagged = await page.evaluate(TAG_JS, pairs)

    html = await page.content()
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "pages").mkdir(exist_ok=True)
    (OUT / "pages" / f"{name}.html").write_text(html)

    await context.close()
    return {
        "page": name,
        "operator": operator,
        "applied": applied,
        "probes": {p: tagged.get(p) for p in probes},
        "target_selector": TARGETS.get(operator) if operator else None,
    }


async def main() -> int:
    if not GDS.exists():
        print(f"missing {GDS}", file=sys.stderr)
        return 1

    built = []
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        # Control first: the unmutated page, all negatives.
        built.append(await build_one(browser, "base", None))
        for operator in sorted(OPERATORS):
            built.append(await build_one(browser, f"mutant-{operator}", operator))
        await browser.close()

    # truth.json in the shape bakeoff.py's corpus loader expects.
    #
    # A generated page only earns a `violation` label if the mutation actually
    # produced the fault. `tools/verify_ma11y_corpus.py` measures that, and any
    # operator whose target fails verification is recorded as `unverified`
    # rather than labelled. An unverified mutant scored as a violation would
    # penalise every detector for missing a fault that is not there, which is
    # worse than a smaller corpus.
    verified = set()
    verification = HERE / "derived" / "ma11y_verification.json"
    if verification.exists():
        for row in json.loads(verification.read_text()):
            if row.get("label") == "violation" and row.get("is_iaf"):
                verified.add(row["probe"])

    probes_out: dict[str, dict] = {}
    pages_out: dict[str, list[str]] = {}
    skipped: list[str] = []
    for record in built:
        if record.get("applied") is False:
            continue
        page_key = f"pages/{record['page']}.html"
        ids = []
        for probe in record.get("probes", {}):
            is_target = probe.endswith("-target")
            if is_target and verification.exists() and probe not in verified:
                skipped.append(probe)
                continue
            probes_out[probe] = {
                "label": "violation" if is_target else "ok",
                "note": (
                    f"{record['operator']} mutant of {record['target_selector']}, "
                    "verified mouse-operable and not keyboard-operable"
                    if is_target
                    else "correctly-built control, untouched by the mutation"
                ),
                "cohort": "ma11y-generated",
            }
            ids.append(probe)
        pages_out[page_key] = ids

    truth = {
        "version": 1,
        "description": (
            "Ma11y-generated IAF faults on the GDS test-cases page. Ground truth "
            "is known by construction AND verified behaviourally: only mutants "
            "measured mouse-operable and not keyboard-operable carry a violation "
            "label. F59 is not implemented in Ma11y (404). F54 is inapplicable "
            "to this base page, which has zero inline onclick attributes. F42's "
            "generated span did not activate on a trusted click, so it is "
            "excluded rather than labelled."
        ),
        "viewports": {"desktop": {"width": 1920, "height": 1080}},
        "pages": pages_out,
        "probes": probes_out,
    }
    (OUT / "truth.json").write_text(json.dumps(truth, indent=2) + "\n")

    for record in built:
        print(json.dumps(record))
    print()
    if skipped:
        print(f"EXCLUDED, mutation did not produce a verified fault: {skipped}")
    print(
        json.dumps(
            {
                "pages": len(pages_out),
                "probes": len(probes_out),
                "violations": sum(
                    1 for v in probes_out.values() if v["label"] == "violation"
                ),
                "ok": sum(1 for v in probes_out.values() if v["label"] == "ok"),
                "excluded_unverified": skipped,
                "corpus": str(OUT),
            },
            indent=1,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
