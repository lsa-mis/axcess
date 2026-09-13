"""Score all twelve detectors on one corpus, on identical pages.

    .venv/bin/python experiments/tabbing/runner/bakeoff.py --corpus edgecases
    .venv/bin/python experiments/tabbing/runner/bakeoff.py --corpus fixtures

This is the convergence half of the exercise: the divergent edge-case space is
cut down to one table where every detector sees exactly the same pages, so the
differences between them are attributable to the detectors rather than to what
each was shown.

Two things about reading the output honestly:

* On the ``edgecases`` corpus the fixtures and the detectors share one author.
  It is development evidence, with no unbiased accuracy or ranking claim.
* On the ``fixtures`` corpus the pages were authored blind by the other agent
  and frozen before any detector ran, so those numbers do carry weight. They are
  limited to these synthetic fixtures and this runner's method definitions.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import platform
import sys
import time
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
for extra in (REPO_ROOT, REPO_ROOT / "src"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from playwright.async_api import async_playwright  # noqa: E402

from audit.analyzer.axe import AxeAnalyzer  # noqa: E402
from audit.analyzer.keyboard.kbdiff import channels, coverage, detectors  # noqa: E402
from audit.analyzer.keyboard.kbdiff.differential import (  # noqa: E402
    DifferentialRunner,
    TrialConfig,
)
from audit.analyzer.keyboard.kbdiff.equivalence import (  # noqa: E402
    apply_equivalence,
    by_coverage_exact,
)
from audit.analyzer.keyboard.kbdiff.model import Uncertainty, Verdict  # noqa: E402
from audit.analyzer.keyboard.kbdiff.score import (  # noqa: E402
    Score,
    check_invariant,
    score_outcomes,
)
from audit.analyzer.keyboard.kbdiff.taborder import TabOrder, compute_tab_order  # noqa: E402
from audit.logging import get_logger  # noqa: E402
from experiments.tabbing.runner import candidate_analysis, upstream_candidates  # noqa: E402
from experiments.tabbing.runner.corpus import (  # noqa: E402
    LABELS,
    compute_corpus_sha256,
    load_corpus,
    sha256_file,
)
from experiments.tabbing.runner.provenance import (  # noqa: E402
    bounded_int,
    require_new_outputs,
    safe_label,
    source_sha256,
    write_new,
)
from experiments.tabbing.runner.run import (  # noqa: E402
    serialize_outcome,
    unknown_outcome,
)
from experiments.tabbing.runner.serve import (  # noqa: E402
    BASE_URL,
    ContextFactory,
    page_url,
)
from experiments.tabbing.runner.upstream_instrument import (  # noqa: E402
    UPSTREAM_INIT_JS,
    UPSTREAM_SNAPSHOT_CALL,
)

log = get_logger(__name__)

VIEWPORT = {"width": 1280, "height": 900}
PAGE_TIMEOUT_SECONDS = 300
PROBE_TIMEOUT_SECONDS = 60
D9_NAME = "D9 behavioural differential"
D10_NAME = "D10a coverage differential (Enter only, no baseline subtraction)"
# Upstream's three formulations we had not measured. Each is a faithful port of
# the rule in their DETECTORS.md, kept as its own row rather than folded into
# ours, so the comparison stays a comparison.
D9U_NAME = "D9u upstream-style differential (8 channels, keys in sequence)"
# Stage 4 is upstream's highest-scoring stage. Scoring the differential with no
# equivalence, with ours, and with theirs isolates what the stage itself
# contributes -- the three rows differ only in that filter.
D9_NOS4_NAME = "D9-noS4 coverage-armed differential, no equivalence filter"
D9_S4OURS_NAME = "D9+S4ours coverage-armed differential, our payload Stage 4"
# The 1:1 pipeline: upstream's differential filtered by upstream's Stage 4.
D9U_S4U_NAME = "D9u+S4u upstream differential with upstream Stage 4 (1:1)"
# Upstream's D10a/D10b run over the SAME sequential trial as their D9, with the
# handler-free baseline subtracted from both sides. Our Enter-only rows are
# modified variants and are named as such; these two are the ports.
D10A_U_NAME = "D10a-u upstream coverage presence (sequential keys, baselined)"
D10B_U_NAME = "D10b-u upstream coverage set-difference (sequential keys, baselined)"
D9_S4U_NAME = "D9+S4u differential with upstream Stage 4 (coverage-exact)"
D10B_NAME = "D10b coverage set-difference (Enter only, no baseline subtraction)"
D10BASE_NAME = "D10a+base coverage differential (Enter only, baseline subtracted)"

# Upstream observed eight channels and compared presence: "did anything change
# on this channel?" Ours drops `mutations` -- a MutationObserver record count
# that the `dom` digest already covers except when edits net out -- and compares
# payloads instead. D9u restores both their channel set and their comparison so
# the difference is measured rather than asserted.
UPSTREAM_CHANNELS: tuple[str, ...] = (
    "dom",
    "geometry",
    "mutations",
    "net",
    "storage",
    "console",
    "canvas",
    "nav",
)


def upstream_delta(before: dict[str, Any], after: dict[str, Any]) -> set[str]:
    """One frame's channel delta, mirroring ``instrument.ts``'s ``delta()``.

    Every rule here is theirs: digests compare unequal, counters compare
    strictly greater, and ``nav`` fires on either a new navigation event or a
    changed href.
    """
    changed: set[str] = set()
    for channel in ("dom", "geometry"):
        if before.get(channel) != after.get(channel):
            changed.add(channel)
    for channel in ("mutations", "net", "storage", "console", "canvas"):
        if int(after.get(channel) or 0) > int(before.get(channel) or 0):
            changed.add(channel)
    if int(after.get("nav") or 0) > int(before.get("nav") or 0) or before.get("href") != after.get(
        "href"
    ):
        changed.add("nav")
    return changed


CHEAP_METHODS = (
    "D0 axcess collectClickables",
    "D2 inline onclick attribute",
    "D2b onclick property",
    "D3 tabindex / ARIA",
    "D4 CSS + lexical",
    "D7 React fiber props",
    "D5 CDP getEventListeners",
    "D6 addEventListener shim",
    "D8 hover-diff",
    "D1 axe-core (keyboard rules)",
    "D1x axe-core (any rule, unsound)",
)

CORPORA = {
    "edgecases": (
        REPO_ROOT / "experiments" / "tabbing" / "edgecases",
        "truth.json",
        "shared-author development corpus; no unbiased accuracy or ranking claim",
    ),
    "fixtures": (
        REPO_ROOT / "experiments" / "tabbing" / "fixtures",
        "truth.json",
        "blind-authored and frozen synthetic corpus; results describe this corpus and runner only",
    ),
}


def load_truth(root: Path, name: str) -> tuple[dict[str, list[str]], dict[str, str]]:
    """Page -> probe ids, and probe id -> label."""
    data = json.loads((root / name).read_text())
    pages = {p: list(ids) for p, ids in data["pages"].items()}
    labels = {
        pid: raw.get("labels_by_viewport", {}).get("desktop", raw["label"])
        for pid, raw in data["probes"].items()
    }
    page_ids = [pid for ids in pages.values() for pid in ids]
    if len(page_ids) != len(set(page_ids)) or set(page_ids) != set(labels):
        raise ValueError("truth must assign every labelled probe to exactly one page")
    if not labels or any(label not in LABELS for label in labels.values()):
        raise ValueError("truth has no probes or contains an unsupported label")
    if any(not (root / page).resolve().is_relative_to(root.resolve()) for page in pages):
        raise ValueError("truth contains a page outside the corpus")
    return pages, labels


def corpus_fingerprint(root: Path, corpus: str) -> str:
    """Pin inputs only; generated results never change the development hash."""
    if corpus == "fixtures":
        return load_corpus(root).corpus_sha256
    inputs = [root / "truth.json", *sorted((root / "pages").rglob("*"))]
    files = {str(path.relative_to(root)): sha256_file(path) for path in inputs if path.is_file()}
    return compute_corpus_sha256(files)


class CheckedInstrument:
    """Surface instrument exceptions even when a reused detector catches them."""

    def __init__(self, target: Any) -> None:
        self.target = target
        self.errors: list[str] = []

    def __getattr__(self, name: str) -> Any:
        method = getattr(self.target, name)
        if name not in {"evaluate", "add_script_tag", "send"}:
            return method

        async def checked(*args: Any, **kwargs: Any) -> Any:
            try:
                result = await method(*args, **kwargs)
                if (
                    name == "send"
                    and args[0] == "Profiler.takePreciseCoverage"
                    and (not isinstance(result, dict) or not isinstance(result.get("result"), list))
                ):
                    raise ValueError("malformed precise-coverage result")
                if name == "send" and isinstance(result, dict) and result.get("exceptionDetails"):
                    raise RuntimeError("CDP evaluation failed")
                return result
            except Exception as exc:
                self.errors.append(f"{name}: {type(exc).__name__}: {exc}"[:240])
                raise

        return checked

    def require_success(self) -> None:
        if self.errors:
            raise RuntimeError("instrument failed: " + "; ".join(self.errors[:3]))


async def run_page(
    factory: ContextFactory,
    root: Path,
    page_path: str,
    probe_ids: list[str],
    axe: AxeAnalyzer,
) -> tuple[dict[str, set[str]], TabOrder, dict[str, Any]]:
    """Run every detector against one page.

    Returns the ids each detector reported, plus — under ``meta['unobservable']``
    — the probes no survey-based detector could even look at. A probe sealed in a
    closed shadow root is invisible to every DOM-walking detector, and scoring
    that as "found nothing" credits them with a judgement they never made.
    """
    url = page_url(page_path)
    reported: dict[str, set[str]] = {}
    meta: dict[str, Any] = {"notes": {}, "timings": {}, "proposed": {}}

    # --- one context carrying both shims, for the survey + listener routes ---
    context = await factory()
    try:
        await context.add_init_script(detectors.LISTENER_SHIM_JS)
        await context.add_init_script(channels.INIT_SCRIPT)
        raw_page = await context.new_page()
        page: Any = CheckedInstrument(raw_page)
        cdp: Any = CheckedInstrument(await context.new_cdp_session(raw_page))
        await page.goto(url, wait_until="load")
        await page.wait_for_timeout(150)
        meta["viewport"] = dict(page.viewport_size)
        order = await compute_tab_order(page)
        page.require_success()

        # One DOM walk feeds six detectors. Upstream ran a separate
        # querySelectorAll pass per detector and so could quote a whole-page cost
        # for each; here the walk is shared, so the shared cost and each
        # detector's own filter are timed separately and reported as both.
        t0 = time.monotonic()
        rows = await detectors.survey(page)
        meta["timings"]["survey (shared DOM walk)"] = round((time.monotonic() - t0) * 1000, 1)
        seen = {r["probe"] for r in rows}
        meta["unobservable"] = sorted(set(probe_ids) - seen)

        for build in (
            detectors.d0_axcess_clickables,
            detectors.d2_inline_attribute,
            detectors.d2b_handler_property,
            detectors.d3_tabindex_aria,
            detectors.d4_css_lexical,
            detectors.d7_react_props,
        ):
            t0 = time.monotonic()
            result = build(rows)
            elapsed = round((time.monotonic() - t0) * 1000, 3)
            reported[result.detector] = result.reported(order)
            meta["proposed"][result.detector] = sorted(result.proposed)
            meta["timings"][result.detector] = elapsed
            if result.note:
                meta["notes"][result.detector] = result.note

        t0 = time.monotonic()
        d5 = await detectors.d5_cdp_listeners(page, cdp, probe_ids)
        cdp.require_success()
        meta["timings"][d5.detector] = round((time.monotonic() - t0) * 1000, 1)
        reported[d5.detector] = d5.reported(order)
        meta["proposed"][d5.detector] = sorted(d5.proposed)

        t0 = time.monotonic()
        d6 = await detectors.d6_listener_shim(page)
        meta["timings"][d6.detector] = round((time.monotonic() - t0) * 1000, 1)
        reported[d6.detector] = d6.reported(order)
        meta["proposed"][d6.detector] = sorted(d6.proposed)
        if d6.note:
            meta["notes"][d6.detector] = d6.note

        t0 = time.monotonic()
        d8 = await detectors.d8_hover_diff(page, probe_ids)
        meta["timings"][d8.detector] = round((time.monotonic() - t0) * 1000, 1)
        reported[d8.detector] = d8.reported(order)
        meta["proposed"][d8.detector] = sorted(d8.proposed)

        # --- D1: axe-core, the scanner axcess already ships ------------------
        t0 = time.monotonic()
        violations = await axe.run(page, level="AA")
        page.require_success()
        relevant = [v for v in violations if _is_keyboard_relevant(v)]
        meta["timings"]["D1 axe-core"] = round((time.monotonic() - t0) * 1000, 1)

        # Scored two ways on purpose. The difference between these rows is the
        # measurement artefact that nearly produced a headline contradicting
        # upstream's central result, and it is worth showing rather than
        # quietly resolving.
        reported["D1 axe-core (keyboard rules)"] = await _axe_probe_ids(page, relevant)
        reported["D1x axe-core (any rule, unsound)"] = await _axe_probe_ids(page, violations)
        for name in ("D1 axe-core (keyboard rules)", "D1x axe-core (any rule, unsound)"):
            meta["proposed"][name] = sorted(reported[name])

        fired = sorted({getattr(v, "rule_id", "?") for v in violations})
        meta["notes"]["D1 axe-core (keyboard rules)"] = (
            f"{len(violations)} violations, {len(relevant)} keyboard-relevant; "
            f"rules fired: {', '.join(fired[:8])}"
        )
        meta["notes"]["D1x axe-core (any rule, unsound)"] = (
            "credits axe for ANY violation on the element, including colour "
            "contrast and landmark structure. Shown to demonstrate the artefact, "
            "not as a result."
        )
        page.require_success()
    finally:
        async with asyncio.timeout(15):
            await context.close()

    return reported, order, meta


# Rules that actually assert something about operating or reaching a control.
# Everything else axe reports on an element -- colour contrast, landmark
# structure, document language -- says nothing about whether a keyboard can use
# it, and crediting those is how a general scanner is made to look like a
# keyboard detector.
KEYBOARD_RELEVANT_RULES = frozenset(
    {
        "scrollable-region-focusable",
        "aria-hidden-focus",
        "tabindex",
        "focus-order-semantics",
        "nested-interactive",
        "interactive-element-affordance",
        "accesskeys",
        "frame-focusable-content",
    }
)


def _is_keyboard_relevant(violation: Any) -> bool:
    """Whether an axe violation is about keyboard operability at all.

    Either it maps to a 2.1.x success criterion (Keyboard Accessible), or it is
    one of the named rules above that concern focusability and reachability.
    """
    sc = getattr(violation, "wcag_sc", None) or ""
    if sc.startswith("2.1"):
        return True
    return getattr(violation, "rule_id", "") in KEYBOARD_RELEVANT_RULES


async def _axe_probe_ids(page: Any, violations: list[Any]) -> set[str]:
    """Map axe violations back to probe ids, by **exact node identity only**.

    Credit requires the violating node to *be* the probe element. An earlier
    version also credited a violation whose node merely *contained* the probe,
    and the result was nonsense: axe reports ``html-has-lang`` against ``<html>``,
    which contains every probe on the page, so axe scored 100% recall on a rule
    about the document language. That would have inverted upstream's central
    finding — that a general scanner declines this defect class entirely — on the
    strength of a mapping artefact.

    Containment is never evidence here. "Some ancestor of this element has a
    problem" is not the same claim as "this control cannot be operated by
    keyboard".
    """
    selectors = [v.target_selector for v in violations if getattr(v, "target_selector", None)]
    if not selectors:
        return set()
    try:
        found: list[str] = await page.evaluate(
            """
            (selectors) => {
              const out = new Set();
              for (const sel of selectors) {
                let nodes = [];
                try { nodes = document.querySelectorAll(sel); } catch (e) { continue; }
                for (const n of nodes) {
                  // Exact identity only. No descendant walk: see the docstring.
                  const own = n.getAttribute && n.getAttribute('data-probe');
                  if (own) out.add(own);
                }
              }
              return Array.from(out);
            }
            """,
            selectors,
        )
        return set(found)
    except Exception as exc:
        raise RuntimeError("could not map axe evidence to probes") from exc


@dataclass
class CoveragePair:
    mouse: set[str] = field(default_factory=set)
    keyboard: set[str] = field(default_factory=set)
    uncertainties: dict[str, str] = field(default_factory=dict)

    baseline: set[str] = field(default_factory=set)

    @property
    def reported(self) -> bool:
        """D10a: the mouse ran something and the keyboard ran nothing at all."""
        return not self.uncertainties and bool(self.mouse) and not self.keyboard

    @property
    def reported_setdiff(self) -> bool:
        """D10b: the mouse ran something the keyboard never reached.

        Upstream's other formulation. It is strictly weaker than D10a's "ran
        nothing", and that is the point: an element the keyboard *reaches* runs
        focus code, so D10a goes quiet while the handler itself still never
        runs. This is the focusable-but-not-actionable case.
        """
        return not self.uncertainties and bool(self.mouse - self.keyboard)

    @property
    def reported_baselined(self) -> bool:
        """D10a with the page's handler-free baseline removed from both sides."""
        if self.uncertainties:
            return False
        mouse = self.mouse - self.baseline
        keyboard = self.keyboard - self.baseline
        return bool(mouse) and not keyboard

    def to_json(self) -> dict[str, Any]:
        return {
            "mouse_coverage": sorted(self.mouse),
            "enter_coverage": sorted(self.keyboard),
            "baseline_size": len(self.baseline),
            "mouse_not_keyboard": sorted(self.mouse - self.keyboard),
            "uncertainties": self.uncertainties,
        }


