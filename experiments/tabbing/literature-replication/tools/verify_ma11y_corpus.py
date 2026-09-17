"""Verify the generated mutants carry the fault they claim.

A mutation operator that produces an *equivalent* mutant -- one that applies
cleanly but changes no behaviour -- would silently inflate recall on a corpus
nobody hand-checked. Ground truth "by construction" is only ground truth if the
construction is verified, so this checks each generated page before any detector
is scored against it.

Pre-registered:
  H-gen: on each mutant page, the mutated element is mouse-operable and NOT
  keyboard-operable.
  Falsified for an operator if its target still activates by keyboard, or is not
  mouse-operable either (in which case it is not an IAF, it is just broken).
  Control: `base.html`, unmutated. Its two correctly-built controls must be both
  mouse- AND keyboard-operable. If a negative fails there, the harness is wrong
  rather than the page.
  N=2 per page, order alternated.

Usage:
    uv run --offline --no-sync python -m tools.verify_ma11y_corpus
"""

from __future__ import annotations

import asyncio
import json
import pathlib

from playwright.async_api import async_playwright

HERE = pathlib.Path(__file__).resolve().parent.parent
CORPUS = HERE / "artifacts" / "ma11y"
OUT = HERE / "derived" / "ma11y_verification.json"

PROBE_JS = """
(probe) => {
    const el = document.querySelector(`[data-probe="${probe}"]`);
    if (!el) return {found: false};
    const tag = el.tagName.toLowerCase();
    const ti = el.getAttribute('tabindex');
    const nativelyFocusable =
        ['button','input','select','textarea'].includes(tag) ||
        (tag === 'a' && el.hasAttribute('href'));
    const r = el.getBoundingClientRect();
    return {
        found: true,
        tag,
        rendered: r.width > 0 && r.height > 0,
        keyboard_reachable: nativelyFocusable || (ti !== null && ti !== '-1'),
        has_onfocus_blur: (el.getAttribute('onfocus') || '').includes('blur'),
        mutated: el.getAttribute('data-ma11y'),
    };
}
"""

INSTRUMENT_JS = """
(probe) => {
    window.__hits = {mouse: 0, key: 0};
    window.__mode = null;
    document.addEventListener('click', (e) => e.preventDefault(), true);
    window.open = () => null;
    window.onbeforeunload = () => '';
    const el = document.querySelector(`[data-probe="${probe}"]`);
    if (!el) return false;
    // Count by how the event arrived, not by which listener fired: a trusted
    // pointer click has detail > 0, a keyboard-synthesised one does not.
    el.addEventListener('click', (e) => {
        if (e.detail === 0) window.__hits.key++; else window.__hits.mouse++;
    });
    el.addEventListener('keypress', () => { window.__hits.key++; });
    return true;
}
"""


async def check(browser, page_file: pathlib.Path, probe: str) -> dict:
    """One probe, mouse and keyboard measured in separate fresh contexts."""
    result = {"page": page_file.stem, "probe": probe}

    for mode in ("mouse", "keyboard"):
        context = await browser.new_context(viewport={"width": 1920, "height": 1080})
        page = await context.new_page()
        await page.goto(page_file.as_uri(), wait_until="load")
        await page.wait_for_timeout(400)

        info = await page.evaluate(PROBE_JS, probe)
        if not info.get("found"):
            await context.close()
            return {**result, "found": False}
        result.update({k: v for k, v in info.items() if k != "found"})

        await page.evaluate(INSTRUMENT_JS, probe)

        if mode == "mouse":
            box = await page.evaluate(
                """(probe) => {
                    const el = document.querySelector(`[data-probe="${probe}"]`);
                    el.scrollIntoView({block: 'center', behavior: 'instant'});
                    const r = el.getBoundingClientRect();
                    return r.width && r.height
                         ? {x: r.x + r.width/2, y: r.y + r.height/2} : null;
                }""",
                probe,
            )
            if box:
                await page.mouse.click(box["x"], box["y"])
                await page.wait_for_timeout(120)
            result["activates_by_mouse"] = (
                await page.evaluate("(window.__hits && window.__hits.mouse) || 0")
            ) > 0
        else:
            try:
                await page.eval_on_selector(
                    f'[data-probe="{probe}"]', "el => el.focus()"
                )
                await page.keyboard.press("Enter")
                await page.wait_for_timeout(120)
            except Exception:
                pass
            result["activates_by_keyboard"] = (
                await page.evaluate("(window.__hits && window.__hits.key) || 0")
            ) > 0

        await context.close()

    result["is_iaf"] = bool(
        result.get("activates_by_mouse") and not result.get("activates_by_keyboard")
    )
    return result


async def main() -> int:
    truth = json.loads((CORPUS / "truth.json").read_text())
    rows = []

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        for repeat in range(2):
            pages = sorted(truth["pages"].items())
            if repeat:
                pages.reverse()
            for page_key, probes in pages:
                page_file = CORPUS / page_key
                for probe in probes:
                    row = await check(browser, page_file, probe)
                    row["repeat"] = repeat
                    row["label"] = truth["probes"][probe]["label"]
                    rows.append(row)
        await browser.close()

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(rows, indent=2) + "\n")

    first = [r for r in rows if r["repeat"] == 0]
    print(f"{'page':<16}{'probe':<16}{'label':<11}{'mouse':<8}{'key':<8}{'is_iaf'}")
    for r in first:
        print(
            f"{r['page']:<16}{r['probe']:<16}{r['label']:<11}"
            f"{str(r.get('activates_by_mouse')):<8}"
            f"{str(r.get('activates_by_keyboard')):<8}{r.get('is_iaf')}"
        )

    violations = [r for r in first if r["label"] == "violation"]
    negatives = [r for r in first if r["label"] == "ok"]
    stable = all(
        next(
            (
                s.get("is_iaf") == r.get("is_iaf")
                for s in rows
                if s["repeat"] == 1
                and s["page"] == r["page"]
                and s["probe"] == r["probe"]
            ),
            True,
        )
        for r in first
    )
    print()
    print(
        json.dumps(
            {
                "violations_confirmed_iaf": sum(1 for r in violations if r["is_iaf"]),
                "violations_total": len(violations),
                "negatives_operable_both_ways": sum(
                    1
                    for r in negatives
                    if r.get("activates_by_mouse") and r.get("activates_by_keyboard")
                ),
                "negatives_total": len(negatives),
                "reproducible": stable,
                "H-gen_falsified": any(not r["is_iaf"] for r in violations),
            },
            indent=1,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
