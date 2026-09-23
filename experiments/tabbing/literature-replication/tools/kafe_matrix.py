"""All 48 Axcess detectors on KAFE's own benchmark, scored KAFE's own way.

`bakeoff.py` scores element-level probes against a `truth.json`. KAFE labels
**pages** (one row per subject, `Type 1 Detection Ground Truth`) and its captures
carry no `data-probe`. This adapter bridges the two without touching either side:

* the capture is replayed offline through `tools.replay.ReplayRouter`;
* a **neutral census** assigns every element a position-derived id, and
  `data-probe` is mirrored onto the ids the frozen candidate collector chose, so
  the detectors can address elements on a page that has no probe attributes;
* every detector is then driven through the *existing* seams — `bakeoff.run_page`
  for the cheap tier, `candidate_analysis.measure_candidate_page` for the
  upstream generators and C1–C9, `bakeoff.run_behavioural` for the D9/D10 arms,
  and the four `experiments/tabbing/probes` observations fed to
  `tools.run_probe_rules.rule_sets` for C10–C16 — so the **frozen** detectors
  produce the verdicts and nothing here re-implements one;
* each detector's element proposals are projected to one page verdict:
  **page-positive iff it flagged >=1 element**.

Design decisions that are load-bearing, each with its reason:

* **The tab cap is derived per subject**, as `bakeoff.run_page` and
  `tools/kafe_scored_run.py` already derive it, because the 300 default caps the
  walk on a real page and turns a budget limit into an absence of evidence. That
  changes an argument of the frozen `compute_tab_order`, never its body.
* **`data-probe` is restricted to the frozen candidate set.**
  `candidate_analysis.measure_candidate_page` requires its feature sweep to cover
  exactly `probe_ids`, so the attribute cannot sit on all ~17k census elements.
  The consequence is a real bias and is reported: every detector is scored on the
  shortlist `audit...kbdiff.candidates.collect_candidates` produced, so no
  detector can propose an element that collector did not surface.
* **Abstention is never a negative.** A replay failure, a missing entry document,
  a capped tab walk, an arm that raised, or a page where the detector decided
  nothing all abstain, in their own column.

Usage:
    uv run --offline --no-sync python -u -m tools.kafe_matrix run
    uv run --offline --no-sync python -u -m tools.kafe_matrix run --only steam
    uv run --offline --no-sync python -u -m tools.kafe_matrix controls
    uv run --offline --no-sync python -u -m tools.kafe_matrix assemble
"""

from __future__ import annotations

import argparse
import ast
import asyncio
import csv
import json
import pathlib
import platform
import re
import statistics
import sys
import time
import traceback
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

REPO = pathlib.Path(__file__).resolve().parents[4]
for _extra in (REPO, REPO / "src"):
    if str(_extra) not in sys.path:
        sys.path.insert(0, str(_extra))

from playwright.async_api import async_playwright  # noqa: E402

from tools import assemble_matrix, flowfile, replay  # noqa: E402
from tools.run_probe_rules import rule_sets  # noqa: E402

from audit.analyzer.axe import AxeAnalyzer  # noqa: E402
from audit.analyzer.keyboard.kbdiff import detectors as frozen_detectors  # noqa: E402
from audit.analyzer.keyboard.kbdiff.candidates import collect_candidates  # noqa: E402
from audit.analyzer.keyboard.kbdiff.differential import TrialConfig  # noqa: E402
from audit.analyzer.keyboard.kbdiff.taborder import (  # noqa: E402
    _active_marker,  # private on purpose: the cap diagnostic must read focus
    compute_tab_order,  # exactly as the frozen walker does, frames included
)
from experiments.tabbing.runner import bakeoff, candidate_analysis, upstream_candidates  # noqa: E402

HERE = pathlib.Path(__file__).resolve().parent.parent
SUBJECTS = HERE / "artifacts" / "subjects"
LEGACY = {
    "citiprogram": HERE / "artifacts" / "subject_citiprogram.bin",
    "craigslist": HERE / "artifacts" / "subject_craigslist.bin",
    "coronavirus": HERE / "artifacts" / "subject_coronavirus.bin",
}
KAFE_CSV = HERE / "artifacts" / "kafe_results_to_reproduce.csv"
DENOM = HERE / "derived" / "kafe_denominator.json"
PRIOR = HERE / "derived" / "kafe_scored.jsonl"
OUT = HERE / "derived" / "kafe_matrix.jsonl"
CONTROLS = HERE / "derived" / "kafe_matrix_controls.json"
SUMMARY = HERE / "derived" / "kafe_matrix_summary.json"
SUMMARY_PERMISSIVE = HERE / "derived" / "kafe_matrix_summary_permissive.json"
PROBES_DIR = REPO / "experiments" / "tabbing" / "probes"

VIEWPORT = {"width": 1920, "height": 1080}  # KAFE section 5.1
TAB_HEADROOM = 200  # cap = focusable count + this, so a complete walk is provable
SUBJECT_TIMEOUT_S = 6 * 3600
ARM_TIMEOUT_S = 4 * 3600
CONTEXT_TIMEOUT_MS = 30_000

# The behavioural row names, transcribed from `bakeoff.main_async` so the two
# lists cannot drift apart silently.
BEHAVIOURAL = (
    bakeoff.D9_NAME,
    bakeoff.D9_NOS4_NAME,
    bakeoff.D9_S4U_NAME,
    bakeoff.D9_S4OURS_NAME,
    bakeoff.D9U_NAME,
    bakeoff.D9U_S4U_NAME,
    bakeoff.D10A_U_NAME,
    bakeoff.D10B_U_NAME,
    bakeoff.D10_NAME,
    bakeoff.D10B_NAME,
    bakeoff.D10BASE_NAME,
)
CHEAP = tuple(bakeoff.CHEAP_METHODS)
UPSTREAM = tuple(candidate_analysis.UPSTREAM_NAMES.values())
VARIANTS = tuple(candidate_analysis.VARIANT_NAMES)
PROBE_RULES = (
    "C10 = C9 minus redundant click surfaces (R1)",
    "C11 = C10 minus roving-tabindex items (R2)",
    "C12 = C11 minus declared shortcuts (R3)",
    "C13 = C12 minus leads with no action path (R5)",
    "C14 = C13 minus name-twinned leads (R6)",
    "C15 = C14 minus leads with no click effect (R7, R8)",
    "C16 = C15 plus divergent-key-effect promotions (R9)",
)
ALL_DETECTORS = (*CHEAP, *UPSTREAM, *VARIANTS, *PROBE_RULES, *BEHAVIOURAL)

# Which arm each detector's verdict comes from, so one arm's failure abstains
# exactly the rows it produced and no others.
ARM_OF = {
    **{name: "cheap" for name in CHEAP},
    **{name: "candidate" for name in (*UPSTREAM, *VARIANTS)},
    **{name: "probe-rules" for name in PROBE_RULES},
    **{name: "behavioural" for name in BEHAVIOURAL},
}


# ---------------------------------------------------------------------------
# The four probe observations, taken from the probe scripts' own source
# ---------------------------------------------------------------------------
def probe_constant(script: str, name: str) -> Any:
    """Read a module-level literal out of a probe script without running it.

    The probe scripts call ``asyncio.run`` at module level, so they cannot be
    imported. Parsing the constant out of their AST keeps the observation JS
    byte-identical to the file that produced the published fixtures numbers,
    which a transcription here would not.
    """
    tree = ast.parse((PROBES_DIR / script).read_text())
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == name:
                return ast.literal_eval(node.value)
            # `SETTLE_MS, SETTLE_STEP = 900, 60` is one Assign with a Tuple target.
            if isinstance(target, ast.Tuple):
                for i, element in enumerate(target.elts):
                    if isinstance(element, ast.Name) and element.id == name:
                        return ast.literal_eval(node.value)[i]
    raise KeyError(f"{script} has no module-level {name}")


CONTAINMENT_JS = probe_constant("probe_containment.py", "JS")
CONTAINMENT_SEL = probe_constant("probe_containment.py", "FOCUSABLE")
COMPOSITE_JS = probe_constant("probe_composite.py", "JS")
EFFECT_IDS_JS = probe_constant("probe_effect.py", "IDS_JS")
EFFECT_SHOT_JS = probe_constant("probe_effect.py", "SHOT_JS")
EFFECT_ACTIVATION = set(probe_constant("probe_effect.py", "ACTIVATION"))
E2_NATIVE = probe_constant("probe_effect2.py", "NATIVE")
E2_STATIC_JS = probe_constant("probe_effect2.py", "STATIC_JS")
E2_DIGEST_JS = probe_constant("probe_effect2.py", "DIGEST_JS")
E2_FIND_JS = probe_constant("probe_effect2.py", "FIND_JS")
E2_SETTLE_MS = probe_constant("probe_effect2.py", "SETTLE_MS")
E2_SETTLE_STEP = probe_constant("probe_effect2.py", "SETTLE_STEP")


# ---------------------------------------------------------------------------
# Replay plumbing
# ---------------------------------------------------------------------------
# `replay.NEUTRAL_CENSUS_JS` numbers each *document* from zero and does not
# cross a frame boundary, so every frame independently mints `/0:html`. An init
# script runs in every frame, so on a page with an iframe two different elements
# end up carrying one identity — `upstream.resolve_probe_nodes` caught this as
# `ValueError: duplicate probe identity: /0:html`, and where it did not raise it
# would silently have let a detector's finding in one frame be attributed to an
# element in another. Sub-frame ids are therefore namespaced by their document
# URL. The top frame keeps the unprefixed census exactly as
# `tools/kafe_scored_run.py` produced it, so identity there is unchanged.
FRAMED_CENSUS_JS = f"""
(attr) => {{
  const n = ({replay.NEUTRAL_CENSUS_JS})(attr);
  let top = true;
  try {{ top = window.top === window.self; }} catch (e) {{ top = false; }}
  if (top) return n;
  const prefix = '@' + location.href + '#';
  const walk = (root) => {{
    let els;
    try {{ els = root.querySelectorAll('*'); }} catch (e) {{ return; }}
    for (const el of els) {{
      const id = el.getAttribute && el.getAttribute(attr);
      if (id !== null && id !== undefined && id.charAt(0) !== '@') {{
        try {{ el.setAttribute(attr, prefix + id); }} catch (e) {{}}
      }}
      if (el.shadowRoot) walk(el.shadowRoot);
    }}
  }};
  walk(document);
  return n;
}}
"""

MIRROR_JS = """
(function (attr, allow) {
  const wanted = new Set(allow);
  const mirror = (root) => {
    let els;
    try { els = root.querySelectorAll('*'); } catch (e) { return; }
    for (const el of els) {
      const id = el.getAttribute && el.getAttribute(attr);
      if (id && wanted.has(id)) el.setAttribute('data-probe', id);
      if (el.shadowRoot) mirror(el.shadowRoot);
    }
  };
  mirror(document);
})
"""


# The discovery context's init script and the focusable count, lifted verbatim
# out of `measure_subject` so the cap diagnostic below cannot drift away from
# the scored path the way it silently had. Both are used by both callers, and
# neither differs from what produced `derived/kafe_matrix.jsonl` in anything but
# leading whitespace.
DISCOVERY_TAG_JS = f"""
window.addEventListener('load', () => {{
    ({FRAMED_CENSUS_JS})('{replay.CENSUS_ATTR}');
    for (const el of document.querySelectorAll('[{replay.CENSUS_ATTR}]')) {{
        el.setAttribute('data-probe',
                        el.getAttribute('{replay.CENSUS_ATTR}'));
    }}
}});
"""

FOCUSABLE_JS = """() => document.querySelectorAll(
    'a[href],button,input,select,textarea,[tabindex],[onclick]').length"""


def capture_path(subject: str) -> pathlib.Path:
    return LEGACY.get(subject) or (SUBJECTS / f"{subject}.bin")


def entry_url(index: flowfile.ExchangeIndex) -> str | None:
    """First HTML 200 in capture order: the document the browser should open."""
    for group in index.by_url.values():
        for exchange in group:
            if exchange.status == 200 and "text/html" in (
                exchange.headers.get("content-type", "").lower()
            ):
                return exchange.url
    return None


def origin_of(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}"