@dataclass
class UpstreamPass:
    """One probe measured the way upstream's D9 measured it."""

    mouse_changed: set[str] = field(default_factory=set)
    keyboard_changed: set[str] = field(default_factory=set)
    mouse_coverage: frozenset[str] = frozenset()
    keyboard_coverage: frozenset[str] = frozenset()
    in_tab_order: bool = False
    uncertainties: dict[str, str] = field(default_factory=dict)
    # Kept apart from `uncertainties` on purpose. A profiler that fails says
    # nothing about the channel measurement, so D9u can still be decided while
    # the coverage rules must abstain. Folding them together would either
    # discard a good channel reading or, worse, let an empty coverage set from a
    # failed read masquerade as "the keyboard ran nothing".
    coverage_uncertainties: dict[str, str] = field(default_factory=dict)

    @property
    def reported(self) -> bool:
        """Upstream's D9 rule: the mouse changed something and the keyboard did not."""
        return not self.uncertainties and bool(self.mouse_changed) and not self.keyboard_changed

    @property
    def coverage_is_trustworthy(self) -> bool:
        """No run-level and no coverage-level failure touched these sets."""
        return not self.uncertainties and not self.coverage_uncertainties

    @property
    def reported_coverage(self) -> bool:
        """Upstream's D10a rule, over the same sequential trial."""
        return (
            self.coverage_is_trustworthy
            and bool(self.mouse_coverage)
            and not self.keyboard_coverage
        )

    @property
    def reported_coverage_setdiff(self) -> bool:
        """Upstream's D10b rule, over the same sequential trial."""
        return self.coverage_is_trustworthy and bool(self.mouse_coverage - self.keyboard_coverage)

    def to_json(self) -> dict[str, Any]:
        """Publish the sets themselves, not just their sizes.

        A zero-dismissal result cannot be audited from counts alone, so the
        function identities that produced it are part of the record.
        """
        return {
            "mouse_changed": sorted(self.mouse_changed),
            "keyboard_changed": sorted(self.keyboard_changed),
            "mouse_coverage": sorted(self.mouse_coverage),
            "keyboard_coverage": sorted(self.keyboard_coverage),
            "in_tab_order": self.in_tab_order,
            "uncertainties": self.uncertainties,
            "coverage_uncertainties": self.coverage_uncertainties,
        }


