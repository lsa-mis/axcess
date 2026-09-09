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
from dataclasses import dataclass, field
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
from audit.analyzer.keyboard.kbdiff import channels, detectors  # noqa: E402
from audit.analyzer.keyboard.kbdiff.differential import (  # noqa: E402
    DifferentialRunner,
    TrialConfig,
)
from audit.analyzer.keyboard.kbdiff.equivalence import apply_equivalence  # noqa: E402
from audit.analyzer.keyboard.kbdiff.model import Uncertainty, Verdict  # noqa: E402
from audit.analyzer.keyboard.kbdiff.score import (  # noqa: E402
    Score,
    check_invariant,
    score_outcomes,
)
from audit.analyzer.keyboard.kbdiff.taborder import TabOrder, compute_tab_order  # noqa: E402
from audit.logging import get_logger  # noqa: E402
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
from experiments.tabbing.runner.serve import ContextFactory, page_url  # noqa: E402

log = get_logger(__name__)

VIEWPORT = {"width": 1280, "height": 900}
PAGE_TIMEOUT_SECONDS = 300
PROBE_TIMEOUT_SECONDS = 60
D9_NAME = "D9 behavioural differential"
D10_NAME = "D10a coverage differential (Enter only, no baseline subtraction)"
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
    meta: dict[str, Any] = {"notes": {}, "timings": {}}

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

        t0 = time.monotonic()
        rows = await detectors.survey(page)
        meta["timings"]["survey"] = round((time.monotonic() - t0) * 1000, 1)
        seen = {r["probe"] for r in rows}
        meta["unobservable"] = sorted(set(probe_ids) - seen)

        survey_detectors = [
            detectors.d0_axcess_clickables(rows),
            detectors.d2_inline_attribute(rows),
            detectors.d2b_handler_property(rows),
            detectors.d3_tabindex_aria(rows),
            detectors.d4_css_lexical(rows),
            detectors.d7_react_props(rows),
        ]
        for result in survey_detectors:
            reported[result.detector] = result.reported(order)
            if result.note:
                meta["notes"][result.detector] = result.note

        d5 = await detectors.d5_cdp_listeners(page, cdp, probe_ids)
        cdp.require_success()
        reported[d5.detector] = d5.reported(order)

        d6 = await detectors.d6_listener_shim(page)
        reported[d6.detector] = d6.reported(order)
        if d6.note:
            meta["notes"][d6.detector] = d6.note

        d8 = await detectors.d8_hover_diff(page, probe_ids)
        reported[d8.detector] = d8.reported(order)

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

    @property
    def reported(self) -> bool:
        return not self.uncertainties and bool(self.mouse) and not self.keyboard

    def to_json(self) -> dict[str, Any]:
        return {
            "mouse_coverage": sorted(self.mouse),
            "enter_coverage": sorted(self.keyboard),
            "uncertainties": self.uncertainties,
        }


@dataclass
class BehaviouralResult:
    d9: set[str] = field(default_factory=set)
    d10: set[str] = field(default_factory=set)
    d9_unknown: set[str] = field(default_factory=set)
    d10_unknown: set[str] = field(default_factory=set)
    reasons: dict[str, str] = field(default_factory=dict)
    coverage: dict[str, dict[str, Any]] = field(default_factory=dict)


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

    for probe_id in probe_ids:
        try:
            async with asyncio.timeout(PROBE_TIMEOUT_SECONDS):
                outcomes.append(await runner.run_probe(probe_id, page_path, order))
        finally:
            # The shared differential may fail during setup before it can own
            # its context in a finally block. The factory tracks those too.
            async with asyncio.timeout(15):
                await factory.close_open_contexts()
        pair = await _coverage_pair(factory, config, probe_id, order)
        if pair.reported:
            result.d10.add(probe_id)
        if pair.uncertainties:
            result.d10_unknown.add(probe_id)
        result.coverage[probe_id] = pair.to_json()

    confirmed, _ = apply_equivalence(outcomes)
    result.d9 = {o.probe_id for o in confirmed if o.verdict is Verdict.VIOLATION}
    result.d9_unknown = {o.probe_id for o in confirmed if o.verdict is Verdict.UNKNOWN}
    for outcome in confirmed:
        result.reasons[outcome.probe_id] = f"{outcome.verdict.value}: {outcome.reason}"
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

    methods = [*CHEAP_METHODS, *([] if args.cheap_only else [D9_NAME, D10_NAME])]
    all_reported: dict[str, set[str]] = {name: set() for name in methods}
    all_unknown: dict[str, set[str]] = {name: set() for name in methods}
    reasons: dict[str, str] = {}
    coverage: dict[str, dict[str, Any]] = {}
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
                            all_unknown[name].update(unobservable)
                            if not name.startswith("D1 ") and not name.startswith("D1x "):
                                all_unknown[name].update(capped)
                        notes.update(meta["notes"])
                        tab_info[page_path] = {"presses": order.presses, "capped": order.capped}

                        if not args.cheap_only:
                            result = await run_behavioural(factory, page_path, probe_ids, order)
                            all_reported[D9_NAME].update(result.d9)
                            all_reported[D10_NAME].update(result.d10)
                            all_unknown[D9_NAME].update(result.d9_unknown)
                            all_unknown[D10_NAME].update(result.d10_unknown)
                            reasons.update(result.reasons)
                            coverage.update(result.coverage)
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
        "--cheap-only",
        action="store_true",
        help="skip D9/D10a behavioural and coverage measurements",
    )
    return asyncio.run(main_async(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
