"""Diagnose and control the CDP pierced-tree failure, against real pages.

The edgecases matrix run aborted with

    CDPSession.send: Protocol error (DOM.getDocument): Failed to convert
    response to JSON: CBOR: stack limit exceeded at position 53429

which suppressed every score for the corpus. This answers the three questions
that decide what the fix should be, and then checks the fix:

  survey    which page triggers it, and how deep that page's DOM is
  bisect    is it a nesting limit or a size limit
  control   does the paged fallback return the same tree the unbounded call
            returns, on pages where the unbounded call still works

    uv run --offline --no-sync python -m tools.diagnose_pierced_tree survey edgecases
    uv run --offline --no-sync python -m tools.diagnose_pierced_tree bisect edgecases pages/scale.html
    uv run --offline --no-sync python -m tools.diagnose_pierced_tree control
"""

from __future__ import annotations

import argparse
import asyncio
import json
import pathlib
import sys

sys.path.insert(0, "src")
sys.path.insert(0, ".")

from playwright.async_api import async_playwright  # noqa: E402

from experiments.tabbing.runner import upstream_candidates as uc  # noqa: E402
from experiments.tabbing.runner.bakeoff import VIEWPORT  # noqa: E402
from experiments.tabbing.runner.serve import ContextFactory, page_url  # noqa: E402

CORPUS_ROOTS = {
    "fixtures": "experiments/tabbing/fixtures",
    "edgecases": "experiments/tabbing/edgecases",
    "gds": "experiments/tabbing/literature-replication/artifacts/gds-corpus",
    "ma11y": "experiments/tabbing/literature-replication/artifacts/ma11y",
}

PROBE_ATTR = "data-probe"

DEPTH_JS = r"""
() => {
  let max = 0, deepest = '';
  const walk = (node, d, path) => {
    if (d > max) { max = d; deepest = path; }
    if (node.shadowRoot) walk(node.shadowRoot, d + 1, path + ' >> #shadow');
    for (const c of node.children)
      walk(c, d + 1, path + ' > ' + c.tagName.toLowerCase());
  };
  walk(document.documentElement, 1, 'html');
  return {max, deepest: deepest.slice(-160),
          elements: document.querySelectorAll('*').length};
}
"""


class ForcedFail:
    """Makes only the unbounded call fail, exactly as Chromium does on a deep page."""

    def __init__(self, cdp):
        self.cdp = cdp

    async def send(self, method, params=None):
        if method == "DOM.getDocument" and (params or {}).get("depth") == -1:
            raise RuntimeError(
                "Protocol error (DOM.getDocument): Failed to convert response to "
                "JSON: CBOR: stack limit exceeded at position 53429"
            )
        return await self.cdp.send(method, params)


def probes_in(root: dict) -> list[str]:
    found: list[str] = []

    def walk(node):
        attrs = node.get("attributes") or []
        for i in range(0, len(attrs) - 1, 2):
            if attrs[i] == PROBE_ATTR:
                found.append(attrs[i + 1])
        for key in ("children", "shadowRoots"):
            for child in node.get(key) or []:
                walk(child)
        for key in ("contentDocument", "templateContent"):
            if node.get(key):
                walk(node[key])

    walk(root)
    return sorted(found)


def shape(node: dict) -> dict:
    """nodeIds differ between fetch strategies; structure and attributes must not."""
    out = {k: node[k] for k in ("nodeName", "nodeType", "attributes") if k in node}
    for key in ("children", "shadowRoots"):
        if node.get(key):
            out[key] = [shape(c) for c in node[key]]
    for key in ("contentDocument", "templateContent"):
        if node.get(key):
            out[key] = shape(node[key])
    return out


async def open_page(pw, root: pathlib.Path, page_path: str):
    browser = await pw.chromium.launch(headless=True)
    factory = ContextFactory(browser, VIEWPORT, root)
    ctx = await factory()
    pg = await ctx.new_page()
    await pg.goto(page_url(page_path), wait_until="load")
    await pg.wait_for_timeout(120)
    return browser, ctx, pg


async def survey(corpus: str) -> None:
    root = pathlib.Path(CORPUS_ROOTS[corpus])
    truth = json.loads((root / "truth.json").read_text())
    async with async_playwright() as pw:
        for page_path in sorted(truth["pages"]):
            browser, ctx, pg = await open_page(pw, root, page_path)
            info = await pg.evaluate(DEPTH_JS)
            cdp = await pg.context.new_cdp_session(pg)
            try:
                await cdp.send("DOM.getDocument", {"depth": -1, "pierce": True})
                verdict = "ok"
            except Exception as exc:
                verdict = f"FAIL {str(exc).splitlines()[0][:70]}"
            print(f"{page_path:<36} depth={info['max']:>4} els={info['elements']:>5}  {verdict}")
            if verdict != "ok":
                print(f"    deepest: ...{info['deepest']}")
            await ctx.close()
            await browser.close()


async def bisect(corpus: str, page_path: str) -> None:
    root = pathlib.Path(CORPUS_ROOTS[corpus])
    async with async_playwright() as pw:
        browser, ctx, pg = await open_page(pw, root, page_path)
        cdp = await pg.context.new_cdp_session(pg)
        for depth in (1, 25, 50, 100, 120, 140, 145, 148, 150, 154, 160, -1):
            try:
                doc = await cdp.send("DOM.getDocument", {"depth": depth, "pierce": True})
                print(f"depth={depth:>4}  ok    response_bytes={len(json.dumps(doc))}")
            except Exception as exc:
                print(f"depth={depth:>4}  FAIL  {str(exc).splitlines()[0][:80]}")
        await ctx.close()
        await browser.close()


async def control() -> None:
    cases = [
        ("edgecases", "pages/scale.html", True),
        ("edgecases", "pages/shadow-tab-scope.html", False),
        ("edgecases", "pages/iframe-tab-scope.html", False),
        ("fixtures", "upstream/h-shadow.html", False),
        ("fixtures", "upstream/b-decoys.html", False),
    ]
    async with async_playwright() as pw:
        for corpus, page_path, paged_only in cases:
            root = pathlib.Path(CORPUS_ROOTS[corpus])
            browser, ctx, pg = await open_page(pw, root, page_path)
            cdp = await pg.context.new_cdp_session(pg)
            paged = await uc.get_pierced_document(ForcedFail(cdp))
            if paged_only:
                print(f"{page_path:<32} unbounded impossible; paged finds {probes_in(paged)}")
            else:
                direct = await uc.get_pierced_document(cdp)
                same = shape(direct) == shape(paged)
                print(f"{page_path:<32} identical={same}  probes={probes_in(direct)}")
                if not same:
                    print("    MISMATCH — the fallback does not reproduce the direct tree")
            await ctx.close()
            await browser.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("survey", "bisect", "control"))
    parser.add_argument("corpus", nargs="?", default="edgecases", choices=sorted(CORPUS_ROOTS))
    parser.add_argument("page", nargs="?", default="pages/scale.html")
    args = parser.parse_args()

    if args.mode == "survey":
        asyncio.run(survey(args.corpus))
    elif args.mode == "bisect":
        asyncio.run(bisect(args.corpus, args.page))
    else:
        asyncio.run(control())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