@dataclass
class BehaviouralResult:
    d9: set[str] = field(default_factory=set)
    d10: set[str] = field(default_factory=set)
    d9_unknown: set[str] = field(default_factory=set)
    d10_unknown: set[str] = field(default_factory=set)
    d10b: set[str] = field(default_factory=set)
    d10base: set[str] = field(default_factory=set)
    d9u: set[str] = field(default_factory=set)
    d9u_unknown: set[str] = field(default_factory=set)
    d10a_u: set[str] = field(default_factory=set)
    d10b_u: set[str] = field(default_factory=set)
    d10u_unknown: set[str] = field(default_factory=set)
    baseline_evidence: dict[str, Any] = field(default_factory=dict)
    d9_nos4: set[str] = field(default_factory=set)
    d9_s4u: set[str] = field(default_factory=set)
    d9_s4u_unknown: set[str] = field(default_factory=set)
    s4u_dismissals: dict[str, str] = field(default_factory=dict)
    d9_nos4_unknown: set[str] = field(default_factory=set)
    d9_s4ours: set[str] = field(default_factory=set)
    d9_s4ours_unknown: set[str] = field(default_factory=set)
    s4ours_dismissals: dict[str, str] = field(default_factory=dict)
    s4_inputs: dict[str, Any] = field(default_factory=dict)
    coverage_errors: dict[str, str] = field(default_factory=dict)
    d9u_s4u: set[str] = field(default_factory=set)
    upstream_passes: dict[str, Any] = field(default_factory=dict)
    d9u_s4u_unknown: set[str] = field(default_factory=set)
    upstream_s4_dismissals: dict[str, str] = field(default_factory=dict)
    reasons: dict[str, str] = field(default_factory=dict)
    coverage: dict[str, dict[str, Any]] = field(default_factory=dict)
    upstream: dict[str, dict[str, Any]] = field(default_factory=dict)
    timings: dict[str, float] = field(default_factory=dict)


