"""Check fixes from an Axcess fix brief with axe-core and Playwright.

Axcess copies this file, word for word, into every fix brief
(:mod:`audit.exports.fix_brief`). A coding agent saves it as
``axcess_check.py`` and runs it to check a fix the same way the scan found
the problem: it opens the page in Chromium with Playwright, adds the
axe-core version the brief names, and runs only the one axe rule of the issue
type. The result is the exit code, so it is the same every time for the same
page code:

* 0: passed. The rule no longer fails at the element (or, for a whole issue
  type, anywhere on the listed pages).
* 1: failed. The rule still fails there.
* 2: could not check. For example the element is gone, its locator now
  matches more than one element, the place appears only after a click, the
  axe-core version is not the one the brief names, the page did not load or answered with
  an error (such as 404 Not Found), or axe-core could not decide (an
  "incomplete" result). A person or a new scan in Axcess has to decide.

A pass is never the default. The script finds the saved element in the page
first, and it must match exactly one element. axe-core then hands back the
elements it checked, and the script compares those elements themselves with
the saved one, not their locator text: axe-core can describe one element with
a different locator after a change (adding ``id="hero"`` turns ``img`` into
``#hero``), and a text match would then call a failing element a pass.

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
# Finds the saved element (when there is a locator to look for), runs the one
# rule, and says for each element axe-core reported whether it is that same
# element (``===`` on the element itself, through axe-core's ``elementRef``).
# ``count`` is how many elements the locator matches, or -1 if it is not a
# valid locator in this browser.
_RUN_RULE = """async ([rule, locator]) => {
    let saved = null;
    let count = null;
    if (locator !== null) {
        try {
            const found = document.querySelectorAll(locator);
            count = found.length;
            if (count === 1) saved = found[0];
        } catch (e) {
            count = -1;
        }
    }
    const result = await window.axe.run(document, {
        runOnly: { type: 'rule', values: [rule] },
        resultTypes: ['violations', 'incomplete'],
        elementRef: true,
    });
    const nodes = (results) => results.flatMap((r) => r.nodes.map((n) => ({
        target: n.target,
        saved: saved !== null && n.element === saved,
    })));
    return { count, failing: nodes(result.violations), unsure: nodes(result.incomplete) };
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


def response_problem(response: Any) -> str | None:
    """Why a page's response cannot be checked, or None if it can.

    Playwright does not treat an error page as a failure: a 404 or 500 page
    loads like any other. Checking it would check the error page, and a rule
    such as ``html-has-lang`` could pass there.
    """

    if response is None:
        return "the browser got no response for it"
    status = int(response.status)
    if not 200 <= status < 300:
        return f"it answered with HTTP status {status}, not the page"
    return None


def verdict(
    place: dict[str, Any], outcome: dict[str, Any], *, whole_page: bool, url: str
) -> tuple[int, str]:
    """The result for one place, from what axe-core reported on its page.

    ``outcome`` is what the in-page check returned: ``count`` (how many
    elements the saved locator matches, -1 if it is not valid, None if no
    locator was looked for), and the ``failing`` and ``unsure``
    (axe-core "incomplete") elements, each with its ``target`` and whether it
    is the ``saved`` element itself.
    """

    failing = outcome["failing"]
    unsure = outcome["unsure"]
    if whole_page or not place["locator_exact"]:
        if failing:
            return FAILED, f"{len(failing)} element(s) on {url}"
        if unsure:
            return NOT_CHECKED, f"axe-core could not decide {len(unsure)} element(s) on {url}"
        return PASSED, f"no element fails the rule on {url}"
    count = outcome["count"]
    if count == 0:
        return NOT_CHECKED, f"the element is no longer found on {url}"
    if count is None or count < 0:
        return NOT_CHECKED, f"the saved element locator does not work in this browser on {url}"
    if count > 1:
        return (
            NOT_CHECKED,
            f"the saved element locator now matches {count} elements on {url}, so the "
            "result cannot be tied to the one element",
        )
    if any(node["saved"] for node in failing):
        return FAILED, f"the element on {url}"
    if any(node["saved"] for node in unsure):
        return NOT_CHECKED, f"axe-core could not decide whether the element passes on {url}"
    return PASSED, f"the element on {url}"


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
            whole_page = bool(args.whole_page or not place["locator_exact"])
            try:
                response = page.goto(url, wait_until="load", timeout=args.timeout * 1000)
                problem = response_problem(response)
                if problem is not None:
                    print(f"NOT CHECKED {label}: {url} was not checked: {problem}.")
                    worst = max(worst, NOT_CHECKED)
                    continue
                page.evaluate(axe_source)
                version = page.evaluate("() => window.axe.version")
                outcome = page.evaluate(
                    _RUN_RULE, [place["rule"], None if whole_page else place["locator"]]
                )
            except Exception as error:  # any failure means "not checked"
                print(f"NOT CHECKED {label}: {url} could not be checked: {error}")
                worst = max(worst, NOT_CHECKED)
                continue
            if version != checks["axe_version"]:
                print(
                    f"NOT CHECKED {label}: axe-core {version}, the brief names "
                    f"{checks['axe_version']}."
                )
                worst = max(worst, NOT_CHECKED)
                continue
            status, where = verdict(place, outcome, whole_page=whole_page, url=url)
            word = {PASSED: "PASSED", FAILED: "FAILED", NOT_CHECKED: "NOT CHECKED"}[status]
            print(f"{word} {label}: {where}")
            if status != PASSED:
                for node in outcome["failing"][:10]:
                    print(f"  still failing: {target_text(node['target'])}")
                for node in outcome["unsure"][:10]:
                    print(f"  axe-core could not decide: {target_text(node['target'])}")
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
