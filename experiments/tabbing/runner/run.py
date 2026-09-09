"""Measure annotated targets and score oracle and candidate-gated outcomes.

The legacy ``end_to_end`` mode filters supplied-target results by candidate
selection. It does not measure unannotated false alarms, discovery workload,
or equivalent alternatives beyond the annotated targets.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from playwright.async_api import async_playwright

from audit.analyzer.keyboard.kbdiff import (
    DifferentialRunner,
    ProbeOutcome,
    TrialConfig,
    Verdict,
    apply_equivalence,
    candidate_probe_ids,
    collect_candidates,
    score_outcomes,
)
from audit.analyzer.keyboard.kbdiff.model import ModalityResult, Uncertainty
from audit.analyzer.keyboard.kbdiff.score import Score, check_invariant
from experiments.tabbing.runner.corpus import Corpus
from experiments.tabbing.runner.serve import ContextFactory, page_url

# Both viewports the corpus carries labels for. Upstream scored one and listed
# single-resolution testing as a limitation they could not close; hover menus and
# responsive collapse are viewport-dependent, so one number hides the disagreement.
VIEWPORTS: dict[str, dict[str, int]] = {
    "desktop": {"width": 1280, "height": 900},
    "mobile": {"width": 390, "height": 844},
}


@dataclass
class RunState:
    """Everything one full run produces, before it is written out."""

    outcomes: list[ProbeOutcome] = field(default_factory=list)
    dismissals: list[dict[str, str]] = field(default_factory=list)
    candidates_by_page: dict[str, list[str] | None] = field(default_factory=dict)
    candidate_outcomes: list[ProbeOutcome] = field(default_factory=list)
    observed_outcomes: list[ProbeOutcome] | None = None
    tab_orders: dict[str, dict[str, Any]] = field(default_factory=dict)
    errors: list[dict[str, str]] = field(default_factory=list)
    timings: dict[str, float] = field(default_factory=dict)
    # Reported by the browser that actually ran, not inferred from the cache
    # directory: three Chromium builds are installed side by side here, and the
    # newest is not the one Playwright launches.
    browser_version: str = "unknown"


async def run_corpus(
    corpus: Corpus,
    *,
    viewports: list[str],
    headless: bool = True,
    max_tabs: int = 300,
    settle_ms: int = 250,
    probe_timeout_s: int = 60,
    run_timeout_s: int = 1800,
) -> RunState:
    """Measure every probe on every page, at every requested viewport."""
    state = RunState()
    started = time.monotonic()

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=headless)
        state.browser_version = browser.version
        try:
            try:
                async with asyncio.timeout(run_timeout_s):
                    for viewport_name in viewports:
                        factory = ContextFactory(browser, VIEWPORTS[viewport_name], corpus.root)
                        try:
                            for page_path, probe_ids in sorted(corpus.pages.items()):
                                await _run_page(
                                    state,
                                    corpus,
                                    factory,
                                    page_path,
                                    probe_ids,
                                    viewport_name,
                                    max_tabs=max_tabs,
                                    settle_ms=settle_ms,
                                    probe_timeout_s=probe_timeout_s,
                                )
                        finally:
                            for counter, value in factory.totals.items():
                                state.timings[f"{counter}.{viewport_name}"] = float(value)
                            await factory.close_open_contexts()
            except TimeoutError:
                state.errors.append(
                    {
                        "page": "all",
                        "stage": "run_timeout",
                        "error": (
                            f"run exceeded {run_timeout_s} seconds; remaining probes are unknown"
                        ),
                    }
                )
        finally:
            await browser.close()

    state.timings["wall_seconds"] = round(time.monotonic() - started, 2)
    return state


async def _run_page(
    state: RunState,
    corpus: Corpus,
    factory: ContextFactory,
    page_path: str,
    probe_ids: list[str],
    viewport: str,
    *,
    max_tabs: int,
    settle_ms: int,
    probe_timeout_s: int = 60,
) -> None:
    """Measure one page at one viewport."""
    config = TrialConfig(
        url=page_url(page_path),
        viewport=viewport,
        settle_ms=settle_ms,
        max_tabs=max_tabs,
    )
    runner = DifferentialRunner(factory, config)
    key = f"{page_path}@{viewport}"

    try:
        async with asyncio.timeout(probe_timeout_s):
            order = await runner.tab_order()
    except Exception as exc:
        state.errors.append({"page": key, "stage": "tab_order", "error": str(exc)[:300]})
        state.candidates_by_page[key] = None
        state.outcomes.extend(
            unknown_outcome(pid, page_path, viewport, "tab-order measurement failed")
            for pid in probe_ids
        )
        return
    finally:
        await factory.close_open_contexts()

    state.tab_orders[key] = {
        "presses": order.presses,
        "capped": order.capped,
        "found": len(order.index),
    }

    # Candidate discovery, for end-to-end scoring. Done once per page in its own
    # context so it cannot perturb the measurements that follow.
    try:
        async with asyncio.timeout(probe_timeout_s):
            context = await factory()
            try:
                page = await context.new_page()
                await page.goto(config.url, wait_until="load")
                found = candidate_probe_ids(await collect_candidates(page))
                state.candidates_by_page[key] = sorted(found)
            finally:
                await context.close()
    except Exception as exc:
        state.errors.append({"page": key, "stage": "candidates", "error": str(exc)[:300]})
        state.candidates_by_page[key] = None
    finally:
        await factory.close_open_contexts()

    for probe_id in probe_ids:
        try:
            async with asyncio.timeout(probe_timeout_s):
                state.outcomes.append(await runner.run_probe(probe_id, page_path, order))
        except Exception as exc:
            state.errors.append(
                {"page": key, "stage": f"probe:{probe_id}", "error": str(exc)[:300]}
            )
            # A probe that crashed the instrument must still be accounted for.
            # Dropping it here shrinks the denominator silently, which flatters
            # every rate computed from it -- the precise failure the invariant
            # check exists to catch, arriving before the check can see it.
            state.outcomes.append(
                ProbeOutcome(
                    probe_id=probe_id,
                    page=page_path,
                    viewport=viewport,
                    in_tab_order=order.contains(probe_id),
                    tab_index=order.position(probe_id),
                    mouse=ModalityResult(
                        attempted=False,
                        note=f"probe raised: {exc!s}"[:200],
                        uncertainty=Uncertainty.INSTRUMENT_ERROR,
                    ),
                    keyboard_by_key={},
                    verdict=Verdict.UNKNOWN,
                    uncertainty=Uncertainty.INSTRUMENT_ERROR,
                    reason="the probe raised during measurement; nothing was observed",
                )
            )
        finally:
            await factory.close_open_contexts()


def unknown_outcome(probe_id: str, page: str, viewport: str, reason: str) -> ProbeOutcome:
    return ProbeOutcome(
        probe_id=probe_id,
        page=page,
        viewport=viewport,
        in_tab_order=False,
        tab_index=None,
        mouse=ModalityResult(attempted=False, uncertainty=Uncertainty.INSTRUMENT_ERROR),
        keyboard_by_key={},
        verdict=Verdict.UNKNOWN,
        uncertainty=Uncertainty.INSTRUMENT_ERROR,
        reason=reason,
    )


def complete_outcomes(
    corpus: Corpus, outcomes: list[ProbeOutcome], viewports: list[str]
) -> list[ProbeOutcome]:
    """Keep every frozen label in the denominator, even if an entire page failed."""
    indexed: dict[tuple[str, str], ProbeOutcome] = {}
    for outcome in outcomes:
        key = (outcome.probe_id, outcome.viewport)
        if key in indexed:
            raise ValueError(f"duplicate measurement: {key}")
        probe = corpus.probes.get(outcome.probe_id)
        if probe is None or probe.page != outcome.page or outcome.viewport not in viewports:
            raise ValueError(f"measurement outside corpus scope: {key}")
        indexed[key] = outcome
    return [
        indexed.get((pid, viewport))
        or unknown_outcome(pid, probe.page, viewport, "measurement missing or run stopped")
        for viewport in viewports
        for pid, probe in corpus.probes.items()
    ]


def score_run(corpus: Corpus, state: RunState, viewports: list[str]) -> list[Score]:
    """Produce every score row, with the invariant checked on each.

    Rows are cut by viewport, cohort and mode rather than reported as one
    aggregate. A single number over a mixed corpus would hide the two
    comparisons the study exists to make: upstream fixtures against fresh ones,
    and supplied targets against discovered ones.
    """
    scores: list[Score] = []
    if state.observed_outcomes is None:
        state.observed_outcomes = list(state.outcomes)
    complete = complete_outcomes(corpus, state.observed_outcomes, viewports)
    confirmed: list[ProbeOutcome] = []
    state.dismissals = []
    for viewport in viewports:
        for page in corpus.pages:
            group = [o for o in complete if o.page == page and o.viewport == viewport]
            rewritten, dismissed = apply_equivalence(group)
            confirmed.extend(rewritten)
            state.dismissals.extend(
                {
                    "probe": d.probe_id,
                    "dismissed_by": d.dismissed_by,
                    "signature": d.signature,
                    "page": page,
                    "viewport": viewport,
                }
                for d in dismissed
            )
    # Publish what was scored. Writing the pre-equivalence outcomes while
    # scoring the post-equivalence ones left raw.json asserting "violation" for
    # probes the score had already dismissed -- evidence that contradicts the
    # number it is supposed to support.
    state.outcomes = confirmed
    state.candidate_outcomes = [candidate_gate(o, state) for o in confirmed]

    for viewport in viewports:
        in_viewport = [o for o in confirmed if o.viewport == viewport]
        truth = corpus.truth_for(viewport)

        for cohort in ("upstream", "holdout", "all"):
            subset = [
                o for o in in_viewport if cohort == "all" or corpus.cohort_of(o.probe_id) == cohort
            ]
            cohort_truth = {
                pid: label
                for pid, label in truth.items()
                if cohort == "all" or corpus.cohort_of(pid) == cohort
            }
            if not cohort_truth:
                continue

            oracle = score_outcomes(
                subset,
                cohort_truth,
                detector="kbdiff differential + equivalence",
                cohort=cohort,
                viewport=viewport,
                mode="oracle",
            )
            check_invariant(oracle, len(cohort_truth))
            scores.append(oracle)

            scores.append(
                _score_end_to_end(subset, cohort_truth, state, cohort=cohort, viewport=viewport)
            )

    return scores


def _score_end_to_end(
    outcomes: list[ProbeOutcome],
    truth: dict[str, str],
    state: RunState,
    *,
    cohort: str,
    viewport: str,
) -> Score:
    """Score candidate-gated annotated targets, preserving uncertain measurements."""
    adjusted = [candidate_gate(outcome, state) for outcome in outcomes]

    score = score_outcomes(
        adjusted,
        truth,
        detector="kbdiff candidates -> differential + equivalence",
        cohort=cohort,
        viewport=viewport,
        mode="end_to_end",
    )
    check_invariant(score, len(truth))
    return score


def candidate_gate(outcome: ProbeOutcome, state: RunState) -> ProbeOutcome:
    """A failed discovery pass is unknown, not evidence that a target was absent."""
    discovered = state.candidates_by_page.get(f"{outcome.page}@{outcome.viewport}")
    if outcome.verdict is Verdict.UNKNOWN:
        return outcome
    if discovered is None:
        return replace(
            outcome,
            verdict=Verdict.UNKNOWN,
            uncertainty=Uncertainty.INSTRUMENT_ERROR,
            reason="candidate discovery failed or was not run",
        )
    if outcome.probe_id not in discovered and outcome.verdict is Verdict.VIOLATION:
        return replace(
            outcome,
            verdict=Verdict.NO_LEAD,
            uncertainty=None,
            reason="never proposed by the candidate pass; unreachable end to end",
        )
    return outcome


def serialize_outcome(outcome: ProbeOutcome) -> dict[str, Any]:
    """Version 2: preserve real independent key trials; do not invent their union."""
    return outcome.to_json()


def candidate_recall(corpus: Corpus, state: RunState, viewport: str) -> dict[str, Any]:
    """How many real defects the cheap pass proposed, before any confirmation.

    This is the ceiling on end-to-end recall: the oracle cannot confirm what it
    is never handed. Reported separately so the report can attribute a low
    end-to-end number to the right stage.
    """
    truth = corpus.truth_for(viewport)
    positives = {pid for pid, label in truth.items() if label == "violation"}

    discovered: set[str] = set()
    for key, ids in state.candidates_by_page.items():
        if key.endswith(f"@{viewport}"):
            discovered.update(ids or [])

    hit = positives & discovered
    return {
        "viewport": viewport,
        "positives": len(positives),
        "proposed": len(hit),
        "missed": sorted(positives - discovered),
        "unknown_pages": sorted(
            page
            for page in corpus.pages
            if state.candidates_by_page.get(f"{page}@{viewport}") is None
        ),
        "recall": round(len(hit) / len(positives), 4) if positives else None,
    }


def resolve_paths(repo_root: Path) -> tuple[Path, Path]:
    """Fixture root and default output directory."""
    base = repo_root / "experiments" / "tabbing"
    return base / "fixtures", base / "results"