async def run_behavioural(
    factory: ContextFactory,
    page_path: str,
    probe_ids: list[str],
    order: TabOrder,
) -> BehaviouralResult:
    """D9 with its existing effect equivalence; D10a uses only Enter coverage.

    D10a neither subtracts a handler-free baseline nor applies Stage 4. It is
    the legacy coverage presence/absence detector, not an upstream replication.
    Each method retains its own measurement uncertainties.
    """
    config = TrialConfig(url=page_url(page_path), viewport="desktop")
    runner = DifferentialRunner(factory, config)
    result = BehaviouralResult()
    outcomes = []

    # Upstream subtracts a per-page handler-free baseline before comparing
    # coverage: click something with no handler, see what ran anyway, and
    # discount it. On a framework page that removes the scheduler and the
    # synthetic event system, which every click runs.
    upstream_baseline, baseline_note, baseline_failed = await _upstream_baseline(
        factory, config, BASE_URL
    )
    # One baseline concept for the whole file. The earlier corner-click at (2,2)
    # was not upstream's method and could miss a framework root's delegated
    # handlers, so the variant rows now subtract the same measured floor as the
    # ports and the two are directly comparable.
    baseline = upstream_baseline
    result.baseline_evidence = {
        "target": "#baseline-target",
        "functions": sorted(upstream_baseline),
        "note": baseline_note,
        "failed": baseline_failed,
    }
    upstream_passes: dict[str, UpstreamPass] = {}

    for probe_id in probe_ids:
        t0 = time.monotonic()
        try:
            async with asyncio.timeout(PROBE_TIMEOUT_SECONDS):
                outcomes.append(await runner.run_probe(probe_id, page_path, order))
        finally:
            # The shared differential may fail during setup before it can own
            # its context in a finally block. The factory tracks those too.
            async with asyncio.timeout(15):
                await factory.close_open_contexts()
        result.timings.setdefault(D9_NAME, 0.0)
        result.timings[D9_NAME] += (time.monotonic() - t0) * 1000

        t0 = time.monotonic()
        pair = await _coverage_pair(factory, config, probe_id, order)
        pair.baseline = set(baseline)
        result.timings.setdefault(D10_NAME, 0.0)
        result.timings[D10_NAME] += (time.monotonic() - t0) * 1000
        if pair.reported:
            result.d10.add(probe_id)
        if pair.reported_setdiff:
            result.d10b.add(probe_id)
        if pair.reported_baselined:
            result.d10base.add(probe_id)
        if baseline_failed:
            pair.uncertainties["baseline"] = baseline_note
        if pair.uncertainties:
            result.d10_unknown.add(probe_id)
        result.coverage[probe_id] = pair.to_json()

        t0 = time.monotonic()
        up = await _upstream_differential(
            factory, config, probe_id, order, BASE_URL, upstream_baseline
        )
        result.timings.setdefault(D9U_NAME, 0.0)
        result.timings[D9U_NAME] += (time.monotonic() - t0) * 1000
        if up.reported:
            result.d9u.add(probe_id)
        if baseline_failed:
            # No floor means no subtraction we can vouch for. The channel-based
            # D9u is unaffected; every coverage rule on this page abstains.
            up.coverage_uncertainties["baseline"] = baseline_note
        if up.reported_coverage:
            result.d10a_u.add(probe_id)
        if up.reported_coverage_setdiff:
            result.d10b_u.add(probe_id)
        if up.uncertainties:
            result.d9u_unknown.add(probe_id)
        if up.uncertainties or up.coverage_uncertainties:
            result.d10u_unknown.add(probe_id)
        result.upstream[probe_id] = up.to_json()
        upstream_passes[probe_id] = up

    confirmed, _ = apply_equivalence(outcomes)
    result.d9 = {o.probe_id for o in confirmed if o.verdict is Verdict.VIOLATION}
    result.d9_unknown = {o.probe_id for o in confirmed if o.verdict is Verdict.UNKNOWN}

    # ---- the Stage-4 ablation ------------------------------------------
    # Upstream's filter needs V8 coverage, which the production config does not
    # collect, so the page is measured once more with it armed. Every row of the
    # ablation is then derived from THAT ONE set of outcomes, so the three rows
    # really do differ only in the filter applied afterwards. Deriving the
    # no-filter row from the uninstrumented pass instead would have compared two
    # different measurements and called the difference a filter effect.
    t0 = time.monotonic()
    cov_outcomes, coverage_errors = await _coverage_armed_outcomes(
        factory, page_path, probe_ids, order, upstream_baseline
    )
    result.timings[D9_S4U_NAME] = round((time.monotonic() - t0) * 1000, 1)
    result.s4_inputs = {o.probe_id: _s4_record(o) for o in cov_outcomes}
    result.coverage_errors = coverage_errors

    # Which rows a failed *coverage* read can touch, and which it cannot. The
    # no-filter and payload rows compare observable effects and never read a
    # function set, so a broken profiler or a missing baseline is irrelevant to
    # them. Any unread set also compromises comparisons with that control as a
    # possible keyboard alternative, so this page's coverage-filter arm abstains
    # as a whole. This conservative failure policy is separate from upstream's
    # successful-measurement rule.
    coverage_blind = set(probe_ids) if coverage_errors or baseline_failed else set()

    result.d9_nos4 = {o.probe_id for o in cov_outcomes if o.verdict is Verdict.VIOLATION}
    result.d9_nos4_unknown = {o.probe_id for o in cov_outcomes if o.verdict is Verdict.UNKNOWN}

    confirmed_u, dismissed_u = (
        (cov_outcomes, [])
        if coverage_blind
        else apply_equivalence(cov_outcomes, strategy=by_coverage_exact)
    )
    result.d9_s4u = {o.probe_id for o in confirmed_u if o.verdict is Verdict.VIOLATION}
    # Its own trial-level unknowns first, then the coverage-blind probes on top.
    # An earlier version built the union before this line and had it silently
    # overwritten here, so a failed baseline reached the published scores as a
    # confident verdict.
    result.d9_s4u_unknown = {
        o.probe_id for o in confirmed_u if o.verdict is Verdict.UNKNOWN
    } | coverage_blind
    result.s4u_dismissals = {d.probe_id: d.dismissed_by for d in dismissed_u}

    # Upstream's Stage 4 searches the WHOLE corpus for an equivalent control,
    # not just the current page, so the passes are handed up and filtered once
    # after every page is measured. Our own filter is deliberately per-page --
    # a control on another page is not an alternative a user has -- and that
    # difference is one of the results, so the two must not be quietly aligned.
    result.upstream_passes = dict(upstream_passes)
    # This arm has its OWN measurements; an error in the independent ablation
    # must not contaminate it. Its global witness pool is guarded in main_async.
    result.d9u_s4u_unknown = set(result.d9u_unknown) | {
        pid for pid, up in upstream_passes.items() if up.coverage_uncertainties
    }

    confirmed_p, dismissed_p = apply_equivalence(cov_outcomes)
    result.d9_s4ours = {o.probe_id for o in confirmed_p if o.verdict is Verdict.VIOLATION}
    # Payload comparison: no coverage dependency, so `coverage_blind` is not
    # applied here and these verdicts stand.
    result.d9_s4ours_unknown = {o.probe_id for o in confirmed_p if o.verdict is Verdict.UNKNOWN}
    result.s4ours_dismissals = {d.probe_id: d.dismissed_by for d in dismissed_p}
    for outcome in confirmed:
        result.reasons[outcome.probe_id] = f"{outcome.verdict.value}: {outcome.reason}"
    return result


def _fixture_only(functions: frozenset[str]) -> frozenset[str]:
    """Executed functions belonging to the fixture, dropping harness noise."""
    return frozenset(f for f in functions if f.split("#", 1)[0].startswith(BASE_URL))


class _WatchedContext:
    """A browser context whose CDP sessions are checked for silent failures."""

    def __init__(self, context: Any, sessions: list[Any]) -> None:
        self._context = context
        self._sessions = sessions

    async def new_cdp_session(self, page: Any) -> Any:
        session = CheckedInstrument(await self._context.new_cdp_session(page))
        self._sessions.append(session)
        return session

    def __getattr__(self, name: str) -> Any:
        return getattr(self._context, name)


class CoverageSessionWatcher:
    """Wraps a context factory so a swallowed profiler error cannot pass as data.

    The shared differential arms coverage through helpers that suppress their
    own exceptions and return an empty set. An empty set is indistinguishable
    from "the keyboard ran nothing", which is a confident violation — so a
    broken profiler read could manufacture a finding, and the published sets
    could not reveal which read had failed.

    ``CheckedInstrument`` records the failure before the inner handler swallows
    it, so wrapping every session the runner is handed makes the failure
    visible without touching the production model. The errors are drained per
    probe, and only the rows that actually compare coverage abstain; the raw and
    payload rows keep their verdicts, because a profiler has nothing to do with
    an effect comparison.
    """

    def __init__(self, factory: Any) -> None:
        self._factory = factory
        self._sessions: list[Any] = []

    async def __call__(self) -> Any:
        return _WatchedContext(await self._factory(), self._sessions)

    async def close_open_contexts(self) -> None:
        await self._factory.close_open_contexts()

    def drain(self) -> list[str]:
        """Errors seen since the last drain, clearing the record."""
        errors = [error for session in self._sessions for error in session.errors]
        self._sessions.clear()
        return errors


def _s4_record(outcome: Any) -> dict[str, Any]:
    """The exact trial Stage 4 was computed from, function identities included.

    ``serialize_outcome`` publishes ``coverage_size`` only, which cannot settle
    whether two sets were equal — and set equality is the entire question here.
    Every list below is **after** fixture-origin filtering and **after**
    subtracting the page's handler-free baseline, which is published separately
    per page under ``baseline_evidence``.

    Failed reads are recorded separately under ``coverage_errors``. They can
    leave empty or partial sets and compromise both findings and alternative
    controls. The coverage-filter row therefore abstains for that page; these
    records remain available for diagnosis, not as successful measurements.
    """
    record = serialize_outcome(outcome)
    record["mouse_coverage"] = sorted(outcome.mouse.coverage)
    record["mouse_attempted"] = outcome.mouse.attempted
    record["keyboard_coverage"] = {
        key: sorted(result.coverage) for key, result in sorted(outcome.keyboard_by_key.items())
    }
    record["coverage_scope"] = "fixture-origin, baseline subtracted"
    return record