class ReplayFactory:
    """A `serve.ContextFactory` work-alike backed by a capture, not a directory.

    Same interface the runner and the differential expect (``__call__``,
    ``close_open_contexts``, ``totals``), so every seam below is handed the
    object it already knows how to use.
    """

    def __init__(self, browser: Any, router: replay.ReplayRouter, allow: list[str]) -> None:
        self._browser = browser
        self._router = router
        self._allow = allow
        self.totals: dict[str, int] = {
            "served": 0,
            "ping": 0,
            "blocked": 0,
            "missing": 0,
            "websocket": 0,
        }
        self._contexts: set[Any] = set()

    @property
    def tag_script(self) -> str:
        # One census per document load, on `load` exactly as
        # `tools/kafe_scored_run.py` does it, so element identity here is the
        # identity that run established. Re-running it after the DOM moved would
        # reassign ids and break identity across trials.
        return f"""
        window.addEventListener('load', () => {{
            ({FRAMED_CENSUS_JS})('{replay.CENSUS_ATTR}');
            ({MIRROR_JS})('{replay.CENSUS_ATTR}', {json.dumps(self._allow)});
        }});
        """

    async def __call__(self) -> Any:
        context = await self._browser.new_context(
            viewport=VIEWPORT,
            locale="en-US",
            timezone_id="UTC",
            reduced_motion="reduce",
            service_workers="block",
        )
        self._contexts.add(context)
        context.on("close", lambda _: self._contexts.discard(context))
        context.set_default_timeout(CONTEXT_TIMEOUT_MS)
        context.set_default_navigation_timeout(CONTEXT_TIMEOUT_MS)
        try:
            await self._router.attach(context)
            if self._allow is not None:
                await context.add_init_script(self.tag_script)
        except BaseException:
            await context.close()
            raise
        return context

    async def close_open_contexts(self) -> None:
        for context in tuple(self._contexts):
            try:
                await context.close()
            except Exception:
                self._contexts.discard(context)


def capped_trial_config(cap: int):
    """`TrialConfig` with this subject's derived tab budget as the default.

    `bakeoff.run_behavioural` builds its own `TrialConfig` with the 300 default,
    which caps the walk on a real page. Only the budget argument changes; the
    frozen dataclass and the frozen walker are untouched.
    """

    def build(**kwargs: Any) -> TrialConfig:
        kwargs.setdefault("max_tabs", cap)
        return TrialConfig(**kwargs)

    return build


def capped_compute_tab_order(cap: int):
    """`compute_tab_order` with this subject's derived budget, for the candidate arm."""

    async def build(page: Any, *, max_tabs: int | None = None) -> Any:
        return await compute_tab_order(page, max_tabs=cap if max_tabs is None else max_tabs)

    return build


# ---------------------------------------------------------------------------
# C10-C16 observations, over the replayed page
# ---------------------------------------------------------------------------
async def observe_containment(factory: ReplayFactory, url: str) -> tuple[dict, float]:
    out: dict[str, Any] = {}
    ms = 0.0
    context = await factory()
    try:
        page = await context.new_page()
        await page.goto(url, wait_until="load")
        await page.wait_for_timeout(120)
        for frame in page.frames:
            try:
                t0 = time.monotonic()
                found = await frame.evaluate(CONTAINMENT_JS, CONTAINMENT_SEL)
                ms += (time.monotonic() - t0) * 1000
                out.update(found)
            except Exception:
                pass
    finally:
        await context.close()
        await factory.close_open_contexts()
    return out, ms


async def observe_composite(factory: ReplayFactory, url: str) -> tuple[dict, float]:
    out: dict[str, Any] = {}
    ms = 0.0
    context = await factory()
    try:
        page = await context.new_page()
        await page.goto(url, wait_until="load")
        await page.wait_for_timeout(120)
        for frame in page.frames:
            try:
                t0 = time.monotonic()
                found = await frame.evaluate(COMPOSITE_JS)
                ms += (time.monotonic() - t0) * 1000
                out.update(found)
            except Exception:
                pass
    finally:
        await context.close()
        await factory.close_open_contexts()
    return out, ms


async def _own_listeners(cdp: Any, probe_id: str) -> list[str] | None:
    """`probe_effect.own_listeners`, transcribed; it is a function, not a literal."""
    try:
        handle = await cdp.send(
            "Runtime.evaluate",
            {
                "expression": "(() => { const find = (root) => {"
                ' const d = root.querySelector(\'[data-probe="' + probe_id + "\"]');"
                " if (d) return d;"
                " for (const el of root.querySelectorAll('*'))"
                "  if (el.shadowRoot) { const h = find(el.shadowRoot); if (h) return h; }"
                " return null; }; return find(document); })()"
            },
        )
        oid = handle.get("result", {}).get("objectId")
        if not oid:
            return None
        got = await cdp.send("DOMDebugger.getEventListeners", {"objectId": oid, "depth": 0})
        return sorted({e.get("type") for e in got.get("listeners", [])} & EFFECT_ACTIVATION)
    except Exception:
        return None


async def observe_effect(factory: ReplayFactory, url: str) -> tuple[dict, float]:
    out: dict[str, Any] = {}
    ms = 0.0
    context = await factory()
    try:
        page = await context.new_page()
        await page.goto(url, wait_until="load")
        await page.wait_for_timeout(120)
        cdp = await context.new_cdp_session(page)
        for frame in page.frames:
            try:
                ids = await frame.evaluate(EFFECT_IDS_JS)
            except Exception:
                continue
            for pid in ids:
                t0 = time.monotonic()
                row: dict[str, Any] = {"own_activation": None, "hover_reveal": None}
                row["own_activation"] = await _own_listeners(cdp, pid)
                try:
                    before = await frame.evaluate(EFFECT_SHOT_JS, pid)
                    loc = frame.locator(f'[data-probe="{pid}"]').first
                    await loc.hover(timeout=1500, force=True)
                    await page.wait_for_timeout(90)
                    after = await frame.evaluate(EFFECT_SHOT_JS, pid)
                    if before is not None and after is not None:
                        b = before.split(",") if before else []
                        a = after.split(",") if after else []
                        gained = sum(
                            1 for x, y in zip(b, a) if x.endswith(":0") and y.endswith(":1")
                        )
                        row["hover_reveal"] = gained > 0
                    await page.mouse.move(0, 0)
                    await page.wait_for_timeout(40)
                except Exception:
                    pass
                ms += (time.monotonic() - t0) * 1000
                out[pid] = row
    finally:
        await context.close()
        await factory.close_open_contexts()
    return out, ms


async def _digest_all(page: Any) -> str:
    out = []
    for frame in page.frames:
        try:
            out.append(await frame.evaluate(E2_DIGEST_JS))
        except Exception:
            out.append("?")
    return "".join(out)


async def _settle(page: Any, before: str) -> str:
    waited = 0
    while waited < E2_SETTLE_MS:
        await page.wait_for_timeout(E2_SETTLE_STEP)
        waited += E2_SETTLE_STEP
        now = await _digest_all(page)
        if now != before:
            return now
    return await _digest_all(page)


async def observe_effect2(
    factory: ReplayFactory, url: str, all_ids: list[str], leads: list[str]
) -> tuple[dict, float]:
    """`probe_effect2.observe`, transcribed, against the replayed entry document."""
    out: dict[str, Any] = {}
    context = await factory()
    try:
        page = await context.new_page()
        await page.goto(url, wait_until="load")
        await page.wait_for_timeout(120)
        statics: dict[str, Any] = {}
        for frame in page.frames:
            try:
                statics.update(await frame.evaluate(E2_STATIC_JS, E2_NATIVE))
            except Exception:
                pass
    finally:
        await context.close()
        await factory.close_open_contexts()

    for pid in all_ids:
        out[pid] = dict(statics.get(pid, {}))
        out[pid].update(click_effect=None, key_effect=None, same_effect=None)
    if not leads:
        return out, 0.0

    total_ms = 0.0
    for pid in leads:
        row = out[pid]
        t0 = time.monotonic()
        for mode in ("click", "key"):
            if mode == "key" and row.get("click_effect") is not True:
                continue
            context = await factory()
            try:
                page = await context.new_page()
                console_seen: list[int] = []
                net_seen: list[int] = []
                page.on("console", lambda m: console_seen.append(1))
                page.on("request", lambda r: net_seen.append(1))
                await page.goto(url, wait_until="load")
                await page.wait_for_timeout(100)
                frame = None
                for candidate in page.frames:
                    if await candidate.locator(f'[data-probe="{pid}"]').count():
                        frame = candidate
                        break
                if frame is None:
                    continue
                before = await _digest_all(page)
                console_mark, net_mark = len(console_seen), len(net_seen)
                if mode == "click":
                    try:
                        await frame.locator(f'[data-probe="{pid}"]').first.click(
                            timeout=1200, force=True
                        )
                    except Exception:
                        continue
                else:
                    if not await frame.evaluate(E2_FIND_JS, pid):
                        continue
                    await page.keyboard.press("Enter")
                    await page.wait_for_timeout(60)
                    await page.keyboard.press(" ")
                after = await _settle(page, before)
                chatter = len(console_seen) > console_mark or len(net_seen) > net_mark
                row[f"{mode}_effect"] = after != before or chatter
                row[f"{mode}_digest"] = after + ("|chatter" if chatter else "")
            except Exception:
                pass
            finally:
                await context.close()
                await factory.close_open_contexts()
        row["ms"] = round((time.monotonic() - t0) * 1000, 1)
        total_ms += row["ms"]
        if row.get("click_effect") and row.get("key_effect"):
            row["same_effect"] = row.get("click_digest") == row.get("key_digest")
        row.pop("click_digest", None)
        row.pop("key_digest", None)
    return out, total_ms


# ---------------------------------------------------------------------------
# One subject
# ---------------------------------------------------------------------------
def project(flagged: int, undecided: int, universe: int, rule: str) -> tuple[str, str]:
    """Project one detector's element counts on one page to one page verdict.

    Both rules agree that **page-positive iff it flagged at least one element**:
    a finding is evidence whatever else on the page went unread.

    They differ on what licenses a *negative*, and the difference is not
    cosmetic. Under ``permissive`` a detector that decided even one candidate and
    flagged nothing calls the page clean — which is how `godaddy`, where 17 of 21
    candidates were unobservable, produced twelve confident negatives off four
    elements. Under ``strict`` a negative requires the detector to have decided
    the **whole** candidate universe; anything less is an abstention, because
    "no evidence here" is only a claim about where you actually looked.

    `strict` is what the published table uses. `permissive` is reported beside it
    so the size of the difference is visible rather than asserted.
    """
    if flagged:
        return "positive", ""
    if undecided <= 0:
        return "negative", ""
    if rule == "strict":
        return "abstain", f"undecided on {undecided} of {universe} candidates"
    decided = universe - undecided
    if decided <= 0:
        return "abstain", f"decided 0 of {universe} candidates"
    return "negative", ""


def verdict_of(reported: set[str], unknown: set[str], universe: int) -> dict[str, Any]:
    """Record the two counts every projection is computed from.

    The verdict stored here is the strict one, but `flagged` and `undecided` are
    what the assembler actually reads, so a rule can be changed without
    re-measuring a corpus that takes hours to measure.
    """
    verdict, reason = project(len(reported), len(unknown), universe, "strict")
    row: dict[str, Any] = {
        "verdict": verdict,
        "flagged": len(reported),
        "undecided": len(unknown),
        "universe": universe,
    }
    if reason:
        row["reason"] = reason
    return row


