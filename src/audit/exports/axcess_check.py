"""Check fixes from an Axcess fix brief with axe-core and Playwright.

Axcess copies this file, word for word, into every fix brief
(:mod:`audit.exports.fix_brief`). A coding agent saves it as
``axcess_check.py`` and runs it to check a fix the same way the scan found
the problem: it opens the page in Chromium with Playwright, adds the same
axe-core version the scan used, and runs only the one axe rule of the issue
type. The result is the exit code, so it is the same every time for the same
page code:

* 0: passed. The rule no longer fails at the element (or, for a whole issue
  type, anywhere on the listed pages).
* 1: failed. The rule still fails there.
* 2: could not check. For example the element is gone, the place appears only
  after a click, the axe-core version is not the scan's, or the page did not
  load. A person or a new scan in Axcess has to decide.

It reads its checks from the brief itself, from the one ``untrusted-data``
block that holds the JSON written by Axcess. Page addresses and element
locators come from the scanned site, so they are only ever data here: they
go to Playwright and axe-core as values, never into a shell command.

Needs Python 3.9 or later, ``pip install playwright``,
``playwright install chromium``, and axe-core's ``axe.min.js``.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

FORMAT = "axcess-fix-brief-checks/1"
PASSED, FAILED, NOT_CHECKED = 0, 1, 2

_FENCE = re.compile(r"^(`{3,})untrusted-data\n(.*?)\n\1$", re.MULTILINE | re.DOTALL)
_RUN_RULE = """async (rule) => {
    const result = await window.axe.run(document, {
        runOnly: { type: 'rule', values: [rule] },
        resultTypes: ['violations'],
    });
    return result.violations.flatMap((v) => v.nodes.map((n) => n.target));
}"""
_COUNT = """(selector) => {
    try { return document.querySelectorAll(selector).length; } catch (e) { return -1; }
}"""


def load_checks(brief_text: str) -> dict[str, Any]:
    """The checks JSON from the brief's one Axcess checks block."""

    found = []
    for match in _FENCE.finditer(brief_text.replace("\r\n", "\n")):
        try:
            data = json.loads(match.group(2))
        except ValueError:
            continue
        if isinstance(data, dict) and data.get("format") == FORMAT:
            found.append(data)
    if len(found) != 1:
        raise ValueError(f"expected 1 checks block in the brief, found {len(found)}")
    return found[0]


def pick(checks: dict[str, Any], wanted: str) -> list[dict[str, Any]]:
    """The places for ``3.1`` (one place) or ``3`` (every place of issue type 3)."""

    places = checks["places"]
    if wanted in places:
        return [places[wanted]]
    chosen = [places[key] for key in places if key.split(".")[0] == wanted]
    if not chosen:
        raise KeyError(f"no check {wanted!r} in this brief")
    return chosen


def with_origin(url: str, origin: str | None) -> str:
    """``url`` on ``origin`` (for example your local copy of the site)."""

    if not origin:
        return url
    new, old = urlsplit(origin), urlsplit(url)
    return urlunsplit((new.scheme, new.netloc, old.path, old.query, ""))


def target_text(target: list[Any]) -> str:
    """axe's target list as one locator, joined the way Axcess saved it."""

    text = " > ".join(str(part) for part in target) if target else "(unknown)"
    return " ".join(text.split())


def run(args: argparse.Namespace) -> int:
    from playwright.sync_api import sync_playwright

    checks = load_checks(Path(args.brief).read_text(encoding="utf-8"))
    places = pick(checks, args.check)
    axe_source = Path(args.axe).read_text(encoding="utf-8")
    worst = PASSED
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport=checks["viewport"])
        for place in places:
            label = f"check {place['id']} ({place['rule']})"
            if place["after_click"]:
                print(f"NOT CHECKED {label}: this place appears only after a click.")
                worst = max(worst, NOT_CHECKED)
                continue
            if not place["page_exact"]:
                print(f"NOT CHECKED {label}: its page address was cut short or redacted.")
                worst = max(worst, NOT_CHECKED)
                continue
            url = with_origin(place["page"], args.origin)
            try:
                page.goto(url, wait_until="load", timeout=args.timeout * 1000)
                page.evaluate(axe_source)
                version = page.evaluate("() => window.axe.version")
                failing = [target_text(t) for t in page.evaluate(_RUN_RULE, place["rule"])]
            except Exception as error:  # any failure means "not checked"
                print(f"NOT CHECKED {label}: {url} could not be checked: {error}")
                worst = max(worst, NOT_CHECKED)
                continue
            if version != checks["axe_version"]:
                print(
                    f"NOT CHECKED {label}: axe-core {version}, the scan used "
                    f"{checks['axe_version']}."
                )
                worst = max(worst, NOT_CHECKED)
                continue
            if args.whole_page or not place["locator_exact"]:
                status = FAILED if failing else PASSED
                where = f"{len(failing)} element(s) on {url}"
            elif place["locator"] in failing:
                status, where = FAILED, f"the element on {url}"
            elif page.evaluate(_COUNT, place["locator"]) < 1:
                status, where = NOT_CHECKED, f"the element is no longer found on {url}"
            else:
                status, where = PASSED, f"the element on {url}"
            word = {PASSED: "PASSED", FAILED: "FAILED", NOT_CHECKED: "NOT CHECKED"}[status]
            print(f"{word} {label}: {where}")
            if status != PASSED and failing:
                for locator in failing[:10]:
                    print(f"  still failing: {locator}")
            worst = max(worst, status)
        browser.close()
    return worst


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("brief", help="the fix brief, saved as a Markdown file")
    parser.add_argument("check", help="a place such as 3.1, or an issue type such as 3")
    parser.add_argument("--axe", default="axe.min.js", help="path to axe-core's axe.min.js")
    parser.add_argument("--origin", help="check your copy instead, e.g. http://127.0.0.1:8000")
    parser.add_argument(
        "--whole-page",
        action="store_true",
        help="fail if the rule fails anywhere on the page, not only at the element",
    )
    parser.add_argument("--timeout", type=int, default=30, help="seconds to load a page")
    args = parser.parse_args(argv)
    try:
        return run(args)
    except (OSError, ValueError, KeyError) as error:
        print(f"NOT CHECKED: {error}")
        return NOT_CHECKED


if __name__ == "__main__":
    sys.exit(main())