async def _coverage_armed_outcomes(
    factory: ContextFactory,
    page_path: str,
    probe_ids: list[str],
    order: TabOrder,
    baseline: frozenset[str] = frozenset(),
) -> tuple[list[Any], dict[str, str]]:
    """Re-measure one page with V8 coverage on, for upstream's Stage 4.

    Same oracle, same keys, same fresh context per trial — the only difference
    is that each :class:`ModalityResult` carries the executed-function set that
    ``by_coverage_exact`` needs.

    Returns the outcomes and, separately, the probes whose profiler reads
    failed. A probe that raises outright becomes an explicit UNKNOWN rather than
    disappearing; a probe whose *coverage* read failed keeps its effect-based
    verdict, because a broken profiler says nothing about what the page did —
    only the rows that compare coverage have to abstain on it.
    """
    config = TrialConfig(url=page_url(page_path), viewport="desktop", collect_coverage=True)
    watcher = CoverageSessionWatcher(factory)
    runner = DifferentialRunner(watcher, config)
    outcomes: list[Any] = []
    coverage_errors: dict[str, str] = {}

    def to_fixture_scripts(outcome: Any) -> Any:
        """Restrict every trial's coverage to fixture-origin scripts.

        Upstream filters inside ``takeCoverage``; doing it here yields the same
        sets without touching the shared differential. It is the difference
        between measuring the page and measuring the harness: unfiltered, one
        click on these fixtures records 87 executed functions of which 85 have
        an empty URL. Two modalities drive the browser differently, so those 85
        never agree, and an equivalence test over them can only ever say no.
        """

        def clean(functions: frozenset[str]) -> frozenset[str]:
            return _fixture_only(functions) - baseline

        return replace(
            outcome,
            mouse=replace(outcome.mouse, coverage=clean(outcome.mouse.coverage)),
            keyboard_by_key={
                key: replace(result, coverage=clean(result.coverage))
                for key, result in outcome.keyboard_by_key.items()
            },
        )

    for probe_id in probe_ids:
        watcher.drain()
        try:
            async with asyncio.timeout(PROBE_TIMEOUT_SECONDS):
                outcomes.append(
                    to_fixture_scripts(await runner.run_probe(probe_id, page_path, order))
                )
        except Exception as exc:
            # A failed trial must stay in the denominator as UNKNOWN. Dropping
            # it silently turned a missing positive into a false negative and a
            # missing negative into a true negative -- the exact collapse of
            # "could not measure" into a verdict that this experiment exists to
            # refuse.
            log.debug("bakeoff.s4u_probe_failed", probe=probe_id, error=str(exc)[:200])
            outcomes.append(
                unknown_outcome(
                    probe_id, page_path, "desktop", f"coverage-armed trial raised: {exc}"[:200]
                )
            )
        finally:
            failures = watcher.drain()
            if failures:
                coverage_errors[probe_id] = failures[0]
            async with asyncio.timeout(15):
                await factory.close_open_contexts()
    return outcomes, coverage_errors


# Upstream's measured waits, from their differential.ts. Ours differ (250 ms
# settle, no inter-key gap because each key gets a fresh page), so the port has
# to carry theirs or it is not their detector.
UPSTREAM_SETTLE_MS = 200
UPSTREAM_KEY_GAP_MS = 120
UPSTREAM_KEYS = ("Enter", "Space", "ArrowDown")

_PROBE_ATTR = "data-probe"


async def _upstream_baseline(
    factory: ContextFactory, config: TrialConfig, origin: str
) -> tuple[frozenset[str], str, bool]:
    """Upstream's per-page coverage floor: click ``#baseline-target``.

    Returns the functions, a note, and whether the measurement *failed*. Three
    outcomes have to stay distinguishable, and a bare size cannot tell them
    apart:

    * **measured** — the target was there and the click was observed.
    * **absent** — the page carries no ``#baseline-target``, so an empty floor
      is the correct answer. Upstream does the same: no box, empty set. Our ten
      holdout pages are in this case, being our fixtures rather than theirs.
    * **failed** — the target exists but we could not read it. That is not a
      baseline of zero; it is no baseline, and every coverage rule on the page
      has to abstain rather than subtract nothing and score on confidently.
    """
    context = None
    try:
        async with asyncio.timeout(PROBE_TIMEOUT_SECONDS):
            context = await factory()
            page = await context.new_page()
            cdp: Any = CheckedInstrument(await context.new_cdp_session(page))
            await page.goto(config.url, wait_until="load")
            target = page.locator("#baseline-target").first
            if await page.locator("#baseline-target").count() == 0:
                return frozenset(), "absent: no #baseline-target on this page", False
            box = await target.bounding_box(timeout=1000)
            await detectors.start_coverage(cdp)
            await coverage.take(cdp, origin)
            if cdp.errors:
                return frozenset(), f"failed: profiler: {cdp.errors[0]}"[:200], True
            if box is None:
                return frozenset(), "absent: #baseline-target has no rendered box", False
            await page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
            await page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
            await page.wait_for_timeout(UPSTREAM_SETTLE_MS)
            measured = frozenset(await coverage.take(cdp, origin))
            if cdp.errors:
                return frozenset(), f"failed: profiler: {cdp.errors[0]}"[:200], True
            return measured, "measured", False
    except Exception as exc:
        return frozenset(), f"failed: {type(exc).__name__}: {exc}"[:200], True
    finally:
        try:
            if context is not None:
                async with asyncio.timeout(15):
                    await context.close()
        finally:
            async with asyncio.timeout(15):
                await factory.close_open_contexts()


async def _pierced_centre(cdp: Any, probe_id: str) -> tuple[tuple[float, float] | None, str | None]:
    """Upstream's target resolution: the pierced CDP tree, then the box model.

    ``DOM.getDocument`` with ``pierce`` walks shadow roots — closed ones
    included — and frame content documents, which a Playwright locator cannot
    reach. Returns the centre of the border box, or a reason it has none.
    """
    try:
        doc = await cdp.send("DOM.getDocument", {"depth": -1, "pierce": True})
    except Exception as exc:
        return None, f"pierced tree unavailable: {type(exc).__name__}"

    found: list[int] = []

    def walk(node: dict[str, Any]) -> None:
        if found:
            return
        attrs = node.get("attributes") or []
        for i in range(0, len(attrs) - 1, 2):
            if attrs[i] == _PROBE_ATTR and attrs[i + 1] == probe_id:
                found.append(node["nodeId"])
                return
        for key in ("children", "shadowRoots"):
            for child in node.get(key) or []:
                walk(child)
        for key in ("contentDocument", "templateContent"):
            child = node.get(key)
            if child:
                walk(child)

    walk(doc.get("root", {}))
    if not found:
        return None, "probe not present in the pierced DOM tree"
    try:
        model = await cdp.send("DOM.getBoxModel", {"nodeId": found[0]})
    except Exception:
        return None, "no rendered box (display:none / zero-size)"
    border = (model.get("model") or {}).get("border") or []
    if len(border) < 8:
        return None, "no rendered box (display:none / zero-size)"
    width = model["model"].get("width") or 0
    height = model["model"].get("height") or 0
    if width == 0 or height == 0:
        return None, "no rendered box (display:none / zero-size)"
    xs = border[0::2]
    ys = border[1::2]
    return ((sum(xs) / 4.0, sum(ys) / 4.0), None)


async def _park_mouse(page: Any) -> None:
    """Upstream parks the pointer so a stale ``:hover`` never leaks into a probe."""
    viewport = page.viewport_size or {"width": 1280, "height": 900}
    await page.mouse.move(viewport["width"] - 2, viewport["height"] - 2)


async def _frame_snapshot(page: Any) -> tuple[dict[str, Any], list[str]]:
    """Snapshot every frame, keyed by URL, as upstream does.

    A clickable element inside an iframe mutates that frame's document, which a
    top-level snapshot cannot see at all. Upstream recorded this as the reason
    one probe scored a false negative in their first run, and reading only the
    top document is one of the ways our earlier D9u was not their detector.
    """
    out: dict[str, Any] = {}
    failures: list[str] = []
    for frame in page.frames:
        try:
            state = await frame.evaluate(UPSTREAM_SNAPSHOT_CALL)
        except Exception as exc:
            # Never swallowed. A snapshot that raises produced no channels, and
            # "no channels changed" is a verdict; the caller must abstain
            # instead. A JS SyntaxError here once silently reported every frame
            # as inert across an entire run.
            failures.append(f"{frame.url}: {type(exc).__name__}: {exc}"[:200])
            continue
        if state is None:
            failures.append(f"{frame.url}: __a11y absent, init script did not run")
            continue
        out[frame.url] = state
    return out, failures


def upstream_frame_delta(before: dict[str, Any], after: dict[str, Any]) -> set[str]:
    """Union of per-frame channel deltas, by upstream's presence test.

    A frame that appears or disappears between the two reads counts as ``nav``,
    which is upstream's rule and not merely a convenience.
    """
    changed: set[str] = set()
    for key in set(before) | set(after):
        b, a = before.get(key), after.get(key)
        if not b or not a:
            changed.add("nav")
            continue
        changed |= upstream_delta(b, a)
    return changed