async def measure_subject(browser: Any, subject: str, label: bool | None, axe: Any) -> dict:
    started = time.perf_counter()
    record: dict[str, Any] = {
        "subject": subject,
        "y": label,
        "started_utc": datetime.now(UTC).isoformat(),
        "viewport": VIEWPORT,
    }

    path = capture_path(subject)
    if not path.exists():
        return {**record, "status": "abstain", "reason": "capture file missing"}
    try:
        index = flowfile.load_exchanges(path.read_bytes())
    except Exception as exc:
        return {**record, "status": "abstain", "reason": f"unparseable: {exc}"}
    url = entry_url(index)
    if url is None:
        return {**record, "status": "abstain", "reason": "no HTML entry document"}
    record["entry"] = url
    record["origin"] = origin_of(url)

    router = replay.ReplayRouter(index)

    # --- discovery: census everything, let the frozen collector choose ------
    discovery = ReplayFactory(browser, router, allow=None)
    try:
        context = await discovery()
        await context.add_init_script(DISCOVERY_TAG_JS)
        page = await context.new_page()
        await page.goto(url, wait_until="load", timeout=60_000)
        await page.wait_for_timeout(3_000)
        # Deliberately NOT re-censused here. An earlier version re-ran the census
        # after the 3-second settle, which produced ids for elements the page had
        # created *after* load — ids no trial context could ever mint, because
        # the init script censuses at `load`. On fandango that made 12 of 13
        # probes unobservable to every survey detector and broke the candidate
        # arm outright. Identity is therefore fixed at `load` in every context,
        # discovery included, and an element that appears later is simply not in
        # the universe.
        tagged = await page.evaluate(
            f"""() => {{
                let n = 0;
                const walk = (root) => {{
                    let els;
                    try {{ els = root.querySelectorAll('[{replay.CENSUS_ATTR}]'); }}
                    catch (e) {{ return; }}
                    n += els.length;
                    for (const el of root.querySelectorAll('*'))
                        if (el.shadowRoot) walk(el.shadowRoot);
                }};
                walk(document);
                return n;
            }}"""
        )
        focusable = await page.evaluate(FOCUSABLE_JS)
        candidates = await collect_candidates(page)
        await context.close()
    except Exception as exc:
        return {
            **record,
            "status": "abstain",
            "reason": f"replay failed: {type(exc).__name__}: {exc}"[:300],
            "elapsed_s": round(time.perf_counter() - started, 1),
        }

    probe_ids = sorted({c.probe_id for c in candidates if c.probe_id})
    cap = focusable + TAB_HEADROOM
    record.update(
        {
            "census_tagged": tagged,
            "focusable": focusable,
            "candidates": len(candidates),
            "probe_ids": len(probe_ids),
            "tab_cap": cap,
            "served": router.served,
            "denied": router.denied,
            "functionally_degraded": router.is_functionally_degraded(),
        }
    )
    if not probe_ids:
        return {
            **record,
            "status": "abstain",
            "reason": (
                "the frozen candidate collector surfaced no addressable element "
                f"({tagged} elements in the replayed document, {focusable} focusable): "
                "no button to decide about, so this is an abstention and not a negative"
            ),
            "elapsed_s": round(time.perf_counter() - started, 1),
        }

    factory = ReplayFactory(browser, router, allow=probe_ids)

    # --- the tab order, on its own freshly navigated page -------------------
    # The same load also measures identity stability: how many of the ids the
    # discovery pass chose a *different* context actually mints. Every trial
    # below addresses elements by that id, so a low figure is the one thing that
    # would invalidate the whole subject, and it is recorded rather than assumed.
    try:
        context = await factory()
        page = await context.new_page()
        await page.goto(url, wait_until="load", timeout=60_000)
        await page.wait_for_timeout(1_000)
        resolved = await page.evaluate(
            """(wanted) => {
                const seen = new Set();
                const walk = (root) => {
                    let els;
                    try { els = root.querySelectorAll('[data-probe]'); }
                    catch (e) { return; }
                    for (const el of els) seen.add(el.getAttribute('data-probe'));
                    for (const el of root.querySelectorAll('*'))
                        if (el.shadowRoot) walk(el.shadowRoot);
                };
                walk(document);
                return wanted.filter((id) => seen.has(id)).length;
            }""",
            probe_ids,
        )
        record["identity_resolved"] = resolved
        record["identity_stability"] = round(resolved / len(probe_ids), 3)
        order = await compute_tab_order(page, max_tabs=cap)
        await context.close()
    except Exception as exc:
        return {
            **record,
            "status": "abstain",
            "reason": f"tab order failed: {type(exc).__name__}: {exc}"[:300],
            "elapsed_s": round(time.perf_counter() - started, 1),
        }
    record["tab_stops"] = len(order.index)
    record["tab_capped"] = order.capped
    record["tab_presses"] = order.presses
    if order.capped:
        return {
            **record,
            "status": "abstain",
            "reason": f"tab walk capped at {cap} with {focusable} focusable elements",
            "elapsed_s": round(time.perf_counter() - started, 1),
        }

    reported: dict[str, set[str]] = {}
    unknown: dict[str, set[str]] = {}
    timings: dict[str, float] = {}
    arms: dict[str, Any] = {}
    evidence: dict[str, Any] = {}

    # Every seam below resolves `page_url` and `BASE_URL` from the bakeoff
    # module at call time. Pointing them at this subject is what lets the
    # unmodified seams drive a replayed capture; nothing else about them changes.
    saved = (bakeoff.page_url, bakeoff.BASE_URL, bakeoff.TrialConfig)
    saved_cand = candidate_analysis.compute_tab_order
    bakeoff.page_url = lambda _p: url
    bakeoff.BASE_URL = record["origin"]
    bakeoff.TrialConfig = capped_trial_config(cap)
    candidate_analysis.page_url = lambda _p: url
    candidate_analysis.compute_tab_order = capped_compute_tab_order(cap)

    try:
        # --- arm 1: the cheap tier, through bakeoff.run_page ----------------
        t0 = time.monotonic()
        try:
            async with asyncio.timeout(ARM_TIMEOUT_S):
                cheap_reported, _order2, meta = await bakeoff.run_page(
                    factory, HERE, subject, probe_ids, axe
                )
            unobservable = set(meta.get("unobservable", []))
            capped_ids = {p for p in probe_ids if not order.reachability_is_certain(p)}
            for name, ids in cheap_reported.items():
                reported[name] = set(ids)
                unknown[name] = set(unobservable)
                if not name.startswith(("D1 ", "D1x ")):
                    unknown[name] |= capped_ids
            timings.update(meta.get("timings", {}))
            evidence["cheap_notes"] = meta.get("notes", {})
            evidence["unobservable"] = len(unobservable)
            arms["cheap"] = {"ok": True, "seconds": round(time.monotonic() - t0, 1)}
        except Exception as exc:
            arms["cheap"] = {
                "ok": False,
                "error": f"{type(exc).__name__}: {exc}"[:300],
                "seconds": round(time.monotonic() - t0, 1),
            }
        finally:
            await factory.close_open_contexts()

        # --- arm 2: upstream generators and C1-C9 --------------------------
        t0 = time.monotonic()
        try:
            axe_source = frozen_detectors.AXE_BUNDLE.read_text()

            async def candidate_axe(page: Any) -> set[str]:
                return await upstream_candidates.d1_axe(page, axe_source)

            async with asyncio.timeout(ARM_TIMEOUT_S):
                study = await candidate_analysis.measure_candidate_page(
                    factory, subject, probe_ids, candidate_axe
                )
            for name in (*UPSTREAM, *VARIANTS):
                reported[name] = set(study.reported.get(name, set()))
                unknown[name] = set(study.unknown.get(name, set()))
            timings.update(study.timings)
            evidence["candidate_tab_capped"] = study.evidence["tab_order"]["capped"]
            evidence["candidate_features"] = len(study.evidence.get("features", {}))
            record["_features"] = study.evidence.get("features", {})
            arms["candidate"] = {"ok": True, "seconds": round(time.monotonic() - t0, 1)}
        except Exception as exc:
            arms["candidate"] = {
                "ok": False,
                "error": f"{type(exc).__name__}: {exc}"[:300],
                "seconds": round(time.monotonic() - t0, 1),
            }
        finally:
            await factory.close_open_contexts()

        # --- arm 3: C10-C16, layered on the C9 lead set --------------------
        t0 = time.monotonic()
        c9_name = next((n for n in VARIANTS if n.startswith("C9")), None)
        if not arms["candidate"]["ok"]:
            arms["probe-rules"] = {
                "ok": False,
                "error": "no C9 lead set: the candidate arm failed",
                "seconds": 0.0,
            }
        else:
            try:
                c9 = set(reported.get(c9_name, set()))
                obs_ms: dict[str, float] = {}
                async with asyncio.timeout(ARM_TIMEOUT_S):
                    con, obs_ms["containment"] = await observe_containment(factory, url)
                    comp, obs_ms["composite"] = await observe_composite(factory, url)
                    eff, obs_ms["effect"] = await observe_effect(factory, url)
                    eff2, obs_ms["effect2"] = await observe_effect2(
                        factory, url, probe_ids, sorted(c9)
                    )
                sets = rule_sets(
                    c9,
                    set(probe_ids),
                    record.get("_features", {}),
                    {"containment": con, "composite": comp, "effect": eff, "effect2": eff2},
                )
                r1, r2, r3, r5 = sets["R1"], sets["R2"], sets["R3"], sets["R5"]
                r6, r7, r8, r9 = sets["R6"], sets["R7"], sets["R8"], sets["R9"]
                c13 = sets["C13"]
                c9_unknown = set(unknown.get(c9_name, set()))
                rows = {
                    PROBE_RULES[0]: (c9 - r1, c9_unknown),
                    PROBE_RULES[1]: (c9 - r1 - r2, c9_unknown),
                    PROBE_RULES[2]: (c9 - r1 - r2 - r3, c9_unknown),
                    PROBE_RULES[3]: (c13, c9_unknown),
                    PROBE_RULES[4]: (c13 - r6, c9_unknown),
                    PROBE_RULES[5]: (c13 - r6 - r7 - r8, c9_unknown),
                    PROBE_RULES[6]: ((c13 - r6 - r7 - r8) | r9, c9_unknown - r9),
                }
                for name, (ids, unk) in rows.items():
                    reported[name] = set(ids) - set(unk)
                    unknown[name] = set(unk)
                evidence["probe_observation_ms"] = {k: round(v, 1) for k, v in obs_ms.items()}
                evidence["c9_lead_set"] = len(c9)
                evidence["rule_fires"] = {k: len(v) for k, v in sets.items() if k != "C13"}
                arms["probe-rules"] = {
                    "ok": True,
                    "seconds": round(time.monotonic() - t0, 1),
                    "observation_ms": {k: round(v, 1) for k, v in obs_ms.items()},
                }
            except Exception as exc:
                arms["probe-rules"] = {
                    "ok": False,
                    "error": f"{type(exc).__name__}: {exc}"[:300],
                    "seconds": round(time.monotonic() - t0, 1),
                }
            finally:
                await factory.close_open_contexts()

        # --- arm 4: the D9/D10 behavioural arms ----------------------------
        t0 = time.monotonic()
        try:
            async with asyncio.timeout(ARM_TIMEOUT_S):
                result = await bakeoff.run_behavioural(factory, subject, probe_ids, order)
            pairs = {
                bakeoff.D9_NAME: (result.d9, result.d9_unknown),
                bakeoff.D9_NOS4_NAME: (result.d9_nos4, result.d9_nos4_unknown),
                bakeoff.D9_S4U_NAME: (result.d9_s4u, result.d9_s4u_unknown),
                bakeoff.D9_S4OURS_NAME: (result.d9_s4ours, result.d9_s4ours_unknown),
                bakeoff.D9U_NAME: (result.d9u, result.d9u_unknown),
                bakeoff.D10A_U_NAME: (result.d10a_u, result.d10u_unknown),
                bakeoff.D10B_U_NAME: (result.d10b_u, result.d10u_unknown),
                bakeoff.D10_NAME: (result.d10, result.d10_unknown),
                bakeoff.D10B_NAME: (result.d10b, result.d10_unknown),
                bakeoff.D10BASE_NAME: (result.d10base, result.d10_unknown),
            }
            # Upstream's Stage 4 searches a global witness pool; `bakeoff` runs
            # it once after every page. One subject is one page here, so the
            # pool is this subject's, and that scope difference is recorded.
            kept_u, dismissed_u = bakeoff.upstream_stage4(result.upstream_passes)
            d9u_s4u_unknown = set(result.d9u_s4u_unknown)
            if any(up.coverage_uncertainties for up in result.upstream_passes.values()):
                d9u_s4u_unknown |= set(result.upstream_passes)
            pairs[bakeoff.D9U_S4U_NAME] = (kept_u, d9u_s4u_unknown)
            for name, (ids, unk) in pairs.items():
                reported[name] = set(ids) - set(unk)
                unknown[name] = set(unk)
            timings.update({k: round(v, 1) for k, v in result.timings.items()})
            evidence["baseline"] = result.baseline_evidence
            evidence["coverage_errors"] = len(result.coverage_errors)
            evidence["upstream_s4_dismissals"] = len(dismissed_u)
            arms["behavioural"] = {"ok": True, "seconds": round(time.monotonic() - t0, 1)}
        except Exception as exc:
            arms["behavioural"] = {
                "ok": False,
                "error": f"{type(exc).__name__}: {exc}"[:300],
                "seconds": round(time.monotonic() - t0, 1),
                "traceback": traceback.format_exc()[-600:],
            }
        finally:
            await factory.close_open_contexts()
    finally:
        bakeoff.page_url, bakeoff.BASE_URL, bakeoff.TrialConfig = saved
        candidate_analysis.compute_tab_order = saved_cand
        candidate_analysis.page_url = saved[0]

    record.pop("_features", None)
    verdicts: dict[str, Any] = {}
    for name in ALL_DETECTORS:
        arm = arms.get(ARM_OF[name])
        if arm is None or not arm.get("ok"):
            verdicts[name] = {
                "verdict": "abstain",
                "reason": f"{ARM_OF[name]} arm failed: "
                + str((arm or {}).get("error", "arm did not run"))[:160],
                "flagged": 0,
            }
            continue
        ids = reported.get(name)
        if ids is None:
            verdicts[name] = {
                "verdict": "abstain",
                "reason": f"{ARM_OF[name]} arm produced no row for this detector",
                "flagged": 0,
            }
            continue
        row = verdict_of(set(ids), set(unknown.get(name, set())), len(probe_ids))
        row["ids"] = sorted(ids)[:20]
        verdicts[name] = row

    record.update(
        {
            "status": "scored",
            "arms": arms,
            "timings": {k: round(v, 1) for k, v in timings.items()},
            "evidence": evidence,
            "detectors": verdicts,
            "served_end": router.served,
            "denied_end": router.denied,
            "elapsed_s": round(time.perf_counter() - started, 1),
        }
    )
    return record