def upstream_stage4(passes: dict[str, UpstreamPass]) -> tuple[set[str], dict[str, str]]:
    """Upstream's Stage 4, applied to upstream's own findings.

    This is the missing half of the 1:1 port. Their ``stage4`` filters the set
    their D9 confirmed, using their channel signatures and their coverage sets;
    our ``D9+S4u`` row instead applied their *signal* to *our* differential's
    findings, which isolates the filter but is not their pipeline. Both are now
    reported, and only this one is a replication.

    Transcribed from ``tests/tabbing-experiment.spec.ts``:

        confirmed        = probes where the mouse changed something and the
                           keyboard changed nothing
        keyboardReachable = probes in the tab order whose keyboard changed
                           something
        keep a finding unless some reachable probe has the identical channel
        signature and an exactly equal executed-function set; a finding with no
        mouse coverage, or a candidate with no keyboard coverage, is skipped
    """
    confirmed = [pid for pid, up in passes.items() if up.reported]
    if any(up.coverage_uncertainties for up in passes.values()):
        # A failed witness can affect another finding anywhere in this global
        # pool. Preserve the raw leads for diagnosis; main_async abstains on the
        # filtered row instead of treating this as a successful no-match.
        return set(confirmed), {}
    reachable = [
        (pid, up)
        for pid, up in passes.items()
        if up.in_tab_order and up.keyboard_changed and up.coverage_is_trustworthy
    ]
    kept: set[str] = set()
    dismissed: dict[str, str] = {}
    for pid in confirmed:
        finding = passes[pid]
        if not finding.mouse_coverage:
            kept.add(pid)
            continue
        signature = ",".join(sorted(finding.mouse_changed))
        match = None
        for candidate_id, candidate in reachable:
            if candidate_id == pid or not candidate.keyboard_coverage:
                continue
            if ",".join(sorted(candidate.keyboard_changed)) != signature:
                continue
            # Jaccard at threshold 1.0 is exactly set equality, and both sets
            # are known non-empty here.
            if candidate.keyboard_coverage == finding.mouse_coverage:
                match = candidate_id
                break
        if match is None:
            kept.add(pid)
        else:
            dismissed[pid] = match
    return kept, dismissed


async def _upstream_differential(
    factory: ContextFactory,
    config: TrialConfig,
    probe_id: str,
    order: TabOrder,
    origin: str,
    baseline: frozenset[str],
) -> UpstreamPass:
    """One probe measured the way upstream's ``runDifferential`` measures it.

    Faithful to their procedure, including the parts we consider defects,
    because reproducing them is the whole point of this row:

    * **One page, reloaded between modalities** — not a fresh context. Their
      storage-contamination bug lives here, and giving each modality its own
      context silently removes it.
    * **Every frame is observed**, not just the top document.
    * **All three keys in sequence against one page state**, 120 ms apart, so a
      control that opens on Enter and closes on Space nets to no change.
    * **The keyboard baseline is taken before the Tab walk**, so every focus
      side effect of every element passed on the way is attributed to this probe.
    * **Presence, not payload**: any change on a channel counts, so an unrelated
      console line from the keypress clears a real finding.
    * 200 ms settle, pointer parked before each pass, target resolved through
      the pierced tree.
    """
    result = UpstreamPass()
    position = order.position(probe_id)
    in_tab_order = position is not None
    context = None
    try:
        async with asyncio.timeout(PROBE_TIMEOUT_SECONDS):
            context = await factory()
            # Their instrument, not ours: the ported rows must observe what
            # their detector observed.
            await context.add_init_script(UPSTREAM_INIT_JS)
            page = await context.new_page()
            cdp: Any = CheckedInstrument(await context.new_cdp_session(page))

            # ---- mouse -------------------------------------------------
            await page.goto(config.url, wait_until="load")
            await _park_mouse(page)
            await page.wait_for_timeout(80)
            centre, reason = await _pierced_centre(cdp, probe_id)
            # Resolution failures already have their own mouse uncertainty.
            # In particular a normal no-box error must not leak into the next
            # keyboard profiler read and invalidate a global Stage-4 pool.
            cdp.errors.clear()
            viewport = page.viewport_size or {"width": 1280, "height": 900}
            if centre is None:
                result.uncertainties["mouse"] = reason or "unresolved"
            elif not (0 <= centre[0] <= viewport["width"] and 0 <= centre[1] <= viewport["height"]):
                result.uncertainties["mouse"] = "outside the viewport"
            else:
                # `coverage.start`/`take` swallow profiler errors and return an
                # empty set. Unguarded, a failed read is indistinguishable from
                # "the keyboard ran nothing", which is a confident violation.
                await detectors.start_coverage(cdp)
                await coverage.take(cdp, origin)
                if cdp.errors:
                    result.coverage_uncertainties["mouse"] = f"profiler: {cdp.errors[0]}"[:200]
                    cdp.errors.clear()
                before, before_fail = await _frame_snapshot(page)
                await page.mouse.move(centre[0], centre[1])
                await page.wait_for_timeout(UPSTREAM_SETTLE_MS)
                await page.mouse.click(centre[0], centre[1], delay=20)
                await page.wait_for_timeout(UPSTREAM_SETTLE_MS)
                after, after_fail = await _frame_snapshot(page)
                if before_fail or after_fail:
                    result.uncertainties["mouse"] = f"snapshot: {(before_fail + after_fail)[0]}"
                result.mouse_changed = upstream_frame_delta(before, after)
                result.mouse_coverage = frozenset(await coverage.take(cdp, origin)) - baseline
                if cdp.errors:
                    result.coverage_uncertainties["mouse"] = f"profiler: {cdp.errors[0]}"[:200]
                    cdp.errors.clear()

            # ---- keyboard, on the SAME page after a full reload ---------
            await page.goto(config.url, wait_until="load")
            await _park_mouse(page)
            await page.wait_for_timeout(80)
            await detectors.start_coverage(cdp)
            await coverage.take(cdp, origin)
            if cdp.errors:
                result.coverage_uncertainties["keyboard"] = f"profiler: {cdp.errors[0]}"[:200]
                cdp.errors.clear()
            kb_before, kb_before_fail = await _frame_snapshot(page)
            if in_tab_order:
                await page.evaluate("() => document.activeElement && document.activeElement.blur()")
                for _ in range(position or 0):
                    await page.keyboard.press("Tab")
                await page.wait_for_timeout(UPSTREAM_SETTLE_MS)
                for key in UPSTREAM_KEYS:
                    await page.keyboard.press(key)
                    await page.wait_for_timeout(UPSTREAM_KEY_GAP_MS)
            await page.wait_for_timeout(UPSTREAM_SETTLE_MS)
            kb_after, kb_after_fail = await _frame_snapshot(page)
            if kb_before_fail or kb_after_fail:
                result.uncertainties["keyboard"] = (
                    f"snapshot: {(kb_before_fail + kb_after_fail)[0]}"
                )
            result.keyboard_changed = upstream_frame_delta(kb_before, kb_after)
            result.keyboard_coverage = frozenset(await coverage.take(cdp, origin)) - baseline
            if cdp.errors:
                result.coverage_uncertainties["keyboard"] = f"profiler: {cdp.errors[0]}"[:200]
                cdp.errors.clear()
            result.in_tab_order = in_tab_order
    except Exception as exc:
        result.uncertainties["run"] = f"{type(exc).__name__}: {exc}"[:240]
    finally:
        try:
            if context is not None:
                async with asyncio.timeout(15):
                    await context.close()
        finally:
            async with asyncio.timeout(15):
                await factory.close_open_contexts()
    return result


async def _coverage_pair(
    factory: ContextFactory, config: TrialConfig, probe_id: str, order: TabOrder
) -> CoveragePair:
    """Measure both modalities without conflating failed reads with empty sets."""
    pair = CoveragePair()
    position = order.position(probe_id)
    if position is None and order.capped:
        pair.uncertainties["keyboard"] = "tab_cap: probe not reached before traversal cap"

    for modality in ("mouse", "keyboard"):
        if modality == "keyboard" and position is None:
            continue
        context = None
        try:
            async with asyncio.timeout(PROBE_TIMEOUT_SECONDS):
                context = await factory()
                page = await context.new_page()
                cdp: Any = CheckedInstrument(await context.new_cdp_session(page))
                await page.goto(config.url, wait_until="load")
                await detectors.start_coverage(cdp)
                cdp.require_success()
                # Reset the profiler after load; this is not a measured
                # handler-free baseline subtraction.
                await detectors.take_coverage(cdp)
                cdp.require_success()
                locator = page.locator(f'[data-probe="{probe_id}"]').first
                if modality == "mouse":
                    box = await locator.bounding_box(timeout=1000)
                    if not box or box["width"] <= 0 or box["height"] <= 0:
                        pair.uncertainties[modality] = "not_rendered: probe has no visible box"
                        continue
                    x, y = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
                    viewport = page.viewport_size
                    if viewport is None or not (
                        0 <= x < viewport["width"] and 0 <= y < viewport["height"]
                    ):
                        pair.uncertainties[modality] = "not_rendered: click point outside viewport"
                        continue
                    await page.mouse.click(x, y)
                else:
                    if position is None:
                        raise RuntimeError("missing tab position")
                    for _ in range(position):
                        await page.keyboard.press("Tab")
                    if not await locator.evaluate("el => el.getRootNode().activeElement === el"):
                        pair.uncertainties[modality] = "unresolved: tab replay did not reach probe"
                        continue
                    await page.keyboard.press("Enter")
                await page.wait_for_timeout(200)
                executed = await detectors.take_coverage(cdp)
                cdp.require_success()
                if modality == "mouse":
                    pair.mouse = executed
                else:
                    pair.keyboard = executed
        except Exception as exc:
            pair.uncertainties[modality] = f"{type(exc).__name__}: {exc}"[:240]
        finally:
            try:
                if context is not None:
                    async with asyncio.timeout(15):
                        await context.close()
            finally:
                async with asyncio.timeout(15):
                    await factory.close_open_contexts()
    return pair


def to_outcome_stub(probe_id: str, reported: set[str], unknown: set[str]) -> Any:
    """Adapt a detector's id set to what :func:`score_outcomes` expects.

    Three-valued, not two. A probe the detector could not observe is UNKNOWN and
    counts against strict recall; it is not silently a negative.
    """
    from audit.analyzer.keyboard.kbdiff.model import Effect, ModalityResult, ProbeOutcome

    if probe_id in unknown:
        verdict = Verdict.UNKNOWN
    else:
        verdict = Verdict.VIOLATION if probe_id in reported else Verdict.NO_LEAD
    return ProbeOutcome(
        probe_id=probe_id,
        page="",
        viewport="desktop",
        in_tab_order=False,
        tab_index=None,
        mouse=ModalityResult(attempted=True, effect=Effect()),
        keyboard_by_key={},
        verdict=verdict,
        uncertainty=Uncertainty.UNSUPPORTED if verdict is Verdict.UNKNOWN else None,
    )


def score_methods(
    labels: dict[str, str],
    reported: dict[str, set[str]],
    unknown: dict[str, set[str]],
    corpus: str,
) -> list[Score]:
    """Every method has the full truth denominator, including unknown targets."""
    scores = []
    for name, ids in reported.items():
        undecided = unknown.get(name, set())
        if (ids | undecided) - labels.keys():
            raise ValueError(f"{name} returned probes outside the selected corpus")
        outcomes = [to_outcome_stub(pid, ids, undecided) for pid in labels]
        score = score_outcomes(outcomes, labels, detector=name, cohort=corpus, viewport="desktop")
        check_invariant(score, len(labels))
        scores.append(score)
    return scores