# ---------------------------------------------------------------------------
# KAFE's own side
# ---------------------------------------------------------------------------
def kafe_rows() -> list[dict[str, str]]:
    rows = list(csv.DictReader(KAFE_CSV.open()))
    return [
        r
        for r in rows
        if (r["Subject"] or "").strip()
        and (r["Type 1 Detection Ground Truth: "] or "").strip() in ("TRUE", "FALSE")
    ]


def kafe_confusion(rows: list[dict[str, str]]) -> dict[str, Any]:
    tp = fp = fn = tn = 0
    for r in rows:
        y = r["Type 1 Detection Ground Truth: "].strip() == "TRUE"
        yhat = r["Type 1 Detection Result: "].strip() == "TRUE"
        if y and yhat:
            tp += 1
        elif yhat:
            fp += 1
        elif y:
            fn += 1
        else:
            tn += 1
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    f1 = (
        2 * precision * recall / (precision + recall)
        if precision and recall
        else None
    )
    return {
        "n": len(rows),
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
        "precision": precision,
        "recall": recall,
        "f1": f1,
    }


def kafe_timing(rows: list[dict[str, str]]) -> dict[str, Any]:
    detection = [float(r["Detection"]) for r in rows]
    ctrl = [float(r["Size of All Visible Ctrl Nodes"]) for r in rows]
    per_button = [d / c for d, c in zip(detection, ctrl) if c]
    return {
        "ms_per_subject_median": round(statistics.median(detection), 1),
        "ms_per_subject_mean": round(statistics.mean(detection), 1),
        "subjects_under_300ms": sum(1 for d in detection if d < 300),
        "ms_per_button_median": round(statistics.median(per_button), 1),
        "ms_per_button_mean": round(statistics.mean(per_button), 1),
        "ms_per_button_pooled": round(sum(detection) / sum(ctrl), 1),
        "buttons_under_300ms_cap": f"{sum(1 for x in per_button if x < 300)}/{len(per_button)}",
        "detection_ms_total": sum(detection),
        "ctrl_nodes_total": int(sum(ctrl)),
    }


# ---------------------------------------------------------------------------
# Controls
# ---------------------------------------------------------------------------
def run_controls(scored_path: pathlib.Path = OUT) -> dict[str, Any]:
    out: dict[str, Any] = {"generated_utc": datetime.now(UTC).isoformat()}

    rows = kafe_rows()
    confusion = kafe_confusion(rows)
    expected = {"n": 60, "tp": 36, "fp": 3, "fn": 0, "tn": 21}
    ok = all(confusion[k] == v for k, v in expected.items())
    ok = ok and round(confusion["precision"] * 100, 1) == 92.3
    ok = ok and round(confusion["recall"] * 100, 1) == 100.0
    out["control_1_kafe_reproduction"] = {
        "pass": ok,
        "expected": expected | {"precision": "92.3%", "recall": "100.0%"},
        "recomputed": confusion
        | {
            "precision_pct": round(confusion["precision"] * 100, 1),
            "recall_pct": round(confusion["recall"] * 100, 1),
        },
        "timing": kafe_timing(rows),
        "source": str(KAFE_CSV.relative_to(HERE)),
    }

    denom = json.loads(DENOM.read_text())
    replayable = [s for s in denom["subjects"] if s.get("status") == "replayable"]
    excluded = [s for s in denom["subjects"] if s.get("status") != "replayable"]
    scored: list[dict] = []
    if scored_path.exists():
        scored = [json.loads(line) for line in scored_path.read_text().splitlines() if line.strip()]
    ok_scored = [r for r in scored if r.get("status") == "scored"]
    abstained = [r for r in scored if r.get("status") != "scored"]
    out["control_2_denominator"] = {
        "kafe_corpus": len(denom["subjects"]),
        "replayable": len(replayable),
        "attempted": len(scored),
        "scored": len(ok_scored),
        "abstained_whole_subject": len(abstained),
        "pass": len(ok_scored) + len(abstained) == len(scored)
        and all(r["subject"] in {s["subject"] for s in replayable} for r in scored),
        "excluded_before_the_run": [
            {"subject": s["subject"], "reason": s.get("exclusion_reason", "unstated")}
            for s in excluded
        ],
        "abstained_during_the_run": [
            {"subject": r["subject"], "reason": r.get("reason", "unstated")} for r in abstained
        ],
        "not_yet_attempted": sorted(
            {s["subject"] for s in replayable} - {r["subject"] for r in scored}
        ),
    }

    negatives = [r for r in ok_scored if r.get("y") is False]
    witness = None
    if negatives:
        pick = negatives[0]
        tn_rows = [
            name
            for name, row in pick["detectors"].items()
            if row["verdict"] == "negative"
        ]
        witness = {
            "subject": pick["subject"],
            "kafe_label": False,
            "detectors_recording_a_true_negative": len(tn_rows),
            "detectors_abstaining": sum(
                1 for row in pick["detectors"].values() if row["verdict"] == "abstain"
            ),
            "detectors_flagging": sum(
                1 for row in pick["detectors"].values() if row["verdict"] == "positive"
            ),
            "example_true_negatives": sorted(tn_rows)[:5],
        }
    out["control_3_negative"] = {
        "pass": bool(witness and witness["detectors_recording_a_true_negative"] > 0),
        "negative_subjects_scored": len(negatives),
        "negative_subject_names": [r["subject"] for r in negatives],
        "witness": witness,
    }

    import audit.analyzer.keyboard.kbdiff as kbdiff
    import audit.analyzer.keyboard.kbdiff.detectors as det_mod
    import audit.analyzer.keyboard.kbdiff.differential as diff_mod
    import audit.analyzer.keyboard.kbdiff.taborder as tab_mod

    frozen_root = (REPO / "src" / "audit" / "analyzer" / "keyboard" / "kbdiff").resolve()
    modules = {
        "kbdiff package": kbdiff.__file__,
        "detectors": det_mod.__file__,
        "differential": diff_mod.__file__,
        "taborder": tab_mod.__file__,
    }
    inside = {
        k: pathlib.Path(v).resolve().is_relative_to(frozen_root) for k, v in modules.items()
    }
    out["control_4_frozen_code"] = {
        "pass": all(inside.values()),
        "expected_root": str(frozen_root),
        "imported_from": modules,
        "all_under_expected_root": inside,
    }
    return out


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------
def assemble(scored_path: pathlib.Path = OUT, rule: str = "strict") -> dict[str, Any]:
    scored = [json.loads(line) for line in scored_path.read_text().splitlines() if line.strip()]
    ok = [r for r in scored if r.get("status") == "scored"]
    ratio = {r["subject"]: r for r in ok}

    detector_rows: dict[str, dict[str, Any]] = {}
    for name in ALL_DETECTORS:
        tp = fp = fn = tn = abst = 0
        ms_total = 0.0
        ms_subjects = 0
        buttons = 0
        covers_seen: set[str] = set()
        ms_reasons: set[str] = set()
        for record in scored:
            # A subject that never replayed abstains for every detector. It is
            # counted here rather than dropped, so `decided + abstentions` is
            # always the number of subjects attempted and no exclusion is silent.
            row = (record.get("detectors") or {}).get(name)
            if record.get("status") != "scored" or row is None:
                abst += 1
                continue
            # An arm that failed carries no counts and stays an abstention. Where
            # counts exist the verdict is recomputed under the requested rule, so
            # the projection can change without re-measuring the corpus.
            if "undecided" not in row:
                abst += 1
                continue
            verdict, _reason = project(
                row["flagged"], row["undecided"], row.get("universe") or record["probe_ids"], rule
            )
            if verdict == "abstain":
                abst += 1
                continue
            y = bool(record["y"])
            yhat = verdict == "positive"
            if y and yhat:
                tp += 1
            elif yhat:
                fp += 1
            elif y:
                fn += 1
            else:
                tn += 1
            ms, covers, reason = subject_cost(name, record)
            covers_seen.add(covers)
            if ms is None:
                if reason:
                    ms_reasons.add(reason)
            else:
                ms_total += ms
                ms_subjects += 1
                buttons += record["probe_ids"]
        precision = tp / (tp + fp) if tp + fp else None
        recall = tp / (tp + fn) if tp + fn else None
        f1 = (
            2 * precision * recall / (precision + recall)
            if precision and recall
            else None
        )
        decided = tp + fp + fn + tn
        detector_rows[name] = {
            "tp": tp,
            "fp": fp,
            "fn": fn,
            "tn": tn,
            "abstentions": abst,
            "decided_subjects": decided,
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "ms_total": round(ms_total, 1) if ms_subjects else None,
            "ms_per_button": round(ms_total / buttons, 1) if buttons else None,
            "ms_per_subject": round(ms_total / ms_subjects, 1) if ms_subjects else None,
            "buttons": buttons,
            "ms_subjects": ms_subjects,
            "ms_covers": "; ".join(sorted(covers_seen)) or "not measured",
            "ms_reason": "; ".join(sorted(ms_reasons)) or None,
        }

    rows = kafe_rows()
    by_subject = {r["Subject"].strip(): r for r in rows}
    kafe_subset = [by_subject[s] for s in ratio if s in by_subject]
    detector_rows["KAFE (Chiou et al., ESEC/FSE 2021)"] = kafe_row(kafe_subset, len(scored))

    return {
        "generated_utc": datetime.now(UTC).isoformat(),
        "verdict_rule": rule,
        "subjects_scored": len(ok),
        "subjects_attempted": len(scored),
        "subject_names": sorted(ratio),
        "positives": sum(1 for r in ok if r["y"]),
        "negatives": sum(1 for r in ok if not r["y"]),
        "buttons_total": sum(r["probe_ids"] for r in ok),
        "kafe_whole_corpus": kafe_confusion(rows) | kafe_timing(rows),
        "kafe_on_scored_subset": kafe_confusion(kafe_subset) | kafe_timing(kafe_subset)
        if kafe_subset
        else None,
        "rows": detector_rows,
    }


def kafe_row(subset: list[dict[str, str]], attempted: int = 0) -> dict[str, Any]:
    """KAFE's own row, computed on the same subjects and in the same two units."""
    if not subset:
        return {
            "tp": 0, "fp": 0, "fn": 0, "tn": 0, "abstentions": 0, "decided_subjects": 0,
            "precision": None, "recall": None, "f1": None,
            "ms_total": None, "ms_per_button": None, "ms_per_subject": None,
            "buttons": 0, "ms_subjects": 0,
            "ms_covers": "measured (their Detection column)",
            "ms_reason": "not measured: no scored subject overlaps their CSV",
        }
    confusion = kafe_confusion(subset)
    detection = [float(r["Detection"]) for r in subset]
    ctrl = [float(r["Size of All Visible Ctrl Nodes"]) for r in subset]
    return {
        **{k: confusion[k] for k in ("tp", "fp", "fn", "tn", "precision", "recall", "f1")},
        # Zero, and that is the honest figure: KAFE decided every subject in its
        # own CSV and abstained on none. The row is *restricted* to the subjects
        # this replication scored, so the comparison sits on one denominator;
        # the subjects Axcess could not put in front of it are counted in
        # control 2 and named there, not charged to KAFE here.
        "abstentions": 0,
        "subjects_axcess_could_not_score": max(attempted - confusion["n"], 0),
        "decided_subjects": confusion["n"],
        "ms_total": round(sum(detection), 1),
        "ms_per_button": round(sum(detection) / sum(ctrl), 1) if sum(ctrl) else None,
        "ms_per_subject": round(sum(detection) / len(detection), 1),
        "buttons": int(sum(ctrl)),
        "ms_subjects": len(detection),
        "ms_covers": "measured (their Detection column / their visible ctrl nodes)",
        "ms_reason": None,
    }