async def main_async(args: argparse.Namespace) -> int:
    root, truth_name, caveat = CORPORA[args.corpus]
    label = safe_label(args.label) if args.label else None
    out_dir = Path(args.out) if args.out else root / "results"
    suffix = f"-{label}" if label else ""
    out_path = out_dir / f"bakeoff-{args.corpus}{suffix}.json"
    try:
        require_new_outputs(out_path)
        fixture_hash = corpus_fingerprint(root, args.corpus)
        pages, labels = load_truth(root, truth_name)
    except (OSError, RuntimeError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"corpus: {args.corpus}  ({len(labels)} probes, {len(pages)} pages)")
    print(f"caveat: {caveat}\n")

    behavioural = [
        D9_NAME,
        D9_NOS4_NAME,
        D9_S4U_NAME,
        D9_S4OURS_NAME,
        D9U_NAME,
        D9U_S4U_NAME,
        D10A_U_NAME,
        D10B_U_NAME,
        D10_NAME,
        D10B_NAME,
        D10BASE_NAME,
    ]
    candidate_study = getattr(args, "candidate_study", False)
    candidate_methods = (
        [*candidate_analysis.UPSTREAM_NAMES.values(), *candidate_analysis.VARIANT_NAMES]
        if candidate_study
        else []
    )
    methods = [*CHEAP_METHODS, *candidate_methods, *([] if args.cheap_only else behavioural)]
    all_reported: dict[str, set[str]] = {name: set() for name in methods}
    all_unknown: dict[str, set[str]] = {name: set() for name in methods}
    all_proposed: dict[str, set[str]] = {
        name: set() for name in [*CHEAP_METHODS, *candidate_methods]
    }
    candidate_evidence: dict[str, Any] = {}
    reasons: dict[str, str] = {}
    coverage: dict[str, dict[str, Any]] = {}
    upstream_evidence: dict[str, dict[str, Any]] = {}
    s4u_dismissals: dict[str, str] = {}
    s4ours_dismissals: dict[str, str] = {}
    upstream_s4_dismissals: dict[str, str] = {}
    all_upstream_passes: dict[str, Any] = {}
    coverage_errors: dict[str, str] = {}
    s4_inputs: dict[str, Any] = {}
    baseline_evidence: dict[str, Any] = {}
    notes: dict[str, str] = {}
    tab_info: dict[str, Any] = {}
    actual_viewports: dict[str, dict[str, int]] = {}
    page_timings: dict[str, Any] = {}
    errors: list[str] = []
    factory = None
    browser_version = None
    source_before = source_sha256()
    started_utc = datetime.now(UTC).isoformat()
    started = time.monotonic()
    try:
        async with asyncio.timeout(args.timeout_seconds):
            axe = AxeAnalyzer.from_bundled()
            candidate_axe_source = detectors.AXE_BUNDLE.read_text() if candidate_study else ""

            async def candidate_axe(page: Any) -> set[str]:
                return await upstream_candidates.d1_axe(page, candidate_axe_source)

            async with async_playwright() as pw:
                browser = await pw.chromium.launch(headless=True)
                browser_version = browser.version
                try:
                    factory = ContextFactory(browser, VIEWPORT, root)
                    for page_path, probe_ids in sorted(pages.items()):
                        print(f"  {page_path} ({len(probe_ids)} probes) ...", flush=True)
                        async with asyncio.timeout(PAGE_TIMEOUT_SECONDS):
                            reported, order, meta = await run_page(
                                factory, root, page_path, probe_ids, axe
                            )
                        if set(reported) != set(CHEAP_METHODS):
                            raise RuntimeError(f"incomplete detector results on {page_path}")
                        if set(meta.get("proposed", {})) != set(CHEAP_METHODS):
                            raise RuntimeError(f"incomplete candidate proposals on {page_path}")
                        if meta["viewport"] != VIEWPORT:
                            raise RuntimeError(f"unexpected viewport on {page_path}")
                        actual_viewports[page_path] = meta["viewport"]
                        page_timings[page_path] = meta["timings"]
                        unobservable = set(meta.get("unobservable", []))
                        capped = {
                            pid for pid in probe_ids if not order.reachability_is_certain(pid)
                        }
                        for name, ids in reported.items():
                            if ids - set(probe_ids):
                                raise RuntimeError(f"{name} returned a probe outside {page_path}")
                            all_reported[name].update(ids)
                            proposals = set(meta["proposed"][name])
                            if proposals - set(probe_ids):
                                raise RuntimeError(f"{name} proposed a probe outside {page_path}")
                            all_proposed[name].update(proposals)
                            all_unknown[name].update(unobservable)
                            if not name.startswith("D1 ") and not name.startswith("D1x "):
                                all_unknown[name].update(capped)
                        notes.update(meta["notes"])
                        tab_info[page_path] = {
                            "presses": order.presses,
                            "capped": order.capped,
                            "index": order.index,
                        }

                        if candidate_study:
                            async with asyncio.timeout(PAGE_TIMEOUT_SECONDS):
                                study = await candidate_analysis.measure_candidate_page(
                                    factory, page_path, probe_ids, candidate_axe
                                )
                            if set(study.reported) != set(candidate_methods):
                                raise RuntimeError(f"incomplete candidate study on {page_path}")
                            for name in candidate_methods:
                                proposals = study.proposed[name]
                                ids = study.reported[name]
                                unknown = study.unknown[name]
                                if (proposals | ids | unknown) - set(probe_ids):
                                    raise RuntimeError(
                                        f"{name} returned a probe outside {page_path}"
                                    )
                                all_proposed[name].update(proposals)
                                all_reported[name].update(ids)
                                all_unknown[name].update(unknown)
                            candidate_evidence[page_path] = study.evidence
                            page_timings[page_path].update(study.timings)

                        if not args.cheap_only:
                            result = await run_behavioural(factory, page_path, probe_ids, order)
                            all_reported[D9_NAME].update(result.d9)
                            all_reported[D9_NOS4_NAME].update(result.d9_nos4)
                            all_reported[D9_S4U_NAME].update(result.d9_s4u)
                            all_reported[D9_S4OURS_NAME].update(result.d9_s4ours)
                            all_reported[D9U_NAME].update(result.d9u)
                            all_upstream_passes.update(result.upstream_passes)
                            all_reported[D10A_U_NAME].update(result.d10a_u)
                            all_reported[D10B_U_NAME].update(result.d10b_u)
                            all_reported[D10_NAME].update(result.d10)
                            all_reported[D10B_NAME].update(result.d10b)
                            all_reported[D10BASE_NAME].update(result.d10base)
                            all_unknown[D9_NAME].update(result.d9_unknown)
                            all_unknown[D9_NOS4_NAME].update(result.d9_nos4_unknown)
                            all_unknown[D9_S4U_NAME].update(result.d9_s4u_unknown)
                            all_unknown[D9_S4OURS_NAME].update(result.d9_s4ours_unknown)
                            s4ours_dismissals.update(result.s4ours_dismissals)
                            s4_inputs.update(result.s4_inputs)
                            coverage_errors.update(result.coverage_errors)
                            all_unknown[D9U_NAME].update(result.d9u_unknown)
                            all_unknown[D9U_S4U_NAME].update(result.d9u_s4u_unknown)
                            for name in (D10A_U_NAME, D10B_U_NAME):
                                all_unknown[name].update(result.d10u_unknown)
                            baseline_evidence[page_path] = result.baseline_evidence
                            s4u_dismissals.update(result.s4u_dismissals)
                            for name in (D10_NAME, D10B_NAME, D10BASE_NAME):
                                all_unknown[name].update(result.d10_unknown)
                            reasons.update(result.reasons)
                            coverage.update(result.coverage)
                            upstream_evidence.update(result.upstream)
                            for name, ms in result.timings.items():
                                page_timings[page_path][name] = round(ms, 1)
                finally:
                    try:
                        if factory is not None:
                            async with asyncio.timeout(15):
                                await factory.close_open_contexts()
                    finally:
                        async with asyncio.timeout(15):
                            await browser.close()
    except Exception as exc:
        errors.append(f"{type(exc).__name__}: {exc}"[:500])

    source_after = source_sha256()
    source_unchanged = source_before == source_after
    if not source_unchanged:
        errors.append("detector or runner source changed during measurement; scores suppressed")
    fixture_hash_after = None
    try:
        fixture_hash_after = corpus_fingerprint(root, args.corpus)
        if fixture_hash_after != fixture_hash:
            errors.append("corpus inputs changed during measurement; scores suppressed")
    except (OSError, RuntimeError, ValueError) as exc:
        errors.append(f"corpus verification after measurement failed: {exc}"[:500])
    # Upstream's Stage 4, applied once over the whole corpus as theirs is --
    # and necessarily BEFORE scoring, since it decides that row's reported set.
    if all_upstream_passes:
        kept_u, upstream_s4_dismissals = upstream_stage4(all_upstream_passes)
        if any(up.coverage_uncertainties for up in all_upstream_passes.values()):
            all_unknown[D9U_S4U_NAME].update(all_upstream_passes)
        all_reported[D9U_S4U_NAME].update(kept_u)

    scores = []
    if not errors:
        try:
            scores = score_methods(labels, all_reported, all_unknown, args.corpus)
        except (ValueError, AssertionError) as exc:
            errors.append(f"invalid measurements; scores suppressed: {exc}"[:500])
    finished_utc = datetime.now(UTC).isoformat()
    wall_seconds = round(time.monotonic() - started, 1)
    counters = (
        dict(factory.totals)
        if factory is not None
        else {"served": 0, "ping": 0, "blocked": 0, "missing": 0, "websocket": 0}
    )
    payload = {
        "run": {
            "label": label,
            "started_utc": started_utc,
            "finished_utc": finished_utc,
            "wall_seconds": wall_seconds,
            "command": list(sys.argv),
            "valid": not errors,
            "errors": errors,
            "corpus_sha256": fixture_hash,
            "corpus_sha256_after": fixture_hash_after,
            "source_sha256_before": source_before,
            "source_sha256_after": source_after,
            "source_unchanged": source_unchanged,
            "versions": {
                "python": platform.python_version(),
                "playwright": version("playwright"),
                "chromium": browser_version,
            },
            "settings": {
                "viewport_name": "desktop",
                "viewport": VIEWPORT,
                "headless": True,
                "cheap_only": args.cheap_only,
                "candidate_study": candidate_study,
                "timeout_seconds": args.timeout_seconds,
                "page_timeout_seconds": PAGE_TIMEOUT_SECONDS,
                "probe_timeout_seconds": PROBE_TIMEOUT_SECONDS,
            },
            "actual_viewports": actual_viewports,
            "request_counters": counters,
        },
        "corpus": args.corpus,
        "caveat": caveat,
        "probes": len(labels),
        "positives": sum(1 for v in labels.values() if v == "violation"),
        "wall_seconds": wall_seconds,
        "tab_orders": tab_info,
        "page_timings_ms": page_timings,
        "notes": notes,
        "reasons": reasons,
        "coverage_evidence": coverage,
        "upstream_evidence": upstream_evidence,
        "s4u_dismissals": s4u_dismissals,
        "s4ours_dismissals": s4ours_dismissals,
        "upstream_s4_dismissals": upstream_s4_dismissals,
        # Probes whose profiler read failed. The coverage rows abstain on
        # these; the effect-based rows do not, and this names which is which.
        "coverage_errors": coverage_errors,
        # The exact trials the Stage-4 rows were computed from, so a
        # dismissal or its absence can be reconstructed from this file.
        "s4_inputs": s4_inputs,
        "baseline_evidence": baseline_evidence,
        "proposed": {name: sorted(ids) for name, ids in all_proposed.items()},
        "proposal_coverage": {
            name: {
                "candidates": len(ids),
                "positive_candidates": sum(labels[pid] == "violation" for pid in ids),
                "positive_total": sum(label == "violation" for label in labels.values()),
                "missing_positive_candidates": sorted(
                    pid for pid, label in labels.items() if label == "violation" and pid not in ids
                ),
            }
            for name, ids in all_proposed.items()
        },
        "candidate_evidence": candidate_evidence,
        "candidate_study_caveat": (
            "Rules designed after inspecting this corpus's errors: development evaluation, "
            "not an unseen holdout. Raw proposals measure shortlist coverage, not violations."
            if candidate_study
            else None
        ),
        "reported": {k: sorted(v) for k, v in all_reported.items()},
        "unobservable": {k: sorted(v) for k, v in all_unknown.items() if v},
        "scores": [s.to_json() for s in scores],
    }
    try:
        write_new(out_path, json.dumps(payload, indent=2) + "\n")
    except FileExistsError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if errors:
        print("Scores suppressed: " + "; ".join(errors), file=sys.stderr)
    else:
        print(
            f"\n{'detector':36} {'TP':>3} {'FP':>3} {'FN':>3} {'unk':>4} "
            f"{'prec':>7} {'recall':>7} {'F1':>7}"
        )
        print("-" * 84)
        for score in scores:

            def pct(value: float | None) -> str:
                return "  —  " if value is None else f"{value * 100:5.1f}%"

            print(
                f"{score.detector:36} {score.tp:>3} {score.fp:>3} {score.fn:>3} "
                f"{score.unknown:>4} {pct(score.precision):>7} "
                f"{pct(score.recall):>7} {pct(score.f1):>7}"
            )
    print(f"\nwrote {out_path}  ({wall_seconds}s)")
    return 1 if errors else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", choices=sorted(CORPORA), default="edgecases")
    parser.add_argument(
        "--label", type=safe_label, help="name a new run; existing output is preserved"
    )
    parser.add_argument("--out", help="output directory (default: selected corpus/results)")
    parser.add_argument(
        "--timeout-seconds",
        type=bounded_int(1, 14_400),
        default=3600,
        help="overall measurement deadline (default: 3600 seconds)",
    )
    parser.add_argument(
        "--candidate-study",
        action="store_true",
        help="also measure the upstream candidate rules and predeclared cheap-detector variants",
    )
    parser.add_argument(
        "--cheap-only",
        action="store_true",
        help="skip D9/D10a behavioural and coverage measurements",
    )
    return asyncio.run(main_async(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