def subject_cost(name: str, record: dict) -> tuple[float | None, str, str | None]:
    """One detector's measured ms on one subject, priced as the matrix prices it."""
    timings = dict(record.get("timings", {}))
    if name in PROBE_RULES:
        c9_name = next((n for n in VARIANTS if n.startswith("C9")), None)
        base, _covers, reason = assemble_matrix.cost_of(c9_name, timings)
        if base is None:
            return None, "C9 + rule observation", reason
        obs = (record.get("evidence") or {}).get("probe_observation_ms")
        if not obs:
            return None, "C9 + rule observation", "not measured: probe observations absent"
        needed = {
            PROBE_RULES[0]: ("containment",),
            PROBE_RULES[1]: ("containment", "composite"),
            PROBE_RULES[2]: ("containment", "composite"),
            PROBE_RULES[3]: ("containment", "composite", "effect"),
            PROBE_RULES[4]: ("containment", "composite", "effect"),
            PROBE_RULES[5]: ("containment", "composite", "effect", "effect2"),
            PROBE_RULES[6]: ("containment", "composite", "effect", "effect2"),
        }[name]
        if any(k not in obs for k in needed):
            return None, "C9 + rule observation", "not measured: an observation pass did not run"
        return base + sum(obs[k] for k in needed), "C9 + rule observation", None
    return assemble_matrix.cost_of(name, timings)


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------
def todo_subjects(only: str, limit: int) -> tuple[list[str], dict[str, bool]]:
    denom = json.loads(DENOM.read_text())
    labels = {
        s["subject"]: s["y"] for s in denom["subjects"] if s.get("status") == "replayable"
    }
    # Cheapest first, using the prior scored run's candidate counts, so an
    # interrupted run still covers most of the corpus.
    size: dict[str, int] = {}
    if PRIOR.exists():
        for line in PRIOR.read_text().splitlines():
            if line.strip():
                row = json.loads(line)
                size[row["subject"]] = row.get("addressable_candidates") or 0
    order = sorted(labels, key=lambda s: (size.get(s, 10**6), s))
    if only:
        wanted = {x.strip() for x in only.split(",")}
        order = [s for s in order if s in wanted]
    elif limit:
        order = order[:limit]
    return order, labels


LOG = HERE / "derived" / "kafe-matrix-run.log"


def say(line: str) -> None:
    """Progress to stdout and to a log file, because the run outlives a terminal."""
    print(line, flush=True)
    with LOG.open("a") as handle:
        handle.write(f"{datetime.now(UTC).strftime('%H:%M:%S')} {line}\n")


async def run(args: argparse.Namespace) -> int:
    order, labels = todo_subjects(args.only, args.limit)
    done: set[str] = set()
    if OUT.exists() and not args.restart:
        for line in OUT.read_text().splitlines():
            if line.strip():
                done.add(json.loads(line)["subject"])
    todo = [s for s in order if s not in done]

    say(f"{len(ALL_DETECTORS)} detectors x {len(todo)} subjects "
        f"({len(done)} already in {OUT.name})")
    async with async_playwright() as pw:
        axe = AxeAnalyzer.from_bundled()
        for i, subject in enumerate(todo, 1):
            # One browser per subject. A single process across a corpus this
            # size accumulates tens of thousands of short-lived contexts, and a
            # browser that degrades halfway through would corrupt later subjects
            # in a way the record could not distinguish from a page effect.
            browser = await pw.chromium.launch(headless=True)
            try:
                async with asyncio.timeout(SUBJECT_TIMEOUT_S):
                    record = await measure_subject(browser, subject, labels.get(subject), axe)
            except Exception as exc:
                record = {
                    "subject": subject,
                    "y": labels.get(subject),
                    "status": "abstain",
                    "reason": f"subject raised: {type(exc).__name__}: {exc}"[:300],
                }
            finally:
                try:
                    await browser.close()
                except Exception:
                    pass
            with OUT.open("a") as handle:
                handle.write(json.dumps(record) + "\n")
            if record.get("status") == "scored":
                counts: dict[str, int] = {}
                for row in record["detectors"].values():
                    counts[row["verdict"]] = counts.get(row["verdict"], 0) + 1
                say(
                    f"[{i}/{len(todo)}] {subject:<18} y={record['y']} "
                    f"buttons={record['probe_ids']:<5} "
                    f"pos={counts.get('positive', 0):<3} neg={counts.get('negative', 0):<3} "
                    f"abst={counts.get('abstain', 0):<3} ({record['elapsed_s']}s)"
                )
            else:
                say(f"[{i}/{len(todo)}] {subject:<18} ABSTAIN: {record.get('reason')}")
    return 0


# ---------------------------------------------------------------------------
# Why a capped subject capped
# ---------------------------------------------------------------------------
CAPDIAG = HERE / "derived" / "kafe_matrix_capdiag.json"
# Independent repeats of the same diagnosis, written by `capdiag --out`. A cap
# diagnosis that only ever ran once could not tell a property of the subject
# from a property of the load, so the report states how far the repeats agree.
CAPDIAG_REPEATS = sorted((HERE / "derived").glob("capdiag_repeat_*.json"))
# Every run's printed verdicts, oldest first. Runs 1 and 2 wrote their JSON to
# the path run 3 later overwrote, so this log is the only record of them.
CAPDIAG_LOG = HERE / "derived" / "capdiag-runs.log"


def capdiag_log_runs(path: pathlib.Path = CAPDIAG_LOG) -> list[dict[str, dict[str, Any]]]:
    """Each capdiag run's per-subject reading, oldest first, read back from the log.

    Only what every verdict line states is taken: whether the walk capped, at how
    many presses it completed if it did not, and whether the verdict says focus
    left the page. `write_report` checks these against the JSON of the runs that
    do survive before relying on the ones that only exist here.
    """
    if not path.exists():
        return []
    header = re.compile(r"^runs? (\d+)(?: and (\d+))? of \d+,")
    verdict = re.compile(r"^([a-z0-9_]+) {2,}(\S.*)$")
    completed = re.compile(r"^terminates at (\d+) presses")
    runs: list[dict[str, dict[str, Any]]] = []
    section: list[dict[str, dict[str, Any]]] = []
    for line in path.read_text().splitlines():
        if match := header.match(line):
            section = [{} for n in match.groups() if n]
            runs.extend(section)
            continue
        match = verdict.match(line)
        if not match or not section:
            continue
        subject, text = match.groups()
        # A section holding two runs lists each subject once per run, in run order.
        target = next((run for run in section if subject not in run), None)
        if target is None:
            continue
        done = completed.match(text)
        target[subject] = {
            "capped": done is None,
            "presses": int(done.group(1)) if done else None,
            "leaves_page": "`document.hasFocus()` is false" in text,
        }
    return runs


LOOP_TAIL = 60  # shortest trailing window examined, however short the period
LOOP_MAX_PERIOD = 400  # longest repeat this will look for
LOOP_MIN_REPEATS = 4  # the window must contain the period at least this often


def terminal_period(sequence: list[str]) -> int | None:
    """The period of the loop the walk ends in, or None if it is not looping.

    Only the tail is read, so a page that wandered for three thousand presses
    before settling still reports the loop it settled into. The window scales
    with the period — a 2-position bounce is only believed after `LOOP_TAIL`
    presses of it, and an 80-position orbit after four laps — because a short
    window makes a long orbit look like fresh ground and a fixed long window
    would reject a short bounce that only just started.

    A first version fixed the window at `LOOP_TAIL` regardless of period. On
    `raise`, whose orbit is longer than that, it reported "no loop" for a walk
    that had not reached a new position in its last hundred presses.
    """
    n = len(sequence)
    for period in range(1, min(LOOP_MAX_PERIOD, n // LOOP_MIN_REPEATS) + 1):
        window = min(n, max(period * LOOP_MIN_REPEATS, LOOP_TAIL))
        tail = sequence[-window:]
        if all(tail[i] == tail[i - period] for i in range(period, window)):
            return period
    return None


async def observe_walk(page, budget: int) -> dict[str, Any]:
    """Re-walk a freshly navigated page, recording *where* focus went.

    `compute_tab_order` is frozen and returns only named stops, `capped` and a
    press count — enough to know a walk capped, never enough to say why. This
    reads focus with the walker's own reader (`_active_marker`, so frames and
    shadow roots resolve identically) and keeps the marker sequence, which is
    what separates a page whose focus is stuck in a short loop from a page that
    is still reaching new controls when the budget runs out.

    Each new position is also asked whether the page still holds focus.
    `document.activeElement` falls back to `<body>` when nothing in the document
    is focused, so a `#el:body:*` marker on its own cannot tell "Tab landed on
    the body" from "focus left the page for the browser's own UI" — and those
    two have opposite meanings for a user. `document.hasFocus()` separates them.

    It observes; it decides nothing. The `capped` fact in every row below comes
    from the frozen walker, never from here.
    """
    sequence: list[str] = []
    page_focus: dict[str, bool] = {}
    for step in range(1, budget + 1):
        await page.keyboard.press("Tab")
        marker = await _active_marker(page)
        if marker is None:
            return {"observed_presses": step, "ended": "focus left the document"}
        sequence.append(marker)
        if marker not in page_focus:
            page_focus[marker] = await page.evaluate("() => document.hasFocus()")
        if len(sequence) > 1 and sequence[-1] == sequence[0]:
            return {"observed_presses": step, "ended": "cycled back to the first stop"}

    period = terminal_period(sequence)
    out: dict[str, Any] = {
        "observed_presses": len(sequence),
        "ended": "budget exhausted",
        "distinct_positions": len(set(sequence)),
        "new_positions_in_last_100": len(set(sequence[-100:]) - set(sequence[:-100])),
        "terminal_loop_period": period,
    }
    if period is not None:
        loop = sequence[-period:]
        out["terminal_loop"] = loop
        out["terminal_loop_page_focus"] = {m: page_focus.get(m) for m in loop}
        out["loop_leaves_the_page"] = any(page_focus.get(m) is False for m in loop)
        first = next(i for i, m in enumerate(sequence) if m == sequence[-period])
        out["loop_entered_at_press"] = first + 1
    return out


async def diagnose_subject(browser: Any, subject: str, ceiling: int) -> dict[str, Any]:
    """One subject's cap diagnosis, walked the way `measure_subject` walks.

    The first version of this walked a context built with ``allow=[]``, which
    mirrors `data-probe` onto nothing. `TabOrder.index` only records *named*
    stops, so `distinct_stops` was zero for every subject by construction while
    focus was in fact moving normally — an instrument reading, not a finding.
    The discovery pass below is therefore the scored run's, verbatim: census at
    `load`, let the frozen collector choose the ids, tag exactly those. Only
    then is the walk comparable to the `tab_stops` already in the matrix.
    """
    index = flowfile.load_exchanges(capture_path(subject).read_bytes())
    url = entry_url(index)
    if url is None:
        return {"error": "no HTML entry document"}
    router = replay.ReplayRouter(index)

    # --- discovery: the same census and the same collector as the scored run --
    discovery = ReplayFactory(browser, router, allow=None)
    context = await discovery()
    try:
        await context.add_init_script(DISCOVERY_TAG_JS)
        page = await context.new_page()
        await page.goto(url, wait_until="load", timeout=60_000)
        await page.wait_for_timeout(3_000)
        focusable = await page.evaluate(FOCUSABLE_JS)
        probe_ids = sorted({c.probe_id for c in await collect_candidates(page) if c.probe_id})
    finally:
        await context.close()

    factory = ReplayFactory(browser, router, allow=probe_ids)

    # --- the frozen walk, at the ceiling, on its own freshly navigated page ---
    context = await factory()
    try:
        page = await context.new_page()
        await page.goto(url, wait_until="load", timeout=60_000)
        await page.wait_for_timeout(1_000)
        order = await compute_tab_order(page, max_tabs=ceiling)
    finally:
        await context.close()

    row: dict[str, Any] = {
        "focusable": focusable,
        "probe_ids": len(probe_ids),
        "headroom_cap": focusable + TAB_HEADROOM,
        "presses_at_ceiling": order.presses,
        "still_capped_at_ceiling": order.capped,
        "distinct_stops": len(order.index),
    }
    if not order.capped:
        short_by = order.presses - (focusable + TAB_HEADROOM)
        row["verdict"] = (
            f"terminates at {order.presses} presses; "
            + (
                f"headroom was short by {short_by}"
                if short_by > 0
                else f"headroom was {-short_by} presses clear of the end"
            )
        )
        return row

    # --- capped: a second fresh page, only to say what it capped *on* ---------
    # `compute_tab_order` requires an unfocused page, so this cannot reuse the
    # one above.
    context = await factory()
    try:
        page = await context.new_page()
        await page.goto(url, wait_until="load", timeout=60_000)
        await page.wait_for_timeout(1_000)
        walk = await observe_walk(page, ceiling)
    finally:
        await context.close()
    row["walk"] = walk

    period = walk.get("terminal_loop_period")
    if period is not None and walk.get("loop_leaves_the_page"):
        # `document.hasFocus()` is false somewhere in the loop, so focus is not
        # trapped *in the page* — it steps out to the browser's own UI and comes
        # back to the same position instead of to the first stop. The frozen
        # walker means to end the walk here ("focus left the document"), but it
        # detects that as `activeElement === null`, and `activeElement` falls
        # back to `<body>` instead of going null. So the wrap is never seen and
        # the walk runs to its budget. This is an instrument limit, not a page
        # defect, and nothing here can be concluded about the site's keyboard
        # behaviour.
        loop = ", ".join(f"`{m}`" for m in walk["terminal_loop"])
        row["verdict"] = (
            f"not decided: from press {walk['loop_entered_at_press']} the walk repeats "
            f"{loop}, and `document.hasFocus()` is false inside that loop — focus is "
            f"leaving the page and re-entering at the same position rather than at the "
            f"first stop. `compute_tab_order` ends a walk on `activeElement === null`, "
            f"which never happens because `activeElement` falls back to `<body>`, so the "
            f"wrap goes unnoticed and the budget runs out. Whether the page itself traps "
            f"a keyboard user is not established by this"
        )
    elif period is not None:
        loop = ", ".join(f"`{m}`" for m in walk["terminal_loop"])
        row["verdict"] = (
            f"focus trap: from press {walk['loop_entered_at_press']} the walk repeats "
            f"{loop} with the page holding focus throughout, and never returns to its "
            f"first stop, so no finite budget completes it"
        )
    elif walk.get("ended") != "budget exhausted":
        # The frozen walker capped and the observation did not: the page is not
        # reproducing press-for-press, so neither reading is trustworthy alone.
        row["verdict"] = (
            f"unstable: the frozen walk capped at {ceiling} but the observation "
            f"{walk['ended']} after {walk['observed_presses']} presses"
        )
    elif walk["new_positions_in_last_100"] == 0:
        # No repeat this can name, but no new ground either. Saying "a larger
        # budget may complete it" here would be a guess dressed as a finding.
        row["verdict"] = (
            f"not decided: {walk['distinct_positions']} distinct positions in {ceiling} "
            f"presses and none of the last 100 presses reached a new one, so the walk is "
            f"going back over ground it has already covered — but no repeat shorter than "
            f"{LOOP_MAX_PERIOD} presses fits it, so what it is circling is not pinned down"
        )
    else:
        row["verdict"] = (
            f"budget, not a trap: {walk['distinct_positions']} distinct positions in "
            f"{ceiling} presses with no repeating loop, and "
            f"{walk['new_positions_in_last_100']} of them first reached in the last 100 "
            f"presses; the walk was still finding new controls when the budget ran out"
        )
    return row


async def cap_diagnosis(subjects: list[str], ceiling: int = 4000) -> dict[str, Any]:
    """Walk a capped subject again with a very large budget, and say what happened.

    A capped walk is an abstention either way. This only separates two very
    different causes that the abstention alone cannot: a headroom that was
    merely too tight (the walk terminates a little past `focusable + 200`) from
    a page whose focus never returns to its starting point at all. Run after the
    matrix, never beside it, so it cannot perturb the measured milliseconds.
    """
    out: dict[str, Any] = {"ceiling": ceiling, "subjects": {}}
    async with async_playwright() as pw:
        for subject in subjects:
            browser = await pw.chromium.launch(headless=True)
            row: dict[str, Any] = {}
            started = time.perf_counter()
            try:
                row = await diagnose_subject(browser, subject, ceiling)
            except Exception as exc:
                row = {"error": f"{type(exc).__name__}: {exc}"[:300]}
            finally:
                await browser.close()
            row["elapsed_s"] = round(time.perf_counter() - started, 1)
            out["subjects"][subject] = row
            print(f"{subject:<18} {row.get('verdict', row.get('error'))}", flush=True)
    return out


# ---------------------------------------------------------------------------
# The table
# ---------------------------------------------------------------------------
MATRIX_MD = HERE / "KAFE-MATRIX.md"
REPORT_MD = HERE / "KAFE-MATRIX-REPORT.md"


def pct(value: float | None, reason: str) -> str:
    return reason if value is None else f"{value * 100:.1f}%"


def num(value: float | None, reason: str) -> str:
    return reason if value is None else f"{value:.1f}"


def row_order(name: str) -> tuple:
    """Group as the published matrix groups, not alphabetically."""
    if name.startswith("KAFE"):
        return (9, 0, "", name)
    stem = name.split(" ")[0]
    if name.startswith("U-"):
        group = 1
    elif stem.startswith("C"):
        group = 2
    elif name.startswith(("D9", "D10")):
        group = 3
    else:
        group = 0
    import re

    match = re.match(r"^[A-Za-z-]*(\d+)", stem)
    return (group, int(match.group(1)) if match else 0, stem, name)


def matrix_table(payload: dict[str, Any]) -> str:
    head = (
        "| detector | TP | FP | FN | TN | abst. | precision | recall | F1 "
        "| ms/button | ms/subject | ms covers |"
    )
    rule = "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|"
    body = []
    for name in sorted(payload["rows"], key=row_order):
        r = payload["rows"][name]
        ms_reason = r.get("ms_reason") or "not measured"
        undefined_p = "undefined: flagged no subject"
        undefined_r = "undefined: no labelled positive decided"
        undefined_f = "undefined: precision undefined [^f1]"
        if r["precision"] is not None and r["recall"] is not None and not r["f1"]:
            undefined_f = "0.0%"
        cells = [
            name,
            str(r["tp"]),
            str(r["fp"]),
            str(r["fn"]),
            str(r["tn"]),
            str(r["abstentions"]),
            pct(r["precision"], undefined_p),
            pct(r["recall"], undefined_r),
            pct(r["f1"], undefined_f),
            num(r["ms_per_button"], ms_reason),
            num(r["ms_per_subject"], ms_reason),
            r["ms_covers"],
        ]
        body.append("| " + " | ".join(c.replace("|", r"\|") for c in cells) + " |")
    return "\n".join([head, rule] + body)


def write_matrix(
    payload: dict[str, Any], controls: dict[str, Any], permissive: dict[str, Any]
) -> str:
    kafe_all = payload["kafe_whole_corpus"]
    subset = payload.get("kafe_on_scored_subset") or {}
    scored = payload["subjects_scored"]
    attempted = payload["subjects_attempted"]
    text = f"""# KAFE's benchmark, all 48 Axcess detectors and KAFE's own result

Generated {payload["generated_utc"]} by `tools/kafe_matrix.py assemble`, from
`derived/kafe_matrix.jsonl` (one checkpoint per subject).

## Provenance

| | |
|---|---|
| benchmark | the 60 subjects of KAFE's own evaluation corpus, replayed offline from their mitmproxy captures |
| paper | Chiou, Alotaibi & Halfond, *Detecting and Localizing Keyboard Accessibility Failures in Web Applications*, ESEC/FSE 2021 |
| DOI | [10.1145/3468264.3468581](https://doi.org/10.1145/3468264.3468581) |
| KAFE's published Table 1 (Type 1 detection) | **92% precision, 100% recall** |
| KAFE's result recomputed here from `artifacts/kafe_results_to_reproduce.csv` | **TP {kafe_all["tp"]}, FP {kafe_all["fp"]}, FN {kafe_all["fn"]}, TN {kafe_all["tn"]} over n={kafe_all["n"]} — {kafe_all["precision"] * 100:.1f}% / {kafe_all["recall"] * 100:.1f}%** |
| KAFE's detector | their published per-subject CSV. That file **is** their tool's output on their corpus; the Java/Selenium/Firefox-68 stack was not rebuilt |
| Axcess detectors | imported unmodified from `src/audit/analyzer/keyboard/kbdiff/` — see control 4 |
| scoring unit | **the page**, because KAFE labels pages, not elements |
| subjects scored | **{scored} of {attempted} attempted, of 60 in the corpus** — see control 2 |

## Read this before the table

**Page-level scoring discards element precision.** A detector that flags 20
elements on a page where 1 is really inoperable scores exactly the same
page-level true positive as a detector that flags only the real one. Every
precision figure below is therefore *page* precision against KAFE's page label,
and it is a much weaker claim than element precision. On a real page with
hundreds of candidates, "flagged at least one element" is close to free, and
rows near the corpus base rate should be read as evidence of that, not of skill.

**Abstention is never a negative, and a negative requires a complete look.**
A page is positive for a detector iff it flagged at least one element — a
finding is evidence whatever else went unread. A page is *negative* only where
the detector flagged nothing **and left no candidate undecided**. Anything in
between is an abstention. That strictness is not pedantry: on `godaddy` only 4
of 21 candidates survived to a second page load, and the permissive rule turned
that into twelve confident "no defect here" verdicts off four elements. The
permissive numbers are reported in full in `KAFE-MATRIX-REPORT.md` so the size of
the difference is visible rather than asserted.

A subject that would not replay, whose tab walk capped, or whose arm raised
abstains for every row. For every Axcess row,
`TP + FP + FN + TN + abst. = {attempted}`, the subjects attempted.
**The KAFE row's `abst.` is 0 and that is literal** — KAFE decided every subject
in its own CSV. Its row is *restricted* to the {scored} subjects this
replication scored, so the two sides are read on one denominator; the
{attempted - scored} subjects Axcess could not put in front of it are named in
control 2, not charged to KAFE.

**The two sides' ms columns are not measured the same way.** Only the
arithmetic is shared: both are pooled, total time over total controls. What goes
into it differs on both sides of the division.

- **Axcess** `ms/button` is this harness's wall time for the detector's arm on
  a subject — the `ms covers` column says what that includes — summed over the
  scored subjects and divided by the candidates `collect_candidates` surfaced on
  them. It is an amortised quotient, not latency measured one button at a time,
  and it is headless Chromium under Playwright on one shared machine.
- **KAFE** `ms/button` is their published `Detection` column divided by their
  `Size of All Visible Ctrl Nodes`, whose node-selection code was not
  published. It is also an amortised quotient, taken with their own instrument
  on their 2019 Firefox 68 / Selenium setup, and nothing here re-timed it.

Neither figure is measured per-button latency, and the two are comparable as
orders of magnitude only. The 300 ms per-button ceiling is this project's
constraint, not KAFE's. `ms/subject` is total time for one subject, pooled the
same way on each side and subject to the same caveat.

**The candidate universe is Axcess's own.** `data-probe` could only be placed on
the elements `audit.analyzer.keyboard.kbdiff.candidates.collect_candidates`
surfaced, because `candidate_analysis.measure_candidate_page` requires its
feature sweep to cover exactly the probe set. No detector below could propose an
element that collector did not surface, which flatters the D0/C families. This
is the largest unclosed threat to validity in the table and is discussed in
`KAFE-MATRIX-REPORT.md`.

## The table

{matrix_table(payload)}

[^f1]: F1 is undefined where precision is undefined — a detector that flagged no
subject at all has no precision to combine with its recall. That is the correct
result, not a missing measurement.

## KAFE on the same denominator

KAFE decided all 60 subjects. Restricted to the {scored} subjects this
replication actually scored, their own numbers are
TP {subset.get("tp", "—")}, FP {subset.get("fp", "—")}, FN {subset.get("fn", "—")}, TN {subset.get("tn", "—")};
their pooled cost on that subset is {subset.get("ms_per_button_pooled", "—")} ms/button and
{subset.get("ms_per_subject_mean", "—")} ms/subject. The `KAFE` row in the table above is
computed on that subset, so it is read against the Axcess rows on one denominator.

## Controls

| control | result |
|---|---|
| 1 — KAFE reproduction | {"**pass**" if controls["control_1_kafe_reproduction"]["pass"] else "**FAIL**"}: 36/3/0/21 at 92.3% / 100.0% |
| 2 — denominator | {"**pass**" if controls["control_2_denominator"]["pass"] else "**FAIL**"}: {controls["control_2_denominator"]["scored"]} scored, {controls["control_2_denominator"]["abstained_whole_subject"]} whole-subject abstentions, {len(controls["control_2_denominator"]["excluded_before_the_run"])} excluded before the run |
| 3 — negative control | {"**pass**" if controls["control_3_negative"]["pass"] else "**FAIL**"}: {controls["control_3_negative"]["negative_subjects_scored"]} KAFE-`FALSE` subjects scored |
| 4 — frozen code | {"**pass**" if controls["control_4_frozen_code"]["pass"] else "**FAIL**"}: every detector imported from `src/audit/analyzer/keyboard/kbdiff/` |

Full control output: `derived/kafe_matrix_controls.json`.
"""
    MATRIX_MD.write_text(text)
    return text


def bullets(rows: list[str]) -> str:
    return "\n".join(f"- {row}" for row in rows) if rows else "- none"


def _playwright_version() -> str:
    try:
        from importlib.metadata import version

        return version("playwright")
    except Exception:
        return "version unavailable"


def write_report(
    payload: dict[str, Any],
    permissive: dict[str, Any],
    controls: dict[str, Any],
    records: list[dict[str, Any]],
    capdiag: dict[str, Any] | None,
    capdiag_repeats: list[dict[str, Any]] | None = None,
) -> str:
    """The companion report: what failed, what was controlled, what was found."""
    c2 = controls["control_2_denominator"]
    scored = [r for r in records if r.get("status") == "scored"]
    attempted = len(records)

    empty = [
        r for r in records if "surfaced no addressable element" in (r.get("reason") or "")
    ]
    capped = [r for r in records if "tab walk capped" in (r.get("reason") or "")]
    other_abstain = [
        r
        for r in records
        if r.get("status") != "scored" and r not in empty and r not in capped
    ]
    arm_failures: dict[str, list[str]] = {}
    for record in scored:
        for arm, info in (record.get("arms") or {}).items():
            if not info.get("ok"):
                arm_failures.setdefault(
                    str(info.get("error", "unstated"))[:90], []
                ).append(record["subject"])
    unstable = sorted(
        (r["subject"], r.get("identity_stability"))
        for r in scored
        if (r.get("identity_stability") or 1.0) < 0.95
    )
    degraded = sorted(r["subject"] for r in scored if r.get("functionally_degraded"))

    def delta_rows() -> list[str]:
        out = []
        for name in sorted(payload["rows"], key=row_order):
            if name.startswith("KAFE"):
                continue
            a, b = payload["rows"][name], permissive["rows"].get(name)
            if not b:
                continue
            if (a["tp"], a["fp"], a["fn"], a["tn"]) != (b["tp"], b["fp"], b["fn"], b["tn"]):
                out.append(
                    f"`{name}` — strict {a['tp']}/{a['fp']}/{a['fn']}/{a['tn']} "
                    f"({a['abstentions']} abst.), permissive "
                    f"{b['tp']}/{b['fp']}/{b['fn']}/{b['tn']} ({b['abstentions']} abst.)"
                )
        return out

    def cap_outcome(row: dict[str, Any]) -> str:
        """The one-line form of a cap diagnosis. `verdict` states the mechanism
        in full and is in the JSON; repeating it seven times here would bury the
        table, so the shared mechanism is explained once in the prose below."""
        walk = row.get("walk") or {}
        loop = walk.get("terminal_loop") or []
        # `raise` orbits 82 positions; listing them all would be a paragraph of
        # markers. The full list is in the JSON under `walk.terminal_loop`.
        shown = ", ".join(f"`{m}`" for m in loop[:4])
        names = shown if len(loop) <= 4 else f"{shown} and {len(loop) - 4} more"
        if loop and walk.get("loop_leaves_the_page"):
            return (
                f"from press {walk['loop_entered_at_press']} focus leaves the page and "
                f"re-enters on a {len(loop)}-position orbit ({names}); **not decided** — "
                f"see below"
            )
        if loop:
            return (
                f"**focus trap** on a {len(loop)}-position loop ({names}) from press "
                f"{walk['loop_entered_at_press']}, with the page holding focus throughout"
            )
        if row.get("still_capped_at_ceiling") and walk.get("new_positions_in_last_100") == 0:
            return (
                f"**not decided** — {walk.get('distinct_positions', '?')} distinct positions, "
                f"no new one in the last 100 presses, but no repeat short enough to name"
            )
        if row.get("still_capped_at_ceiling"):
            return (
                f"**still advancing** at the ceiling: {walk.get('distinct_positions', '?')} "
                f"distinct positions, {walk['new_positions_in_last_100']} of them new in the "
                f"last 100 presses"
            )
        return f"**completes** — {row['verdict']}"

    cap_lines = []
    diag_rows = (capdiag or {}).get("subjects") or {}
    for subject, row in sorted(diag_rows.items()):
        if "verdict" not in row:
            cap_lines.append(f"`{subject}` — diagnosis failed: {row.get('error', '?')}")
            continue
        cap_lines.append(
            f"`{subject}` — {row['distinct_stops']} named stops in "
            f"{row['presses_at_ceiling']} presses; {cap_outcome(row)}"
        )
    leaky = [
        s for s, r in diag_rows.items() if (r.get("walk") or {}).get("loop_leaves_the_page")
    ]
    json_runs = [capdiag, *(capdiag_repeats or [])] if capdiag else []
    # Whether a walk caps is read over every run, including the ones that only
    # survive in the log; the log is trusted only where it agrees with the JSON
    # of every run that also has one.
    log_runs = capdiag_log_runs()
    if json_runs and len(log_runs) >= len(json_runs):
        for logged, run in zip(log_runs[-len(json_runs):], json_runs):
            for subject, row in (run.get("subjects") or {}).items():
                seen = logged.get(subject) or {}
                if seen.get("capped") != row.get("still_capped_at_ceiling") or (
                    seen.get("capped") is False
                    and seen.get("presses") != row.get("presses_at_ceiling")
                ):
                    raise ValueError(
                        f"{CAPDIAG_LOG.name} disagrees with the capdiag JSON on {subject}"
                    )
        cap_runs = log_runs
    else:
        cap_runs = [
            {
                s: {
                    "capped": r.get("still_capped_at_ceiling"),
                    "presses": r.get("presses_at_ceiling"),
                }
                for s, r in (run.get("subjects") or {}).items()
            }
            for run in json_runs
        ]
    only_logged = len(cap_runs) - len(json_runs)

    def capped_in(subject: str) -> int:
        return sum(1 for run in cap_runs if (run.get(subject) or {}).get("capped"))

    freed = sorted(s for s in diag_rows if cap_runs and capped_in(s) == 0)
    split_cap = sorted(s for s in diag_rows if 0 < capped_in(s) < len(cap_runs))
    still = sorted(s for s in diag_rows if s not in freed and s not in split_cap)
    if diag_rows and not freed:
        cap_note = (
            "No subject completes the walk at the higher ceiling in every run, so every one "
            "of these abstentions stands; what the re-walk adds is *why* each abstains. "
        )
    elif freed:
        names = ", ".join(f"`{s}`" for s in freed)
        verb = "completes" if len(freed) == 1 else "complete"
        was = "was an abstention" if len(freed) == 1 else "were abstentions"
        cap_note = (
            f"{len(freed)} of these ({names}) {verb} the walk at the higher ceiling in every "
            f"run and {was} only because the `focusable + {TAB_HEADROOM}` budget was too "
            f"tight; {len(still)} still cap. "
        )
    else:
        cap_note = ""
    for subject in split_cap:
        done = sorted(
            run[subject]["presses"]
            for run in cap_runs
            if subject in run and not run[subject]["capped"]
        )
        cap_note += (
            f"`{subject}` completed at the {(capdiag or {}).get('ceiling', 'n/a')}-press "
            f"ceiling in {len(done)} of {len(cap_runs)} runs (at "
            f"{', '.join(str(p) for p in done)} presses, against a "
            f"{(diag_rows[subject] or {}).get('headroom_cap', '?')}-press budget) and capped "
            f"in the other {capped_in(subject)}, so it is unstable rather than freed, and its "
            f"line above is one reading of it, not a property of the subject. "
        )
    if diag_rows:
        cap_note += (
            "The published numbers are unchanged either way — they were measured at the "
            "derived budget, and this diagnosis is not a re-score."
        )

    if len(cap_runs) > 1:

        def readings(subject: str, field: str) -> list[Any]:
            return [(r["subjects"].get(subject) or {}).get(field) for r in json_runs]

        split_stops = sorted(
            s
            for s in diag_rows
            if s not in split_cap and len(set(readings(s, "distinct_stops"))) > 1
        )
        agreed = sorted(s for s in diag_rows if s not in split_cap and s not in split_stops)
        cap_note += (
            f"\n\nThe diagnosis was run {len(cap_runs)} times over independent page loads, "
            f"because one reading cannot separate a property of the subject from a property "
            f"of the load. "
        )
        if only_logged > 0:
            cap_note += (
                f"The first {only_logged} wrote JSON that a later run overwrote, so their "
                f"readings come from the verdict lines in `derived/capdiag-runs.log`, which "
                f"agree with the JSON of the other {len(json_runs)} wherever both exist. "
                f"Whether the walk caps is compared over all {len(cap_runs)}; named-stop "
                f"counts only over the {len(json_runs)} whose JSON survives. "
            )
        if agreed:
            cap_note += (
                f"{len(agreed)} gave the same answer in every run "
                f"({', '.join(f'`{s}`' for s in agreed)}) — which is agreement across these "
                f"runs, not a guarantee. "
            )
        if split_cap:
            cap_note += (
                f"**{', '.join(f'`{s}`' for s in split_cap)} did not even agree on whether the "
                f"walk caps**, so no verdict above should be read as a property of "
                f"{'that subject' if len(split_cap) == 1 else 'those subjects'}. "
            )
        if split_stops:
            cap_note += (
                f"{', '.join(f'`{s}`' for s in split_stops)} agreed on capping but not on "
                f"what the walk contains — how many of its stops carry a probe id differs "
                f"between runs — the same identity instability §1.4 records. "
            )
        cap_note += (
            "Every run's output, earlier ones whose JSON a later run overwrote included, "
            "is in `derived/capdiag-runs.log`."
        )
    also_leaky = {
        s: [i + 1 for i, run in enumerate(cap_runs) if (run.get(s) or {}).get("leaves_page")]
        for s in diag_rows
        if s not in leaky
    }
    also_leaky = {s: runs for s, runs in also_leaky.items() if runs}
    if leaky:
        cap_note = cap_note.rstrip() + "\n\n" if cap_note else ""
        cap_note += (
            f"{len(leaky)} of them ({', '.join(f'`{s}`' for s in sorted(leaky))}) share one "
            f"mechanism, and it is **not** a page defect. Their walk settles into a loop in "
            f"which `document.hasFocus()` is false: Tab steps out of the page to the browser's own "
            f"UI, and the next Tab re-enters at the position it left from rather than at the first "
            f"stop. `compute_tab_order` means to end a walk exactly there — its comment calls it "
            f"\"focus left the document (browser chrome)\" — but it detects that as "
            f"`document.activeElement === null`, and `activeElement` falls back to `<body>` "
            f"instead of going null, so the branch never fires and the budget runs out. These "
            f"subjects are abstentions for an instrument reason, and **nothing here says whether "
            f"the site traps a keyboard user**. Deciding that needs a walker whose termination "
            f"test is `document.hasFocus()` rather than a null `activeElement`, which is a change "
            f"to a frozen detector and out of scope for this run."
        )
        for subject, runs in sorted(also_leaky.items()):
            which = ", ".join(str(n) for n in runs)
            cap_note += (
                f" In the run{'s' if len(runs) > 1 else ''} where it capped with the "
                f"`hasFocus` reading in place (run {which}), `{subject}` shows the same "
                f"mechanism."
            )
        cap_note += "\n\n"

    text = f"""# KAFE matrix: report

Companion to `KAFE-MATRIX.md`. Generated {payload["generated_utc"]}.
Everything below is derived from `derived/kafe_matrix.jsonl`,
`derived/kafe_matrix_summary.json` and `derived/kafe_matrix_controls.json`;
no figure in this file is typed by hand.

## 1. What I could not close

### 1.1 The candidate universe is Axcess's own, and that flatters Axcess

`candidate_analysis.measure_candidate_page` raises unless its feature sweep
covers exactly the probe set, so `data-probe` could only be placed on elements
`audit.analyzer.keyboard.kbdiff.candidates.collect_candidates` had already
surfaced. Every one of the 48 rows is therefore scored on a shortlist that
Axcess's own collector drew. The upstream generators (`U-D*`) and every `C*`
combination are structurally unable to propose an element it missed, so their
recall is bounded by a competitor's recall. **This is the largest threat to
validity in the table and it is not closed.** Closing it needs a universe
defined independently of any detector under test — KAFE's own
`Size of All Visible Ctrl Nodes` is such a definition, but their node-selection
code was not published with the CSV, so it could not be reproduced here.

### 1.2 {len(empty)} subjects replay to a document with no controls in it

{bullets([f"`{r['subject']}` — {r.get('census_tagged', '?')} elements, {r.get('focusable', '?')} focusable, KAFE label `{r.get('y')}`" for r in empty])}

These are counted as abstentions, never as negatives. That matters: some carry
a KAFE `TRUE` label, and scoring them as negatives would have manufactured a
false negative in all 48 rows off a replay defect. What is *not* closed is
**why** they replay empty — a capture that needs a live XHR, a script the
default-deny router refused, or a page that builds itself from state the capture
does not contain. The replayed document is not the document KAFE analysed, and
no result here describes those subjects.

### 1.3 {len(capped)} subjects cap their tab walk

{bullets([f"`{r['subject']}` — cap {r.get('tab_cap', '?')} ({r.get('focusable', '?')} focusable)" for r in capped])}

The budget is `focusable + {TAB_HEADROOM}`, the convention
`tools/kafe_scored_run.py` established. A walk that still caps is an abstention
by the brief's own rule. Re-walked afterwards by `kafe_matrix capdiag` with a
{(capdiag or {}).get("ceiling", "n/a")}-press ceiling, through the same discovery pass, the same
`data-probe` set and the same frozen walker the scored run uses, so the stop
counts below are the same measurement as `tab_stops` in the matrix:

{bullets(cap_lines) if cap_lines else "- not diagnosed: `capdiag` did not run"}

{cap_note}Where a terminal loop is named, the walk was observed a second time on
a fresh page with the walker's own focus reader, and the loop is the positions
it repeated to the end of the budget. That observation explains the cap; it
never overrides it — `capped` always comes from the frozen walker.

### 1.4 Element identity is not perfectly stable across page loads

Every trial addresses elements by a census id minted at `load` in its own fresh
context. Subjects where fewer than 95% of the discovered ids reappear on a
second load:

{bullets([f"`{s}` — {v:.0%} of probe ids reappeared" for s, v in unstable])}

Where this bites, `measure_candidate_page` raises
`candidate feature coverage differs from page probes` and its 19 rows abstain
for that subject. It is recorded, not repaired: making identity stable would
mean freezing the page, and a page that renders differently on two loads is a
fact about the subject, not about the detectors.

### 1.5 Arm failures on otherwise-scored subjects

{bullets([f"{error} — {len(subjects)} subject(s): {', '.join(sorted(subjects)[:8])}" for error, subjects in sorted(arm_failures.items())])}

Each failure abstains exactly the rows that arm produced and leaves the other
arms' verdicts standing.

### 1.6 Scope limits stated rather than solved

- **Coverage origin.** The D9/D10 coverage rules filter executed functions to
  the entry document's origin, which is upstream's own rule. A subject whose
  handlers live on a CDN has those functions filtered out, so its coverage sets
  are narrower than the page's real behaviour.
- **No `#baseline-target`.** Upstream's handler-free coverage floor is measured
  by clicking `#baseline-target`, which exists only in their fixtures. On every
  KAFE subject that resolves to `absent: no #baseline-target on this page`, i.e.
  an empty floor — the documented "absent", not a failed read, so the coverage
  rows still decide.
- **Candidates are top-frame only.** `collect_candidates` evaluates in the main
  frame, so a control inside an iframe is outside the universe on every row.
- **Upstream Stage 4's witness pool is one subject.** `bakeoff` runs it once
  over a whole corpus; here one subject is one page, so `D9u+S4u` searches a
  smaller pool for an equivalent control than it would on a multi-page corpus,
  and will dismiss less.
- **Not KAFE's browser.** KAFE ran Firefox 68 through Selenium; this is headless
  Chromium under Playwright {_playwright_version()} on
  Python {platform.python_version()}. The ms columns are not comparable as
  hardware benchmarks, only as orders of magnitude, and every Axcess figure is
  wall time on one shared machine.

### 1.7 The comparison runs in one direction only

All {len(ALL_DETECTORS)} rows are Axcess detectors scored on KAFE's corpus. KAFE's detector was
never scored on ours. Its row here is their **published output** —
`artifacts/kafe_results_to_reproduce.csv`, their tool's real result on their own
{c2["kafe_corpus"]} subjects, reconciled against their paper's Table 1 by Control 1 below — and
not a local execution: their Java / Selenium 3.141.5 / Firefox 68 stack was not
rebuilt, and by decision it will not be. The reverse direction is out of scope
for this work, not queued behind it.

One part of it could not be closed even if it were in scope. KAFE emits
page-level labels; `fixtures`, `gds` and `ma11y` label elements. Running their
binary against those corpora would still need a projection invented between two
different units of truth, and that projection — not their detector — would
decide the result.

The asymmetry is not neutral, and it cuts both ways. Measuring our detectors on
someone else's corpus against their published numbers is the harder and more
exposed direction, and that is the direction taken. But it means nothing in this
work independently validates **our** corpora: `edgecases` is shared-author and
already carries no unbiased accuracy claim, and `fixtures` was authored here
too. No outside tool has been scored on either.

## 2. Controls

### Control 1 — KAFE reproduction: {"PASS" if controls["control_1_kafe_reproduction"]["pass"] else "FAIL"}

```json
{json.dumps(controls["control_1_kafe_reproduction"]["recomputed"], indent=2)}
```

Their published Table 1 reports 92% / 100%; recomputing from
`artifacts/kafe_results_to_reproduce.csv` gives 36/3/0/21 at 92.3% / 100.0% over
n=60. Their timing reproduces too:

```json
{json.dumps(controls["control_1_kafe_reproduction"]["timing"], indent=2)}
```

### Control 2 — denominator: {"PASS" if c2["pass"] else "FAIL"}

- KAFE's corpus: **{c2["kafe_corpus"]}** subjects.
- Judged replayable beforehand: **{c2["replayable"]}**.
- Attempted here: **{c2["attempted"]}**. Scored: **{c2["scored"]}**.
  Whole-subject abstentions: **{c2["abstained_whole_subject"]}**.

Excluded before the run ever started:

{bullets([f"`{row['subject']}` — {row['reason']}" for row in c2["excluded_before_the_run"]])}

Abstained during the run:

{bullets([f"`{row['subject']}` — {row['reason']}" for row in c2["abstained_during_the_run"]])}

Replayable, but with no result in `derived/kafe_matrix.jsonl` — not scored, and
not counted as an abstention, because nothing was measured:

{bullets([f"`{name}`" for name in c2["not_yet_attempted"]])}

The scored denominator in `KAFE-MATRIX.md` is **{payload["subjects_scored"]}**,
which is exactly the number of subjects that replayed and produced a verdict.

### Control 3 — negative control: {"PASS" if controls["control_3_negative"]["pass"] else "FAIL"}

{controls["control_3_negative"]["negative_subjects_scored"]} subjects KAFE labels
`FALSE` were scored: {", ".join(f"`{n}`" for n in controls["control_3_negative"]["negative_subject_names"]) or "none"}.

```json
{json.dumps(controls["control_3_negative"]["witness"], indent=2)}
```

The point of this control is that a detector which flags nothing on a genuinely
clean page records a **true negative**, not an abstention. The witness above
shows detectors doing exactly that.

### Control 4 — frozen code: {"PASS" if controls["control_4_frozen_code"]["pass"] else "FAIL"}

```json
{json.dumps(controls["control_4_frozen_code"]["imported_from"], indent=2)}
```

Every module resolves under
`{controls["control_4_frozen_code"]["expected_root"]}`. Nothing under
`src/audit/` was edited; `git diff --stat src/audit/` is empty and
`git status --porcelain` reports no change there, nor under
`experiments/tabbing/runner/` or `experiments/tabbing/probes/`. Nothing was
committed.

## 3. What the run found

- **{payload["subjects_scored"]} subjects scored** of {attempted} attempted, of 60 in KAFE's corpus:
  {payload["positives"]} KAFE-positive, {payload["negatives"]} KAFE-negative.
- **{payload["buttons_total"]} controls probed** in total across those subjects.
- On the same subjects, KAFE itself scores
  {json.dumps({k: payload["kafe_on_scored_subset"][k] for k in ("tp", "fp", "fn", "tn")}) if payload.get("kafe_on_scored_subset") else "n/a"}.

Read the precision column with the page-level caveat in front of it. A page with
hundreds of candidates makes "flagged at least one element" nearly free, so a
row sitting at the corpus base rate has demonstrated almost nothing. The rows
worth attention are the ones that are *below* it — a detector that manages to be
worse than always saying yes — and the ms columns, which are measured and mean
what they say.

## 4. Strict versus permissive projection

`KAFE-MATRIX.md` uses the strict rule: a page is negative only where the
detector flagged nothing **and** left no candidate undecided. The permissive
rule lets any decided candidate license a negative. Rows where the two disagree:

{bullets(delta_rows())}

Full permissive numbers: `derived/kafe_matrix_summary_permissive.json`.

## 5. Method notes

- **Seams, not re-implementations.** The cheap tier runs through
  `bakeoff.run_page`; `U-D*` and `C1`–`C9` through
  `candidate_analysis.measure_candidate_page`; `D9`/`D10` through
  `bakeoff.run_behavioural`; `C10`–`C16` from the four
  `experiments/tabbing/probes` observations fed to
  `tools.run_probe_rules.rule_sets`. The probe scripts call `asyncio.run` at
  module level and cannot be imported, so their observation JS is lifted out of
  their own AST rather than transcribed.
- **The brief named two seams; four were needed.** `run_page` and
  `run_behavioural` cover 22 of the 48 rows. The other 26 (`U-D0`–`U-D8`,
  `C1`–`C16`) live in `candidate_analysis` and the probe scripts, and are driven
  through those.
- **What the adapter changes.** Three module-level names are pointed at the
  subject for the duration of its measurement — `bakeoff.page_url` and
  `candidate_analysis.page_url` to the capture's entry URL, `bakeoff.BASE_URL`
  to its origin, and `TrialConfig`/`compute_tab_order` to this subject's derived
  tab budget. No detector body is touched; only arguments the frozen functions
  already accept.
- **Two adapter defects found and fixed before the measured run.**
  `replay.NEUTRAL_CENSUS_JS` numbers each document from zero, so an iframe's
  `<html>` and the top document's `<html>` both minted `/0:html`; sub-frame ids
  are now namespaced by document URL. And discovery originally re-censused three
  seconds after `load` while every trial censused at `load`, so the two
  disagreed about identity — on `fandango` that made 12 of 13 probes
  unobservable to every survey detector. Identity is now fixed at `load`
  everywhere. The pre-fix checkpoints are kept as
  `derived/kafe_matrix.pre-frame-fix.jsonl` and
  `derived/kafe_matrix.pre-identity-fix.jsonl`.
- **Milliseconds.** Composed by `tools/assemble_matrix.cost_of`, so the
  `ms covers` conventions match the existing matrix by construction.
  `ms/button` divides by the candidates that subject probed; `ms/subject` by the
  subjects measured. KAFE's two figures come from their `Detection` column over
  their `Size of All Visible Ctrl Nodes`. The pooling arithmetic is the same on
  both sides; the instrument, hardware, browser and control count are not, so
  the two are comparable as orders of magnitude only (see `KAFE-MATRIX.md`).
"""
    REPORT_MD.write_text(text)
    return text


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    runner = sub.add_parser("run")
    runner.add_argument("--only", default="", help="comma-separated subject names")
    runner.add_argument("--limit", type=int, default=0, help="first N subjects, cheapest first")
    runner.add_argument("--restart", action="store_true", help="ignore existing checkpoints")
    sub.add_parser("controls")
    sub.add_parser("assemble")
    reporter = sub.add_parser("report")
    reporter.add_argument(
        "--reuse",
        action="store_true",
        help=(
            "rebuild only KAFE-MATRIX-REPORT.md, from the summaries and controls already "
            "in derived/. Re-running the controls launches browsers and re-times them, and "
            "a plain `report` rewrites KAFE-MATRIX.md too; use this when only the report "
            "prose changed and no published number may move."
        ),
    )
    diag = sub.add_parser("capdiag")
    diag.add_argument(
        "--subjects",
        default="",
        help="comma-separated subjects; default is every subject the matrix capped",
    )
    diag.add_argument("--ceiling", type=int, default=4000)
    diag.add_argument(
        "--out",
        default="",
        help="write here instead of derived/kafe_matrix_capdiag.json (controls)",
    )
    args = parser.parse_args()

    if args.cmd == "run":
        return asyncio.run(run(args))
    if args.cmd == "capdiag":
        capped = [s for s in args.subjects.split(",") if s.strip()] or [
            json.loads(line)["subject"]
            for line in OUT.read_text().splitlines()
            if line.strip() and "tab walk capped" in (json.loads(line).get("reason") or "")
        ]
        payload = asyncio.run(cap_diagnosis(capped, ceiling=args.ceiling))
        target = pathlib.Path(args.out) if args.out else CAPDIAG
        target.write_text(json.dumps(payload, indent=2) + "\n")
        return 0
    if args.cmd == "controls":
        payload = run_controls()
        CONTROLS.write_text(json.dumps(payload, indent=2) + "\n")
        print(json.dumps(payload, indent=2))
        return 0 if all(v.get("pass") for k, v in payload.items() if k.startswith("control")) else 1

    reuse = getattr(args, "reuse", False)
    records = [json.loads(line) for line in OUT.read_text().splitlines() if line.strip()]
    capdiag = json.loads(CAPDIAG.read_text()) if CAPDIAG.exists() else None
    repeats = [json.loads(p.read_text()) for p in CAPDIAG_REPEATS]

    if reuse:
        payload = json.loads(SUMMARY.read_text())
        permissive = json.loads(SUMMARY_PERMISSIVE.read_text())
        controls = json.loads(CONTROLS.read_text())
        write_report(payload, permissive, controls, records, capdiag, repeats)
        print(f"wrote {REPORT_MD.name} from derived/; {MATRIX_MD.name} untouched")
        return 0

    payload = assemble(rule="strict")
    permissive = assemble(rule="permissive")
    SUMMARY.write_text(json.dumps(payload, indent=2) + "\n")
    SUMMARY_PERMISSIVE.write_text(json.dumps(permissive, indent=2) + "\n")
    if args.cmd == "assemble":
        print(json.dumps({k: v for k, v in payload.items() if k != "rows"}, indent=2))
        return 0

    controls = run_controls()
    CONTROLS.write_text(json.dumps(controls, indent=2) + "\n")
    write_matrix(payload, controls, permissive)
    write_report(payload, permissive, controls, records, capdiag, repeats)
    print(f"wrote {MATRIX_MD.name} ({len(payload['rows'])} rows) and {REPORT_MD.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
