"""Offline bakeoff integrity: failed instruments cannot improve a score."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from audit.analyzer.keyboard.kbdiff.model import Verdict
from audit.analyzer.keyboard.kbdiff.taborder import TabOrder
from experiments.tabbing.runner import bakeoff
from experiments.tabbing.runner.corpus import compute_corpus_sha256, sha256_file


@pytest.fixture
def corpus_root(tmp_path: Path) -> Path:
    root = tmp_path / "corpus"
    (root / "pages").mkdir(parents=True)
    (root / "pages/a.html").write_text("<button data-probe='p1'>Go</button>")
    (root / "pages/helper.js").write_text("const helper = 1;")
    (root / "truth.json").write_text(
        json.dumps(
            {
                "pages": {"pages/a.html": ["p1", "p2"]},
                "probes": {"p1": {"label": "violation"}, "p2": {"label": "ok"}},
            }
        )
    )
    return root


def test_development_hash_pins_inputs_and_ignores_generated_results(corpus_root: Path):
    before = bakeoff.corpus_fingerprint(corpus_root, "edgecases")
    (corpus_root / "results").mkdir()
    (corpus_root / "results/old.json").write_text("historical result")
    assert bakeoff.corpus_fingerprint(corpus_root, "edgecases") == before
    (corpus_root / "pages/helper.js").write_text("const helper = 2;")
    assert bakeoff.corpus_fingerprint(corpus_root, "edgecases") != before
    assert "no unbiased accuracy or ranking claim" in bakeoff.CORPORA["edgecases"][2]


def test_fixture_hash_verifies_frozen_manifest(corpus_root: Path):
    files = {
        str(path.relative_to(corpus_root)): sha256_file(path)
        for path in corpus_root.rglob("*")
        if path.is_file()
    }
    expected = compute_corpus_sha256(files)
    (corpus_root / "frozen-manifest.json").write_text(
        json.dumps(
            {
                "files": files,
                "corpus_sha256": expected,
            }
        )
    )
    assert bakeoff.corpus_fingerprint(corpus_root, "fixtures") == expected
    (corpus_root / "truth.json").write_text("{}")
    with pytest.raises(RuntimeError, match="refusing to score"):
        bakeoff.corpus_fingerprint(corpus_root, "fixtures")


def test_truth_rejects_unassigned_and_duplicated_probes(corpus_root: Path):
    path = corpus_root / "truth.json"
    data = json.loads(path.read_text())
    data["pages"]["pages/a.html"] = ["p1", "p1"]
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="exactly one page"):
        bakeoff.load_truth(corpus_root, "truth.json")


def test_truth_selects_desktop_label(corpus_root: Path):
    path = corpus_root / "truth.json"
    data = json.loads(path.read_text())
    data["probes"]["p1"]["labels_by_viewport"] = {"desktop": "ok", "mobile": "violation"}
    path.write_text(json.dumps(data))
    assert bakeoff.load_truth(corpus_root, "truth.json")[1]["p1"] == "ok"


def test_uncertainty_overrides_even_reported_violation_and_retains_denominator():
    labels = {"p1": "violation", "p2": "ok", "p3": "violation"}
    scores = bakeoff.score_methods(
        labels, {"first": {"p1"}, "empty": set()}, {"first": {"p1", "p2"}}, "edgecases"
    )
    assert [(score.total, score.viewport) for score in scores] == [(3, "desktop"), (3, "desktop")]
    assert (scores[0].tp, scores[0].unknown_positive, scores[0].unknown_negative) == (0, 1, 1)
    assert scores[0].recall == 0
    assert scores[1].fn == 2
    assert bakeoff.to_outcome_stub("p1", {"p1"}, {"p1"}).verdict is Verdict.UNKNOWN


def test_scores_reject_probes_outside_truth():
    with pytest.raises(ValueError, match="outside the selected corpus"):
        bakeoff.score_methods({"p1": "ok"}, {"method": {"foreign"}}, {}, "edgecases")


class FakeCDP:
    def __init__(self, *, broken: str | None = None):
        self.broken = broken
        self.reads = 0

    async def send(self, command, _options=None):
        if self.broken == "start" and command == "Profiler.startPreciseCoverage":
            raise RuntimeError("profiler unavailable")
        if command != "Profiler.takePreciseCoverage":
            return {}
        if self.broken == "read":
            raise RuntimeError("coverage unavailable")
        if self.broken == "malformed":
            return {}
        self.reads += 1
        return {
            "result": []
            if self.reads == 1
            else [
                {
                    "url": "fixture",
                    "functions": [
                        {
                            "functionName": "handler",
                            "ranges": [{"count": 1, "startOffset": 7}],
                        }
                    ],
                }
            ]
        }


def fake_page(*, visible=True, focused=True):
    locator = SimpleNamespace(
        bounding_box=AsyncMock(
            return_value={"x": 10, "y": 10, "width": 10, "height": 10} if visible else None
        ),
        evaluate=AsyncMock(return_value=focused),
    )
    locator.first = locator
    return SimpleNamespace(
        goto=AsyncMock(),
        wait_for_timeout=AsyncMock(),
        locator=lambda _selector: locator,
        mouse=SimpleNamespace(click=AsyncMock()),
        keyboard=SimpleNamespace(press=AsyncMock()),
        viewport_size=dict(bakeoff.VIEWPORT),
    )


class FakeCoverageFactory:
    def __init__(self, *trials):
        self.trials = list(trials)
        self.contexts = []
        self.close_open_contexts = AsyncMock()

    async def __call__(self):
        page, cdp = self.trials.pop(0)
        context = SimpleNamespace(
            new_page=AsyncMock(return_value=page),
            new_cdp_session=AsyncMock(return_value=cdp),
            close=AsyncMock(),
        )
        self.contexts.append(context)
        return context


@pytest.mark.parametrize("broken", ["start", "read", "malformed"])
async def test_swallowed_profiler_failure_is_unknown(broken):
    factory = FakeCoverageFactory((fake_page(), FakeCDP(broken=broken)))
    pair = await bakeoff._coverage_pair(
        factory, bakeoff.TrialConfig("fixture", "desktop"), "p1", TabOrder({}, False, 1)
    )
    assert "mouse" in pair.uncertainties
    assert not pair.reported
    factory.contexts[0].close.assert_awaited_once()


@pytest.mark.parametrize("capped", [False, True])
async def test_coverage_cap_is_unknown_but_completed_unreachability_is_measured(capped):
    factory = FakeCoverageFactory((fake_page(), FakeCDP()))
    pair = await bakeoff._coverage_pair(
        factory, bakeoff.TrialConfig("fixture", "desktop"), "p1", TabOrder({}, capped, 3)
    )
    assert pair.mouse == {"fixture#handler@7"}
    assert pair.reported is (not capped)
    assert bool(pair.uncertainties) is capped


async def test_missing_mouse_box_is_unknown():
    factory = FakeCoverageFactory((fake_page(visible=False), FakeCDP()))
    pair = await bakeoff._coverage_pair(
        factory, bakeoff.TrialConfig("fixture", "desktop"), "p1", TabOrder({}, False, 3)
    )
    assert pair.uncertainties["mouse"].startswith("not_rendered")
    assert not pair.reported


async def test_keyboard_failure_keeps_mouse_evidence_without_reporting_violation():
    factory = FakeCoverageFactory((fake_page(), FakeCDP()), (fake_page(), FakeCDP(broken="read")))
    pair = await bakeoff._coverage_pair(
        factory, bakeoff.TrialConfig("fixture", "desktop"), "p1", TabOrder({"p1": 1}, False, 3)
    )
    assert pair.mouse
    assert "keyboard" in pair.uncertainties
    assert not pair.reported
    for context in factory.contexts:
        context.close.assert_awaited_once()


async def test_wrong_tab_focus_is_unknown_without_sending_enter():
    keyboard_page = fake_page(focused=False)
    factory = FakeCoverageFactory((fake_page(), FakeCDP()), (keyboard_page, FakeCDP()))
    pair = await bakeoff._coverage_pair(
        factory, bakeoff.TrialConfig("fixture", "desktop"), "p1", TabOrder({"p1": 1}, False, 3)
    )
    assert "unresolved" in pair.uncertainties["keyboard"]
    assert [call.args for call in keyboard_page.keyboard.press.await_args_list] == [("Tab",)]


async def test_behavioural_methods_keep_independent_unknown_sets(monkeypatch):
    # A measured baseline, so this test isolates what it means to isolate: the
    # per-method unknown sets. Baseline failure is covered separately below.
    monkeypatch.setattr(
        bakeoff, "_upstream_baseline", AsyncMock(return_value=(frozenset(), "measured", False))
    )
    monkeypatch.setattr(
        bakeoff, "_upstream_differential", AsyncMock(return_value=bakeoff.UpstreamPass())
    )
    outcomes = [
        bakeoff.to_outcome_stub("p1", set(), {"p1"}),
        bakeoff.to_outcome_stub("p2", set(), set()),
    ]
    runner = SimpleNamespace(run_probe=AsyncMock(side_effect=outcomes))
    monkeypatch.setattr(bakeoff, "DifferentialRunner", lambda *_args: runner)
    monkeypatch.setattr(
        bakeoff,
        "_coverage_pair",
        AsyncMock(
            side_effect=[
                bakeoff.CoveragePair(mouse={"handler"}),
                bakeoff.CoveragePair(uncertainties={"mouse": "failed"}),
            ]
        ),
    )
    result = await bakeoff.run_behavioural(
        SimpleNamespace(close_open_contexts=AsyncMock()),
        "a.html",
        ["p1", "p2"],
        TabOrder({}, False, 2),
    )
    assert result.d9_unknown == {"p1"}
    assert result.d10_unknown == {"p2"}
    assert result.d10 == {"p1"}


async def test_page_setup_failure_closes_context():
    context = SimpleNamespace(
        add_init_script=AsyncMock(side_effect=RuntimeError("setup failed")), close=AsyncMock()
    )
    with pytest.raises(RuntimeError, match="setup failed"):
        await bakeoff.run_page(AsyncMock(return_value=context), Path("."), "a.html", [], None)
    context.close.assert_awaited_once()


@pytest.fixture
def fake_run(monkeypatch, corpus_root: Path, tmp_path: Path):
    monkeypatch.setitem(bakeoff.CORPORA, "edgecases", (corpus_root, "truth.json", "development"))
    browser = SimpleNamespace(version="test-chromium-1", close=AsyncMock())
    launcher = SimpleNamespace(launch=AsyncMock(return_value=browser))

    class Playwright:
        async def __aenter__(self):
            return SimpleNamespace(chromium=launcher)

        async def __aexit__(self, *_exc):
            return False

    monkeypatch.setattr(bakeoff, "async_playwright", Playwright)
    monkeypatch.setattr(bakeoff.AxeAnalyzer, "from_bundled", lambda: None)
    factory = SimpleNamespace(
        totals={"served": 3, "ping": 1, "blocked": 0, "missing": 0, "websocket": 0},
        close_open_contexts=AsyncMock(),
    )
    monkeypatch.setattr(bakeoff, "ContextFactory", lambda *_args: factory)
    monkeypatch.setattr(
        bakeoff,
        "source_sha256",
        lambda: {"detector": {"_combined": "d"}, "runner": {"_combined": "r"}},
    )

    async def run_page(*_args):
        await asyncio.sleep(0.001)
        return (
            {name: set() for name in bakeoff.CHEAP_METHODS},
            TabOrder({}, False, 2),
            {"notes": {}, "timings": {}, "unobservable": [], "viewport": dict(bakeoff.VIEWPORT)},
        )

    monkeypatch.setattr(bakeoff, "run_page", run_page)
    args = argparse.Namespace(
        corpus="edgecases",
        out=str(tmp_path / "out"),
        label="new-run",
        cheap_only=True,
        timeout_seconds=10,
    )
    output = Path(args.out) / "bakeoff-edgecases-new-run.json"
    return args, output, browser, launcher


async def test_new_output_has_actual_metadata_and_complete_denominators(fake_run):
    args, output, browser, _launcher = fake_run
    assert await bakeoff.main_async(args) == 0
    payload = json.loads(output.read_text())
    run = payload["run"]
    assert run["valid"]
    assert datetime.fromisoformat(run["started_utc"]) < datetime.fromisoformat(run["finished_utc"])
    assert run["versions"]["chromium"] == "test-chromium-1"
    assert run["versions"]["python"] and run["versions"]["playwright"]
    assert run["source_sha256_before"] == run["source_sha256_after"]
    assert run["corpus_sha256"] == run["corpus_sha256_after"]
    assert run["actual_viewports"] == {"pages/a.html": bakeoff.VIEWPORT}
    assert run["request_counters"] == {
        "served": 3,
        "ping": 1,
        "blocked": 0,
        "missing": 0,
        "websocket": 0,
    }
    assert len(payload["scores"]) == len(bakeoff.CHEAP_METHODS)
    assert all(
        sum(row[k] for k in ("tp", "fp", "fn", "tn", "unknown")) == 2 for row in payload["scores"]
    )
    browser.close.assert_awaited_once()


async def test_existing_output_is_preserved_before_launch(fake_run):
    args, output, _browser, launcher = fake_run
    output.parent.mkdir()
    output.write_text("preserved result")
    assert await bakeoff.main_async(args) == 2
    assert output.read_text() == "preserved result"
    launcher.launch.assert_not_awaited()


async def test_output_created_during_run_is_not_overwritten(fake_run, monkeypatch):
    args, output, _browser, _launcher = fake_run
    original = bakeoff.run_page

    async def raced(*args):
        output.write_text("other run")
        return await original(*args)

    monkeypatch.setattr(bakeoff, "run_page", raced)
    assert await bakeoff.main_async(args) == 2
    assert output.read_text() == "other run"


async def test_source_change_suppresses_scores_and_fails(fake_run, monkeypatch):
    args, output, _browser, _launcher = fake_run
    hashes = iter([{"runner": {"_combined": "before"}}, {"runner": {"_combined": "after"}}])
    monkeypatch.setattr(bakeoff, "source_sha256", lambda: next(hashes))
    assert await bakeoff.main_async(args) == 1
    payload = json.loads(output.read_text())
    assert not payload["run"]["valid"]
    assert not payload["run"]["source_unchanged"]
    assert payload["scores"] == []
    assert "source changed" in payload["run"]["errors"][0]


@pytest.mark.parametrize("failure", ["exception", "missing_method", "viewport", "timeout"])
async def test_incomplete_measurement_never_scores_partial_negatives(
    fake_run, monkeypatch, failure
):
    args, output, browser, _launcher = fake_run
    original = bakeoff.run_page

    async def broken(*args):
        if failure == "exception":
            raise RuntimeError("survey failed")
        if failure == "timeout":
            raise TimeoutError("page deadline")
        reported, order, meta = await original(*args)
        if failure == "missing_method":
            reported.pop(next(iter(reported)))
        else:
            meta["viewport"] = {"width": 1, "height": 1}
        return reported, order, meta

    monkeypatch.setattr(bakeoff, "run_page", broken)
    assert await bakeoff.main_async(args) == 1
    payload = json.loads(output.read_text())
    assert payload["scores"] == []
    assert not payload["run"]["valid"]
    assert payload["run"]["errors"]
    browser.close.assert_awaited_once()


@pytest.mark.parametrize("label", ["../old", "/absolute", "nested/name", "x y", "x" * 65])
def test_cli_rejects_unsafe_output_label(monkeypatch, label):
    monkeypatch.setattr(sys, "argv", ["bakeoff", "--label", label])
    with pytest.raises(SystemExit) as exc:
        bakeoff.main()
    assert exc.value.code == 2


async def test_axe_swallowed_install_error_remains_an_instrument_failure():
    page = bakeoff.CheckedInstrument(
        SimpleNamespace(evaluate=AsyncMock(side_effect=RuntimeError("execution context destroyed")))
    )
    analyzer = bakeoff.AxeAnalyzer(axe_source="fixture bundle")
    assert await analyzer.run(page) == []
    with pytest.raises(RuntimeError, match="instrument failed"):
        page.require_success()


async def test_corpus_change_during_measurement_suppresses_scores(fake_run, monkeypatch):
    args, output, _browser, _launcher = fake_run
    fingerprints = iter(["before", "after"])
    monkeypatch.setattr(bakeoff, "corpus_fingerprint", lambda *_args: next(fingerprints))
    assert await bakeoff.main_async(args) == 1
    payload = json.loads(output.read_text())
    assert payload["scores"] == []
    assert "corpus inputs changed" in payload["run"]["errors"][0]


async def test_actual_overall_timeout_writes_invalid_result_and_closes_browser(
    fake_run, monkeypatch
):
    args, output, browser, _launcher = fake_run
    args.timeout_seconds = 0.005

    async def blocked(*_args):
        await asyncio.Event().wait()

    monkeypatch.setattr(bakeoff, "run_page", blocked)
    assert await bakeoff.main_async(args) == 1
    payload = json.loads(output.read_text())
    assert payload["scores"] == []
    assert "TimeoutError" in payload["run"]["errors"][0]
    browser.close.assert_awaited_once()


class TestCoverageArmedFailuresStayUnknown:
    """A coverage-armed trial that raises must not quietly become a verdict.

    The first version of ``_coverage_armed_outcomes`` dropped a failed probe
    from its list. The score denominator still contained the target, so a
    missing positive was counted as a false negative and a missing negative as
    a true negative -- the collapse of "could not measure" into an answer that
    the whole experiment exists to refuse. It is only reachable when the
    browser fails mid-run, which no other test drove.
    """

    def test_a_raising_probe_becomes_an_unknown_outcome(self):
        import asyncio
        from unittest.mock import AsyncMock, patch

        from audit.analyzer.keyboard.kbdiff.model import Uncertainty, Verdict
        from experiments.tabbing.runner import bakeoff

        factory = AsyncMock()
        factory.close_open_contexts = AsyncMock()
        order = SimpleNamespace(position=lambda pid: 1, capped=False)

        with patch.object(bakeoff, "DifferentialRunner") as runner_cls:
            runner_cls.return_value.run_probe = AsyncMock(side_effect=RuntimeError("browser died"))
            outcomes = asyncio.run(
                bakeoff._coverage_armed_outcomes(factory, "a.html", ["p01", "p02"], order)
            )

        assert len(outcomes) == 2, "every probe must stay in the record"
        assert {o.probe_id for o in outcomes} == {"p01", "p02"}
        for outcome in outcomes:
            assert outcome.verdict is Verdict.UNKNOWN
            assert outcome.uncertainty is Uncertainty.INSTRUMENT_ERROR


class TestFixtureOriginFilter:
    """Coverage comparisons must see the page, not the harness."""

    def test_harness_functions_are_excluded(self):
        from experiments.tabbing.runner.bakeoff import BASE_URL, _fixture_only

        mixed = frozenset(
            {
                f"{BASE_URL}/upstream/b-decoys.html#favourite@586",
                f"{BASE_URL}/upstream/_helpers.js#fired@157",
                "#(anon)@0",  # an evaluate body: empty url
                "chrome-extension://x/y.js#f@1",  # not the fixture origin
            }
        )
        assert _fixture_only(mixed) == {
            f"{BASE_URL}/upstream/b-decoys.html#favourite@586",
            f"{BASE_URL}/upstream/_helpers.js#fired@157",
        }

    def test_an_all_harness_set_becomes_empty_rather_than_equal(self):
        """Two unfiltered sets of harness noise must not be mistaken for a match."""
        from experiments.tabbing.runner.bakeoff import _fixture_only

        assert _fixture_only(frozenset({"#a@0", "#b@1"})) == frozenset()


class TestBaselineFailurePropagates:
    """A floor we could not measure is not a floor of zero.

    Subtracting nothing and scoring on regardless turns a failed profiler read
    into a confident coverage verdict, which is the same defect as counting an
    unreachable probe as a pass.
    """

    async def test_failed_baseline_makes_every_coverage_rule_abstain(self, monkeypatch):
        monkeypatch.setattr(
            bakeoff,
            "_upstream_baseline",
            AsyncMock(return_value=(frozenset(), "failed: profiler: boom", True)),
        )
        monkeypatch.setattr(
            bakeoff, "_upstream_differential", AsyncMock(return_value=bakeoff.UpstreamPass())
        )
        runner = SimpleNamespace(
            run_probe=AsyncMock(side_effect=[bakeoff.to_outcome_stub("p1", set(), set())])
        )
        monkeypatch.setattr(bakeoff, "DifferentialRunner", lambda *_args: runner)
        monkeypatch.setattr(
            bakeoff, "_coverage_pair", AsyncMock(return_value=bakeoff.CoveragePair(mouse={"h"}))
        )
        result = await bakeoff.run_behavioural(
            SimpleNamespace(close_open_contexts=AsyncMock()),
            "a.html",
            ["p1"],
            TabOrder({}, False, 1),
        )
        assert result.d10_unknown == {"p1"}
        assert result.d10u_unknown == {"p1"}
        assert result.baseline_evidence["failed"] is True

    async def test_absent_baseline_target_is_not_a_failure(self):
        """Ten holdout pages carry no #baseline-target; an empty floor is correct there."""
        assert bakeoff.UpstreamPass().coverage_is_trustworthy

    async def test_a_profiler_failure_stops_a_confident_coverage_verdict(self):
        """Without this, an unread keyboard set reads as "the keyboard ran nothing"."""
        clean = bakeoff.UpstreamPass(mouse_coverage=frozenset({"f"}))
        assert clean.reported_coverage
        broken = bakeoff.UpstreamPass(
            mouse_coverage=frozenset({"f"}), coverage_uncertainties={"keyboard": "profiler: boom"}
        )
        assert not broken.reported_coverage
        assert not broken.reported_coverage_setdiff


class TestUpstreamStage4IsTranscribed:
    """Pins `upstream_stage4` to the rules in tabbing-experiment.spec.ts.

    Their filter has four guards that are easy to drop in translation, and each
    one changes results: an empty mouse coverage abstains, an empty candidate
    coverage is skipped, the channel signatures must match exactly, and the
    coverage sets must be equal rather than merely overlapping.
    """

    @staticmethod
    def _pass(**kw):
        from experiments.tabbing.runner.bakeoff import UpstreamPass

        return UpstreamPass(**kw)

    def test_equal_coverage_and_signature_dismisses(self):
        from experiments.tabbing.runner.bakeoff import upstream_stage4

        passes = {
            "f": self._pass(mouse_changed={"dom"}, mouse_coverage=frozenset({"a"})),
            "k": self._pass(
                keyboard_changed={"dom"}, keyboard_coverage=frozenset({"a"}), in_tab_order=True
            ),
        }
        kept, dismissed = upstream_stage4(passes)
        assert kept == set() and dismissed == {"f": "k"}

    def test_a_different_signature_does_not_dismiss(self):
        from experiments.tabbing.runner.bakeoff import upstream_stage4

        passes = {
            "f": self._pass(mouse_changed={"dom"}, mouse_coverage=frozenset({"a"})),
            "k": self._pass(
                keyboard_changed={"console"}, keyboard_coverage=frozenset({"a"}), in_tab_order=True
            ),
        }
        assert upstream_stage4(passes)[0] == {"f"}

    def test_overlapping_but_unequal_coverage_does_not_dismiss(self):
        from experiments.tabbing.runner.bakeoff import upstream_stage4

        passes = {
            "f": self._pass(mouse_changed={"dom"}, mouse_coverage=frozenset({"a"})),
            "k": self._pass(
                keyboard_changed={"dom"},
                keyboard_coverage=frozenset({"a", "b"}),
                in_tab_order=True,
            ),
        }
        assert upstream_stage4(passes)[0] == {"f"}

    def test_a_candidate_with_no_coverage_is_skipped(self):
        from experiments.tabbing.runner.bakeoff import upstream_stage4

        passes = {
            "f": self._pass(mouse_changed={"dom"}, mouse_coverage=frozenset({"a"})),
            "k": self._pass(keyboard_changed={"dom"}, in_tab_order=True),
        }
        assert upstream_stage4(passes)[0] == {"f"}

    def test_a_finding_without_coverage_is_kept_not_dismissed(self):
        from experiments.tabbing.runner.bakeoff import upstream_stage4

        passes = {
            "f": self._pass(mouse_changed={"dom"}),
            "k": self._pass(
                keyboard_changed={"dom"}, keyboard_coverage=frozenset({"a"}), in_tab_order=True
            ),
        }
        assert upstream_stage4(passes)[0] == {"f"}

    def test_a_candidate_outside_the_tab_order_cannot_dismiss(self):
        from experiments.tabbing.runner.bakeoff import upstream_stage4

        passes = {
            "f": self._pass(mouse_changed={"dom"}, mouse_coverage=frozenset({"a"})),
            "k": self._pass(keyboard_changed={"dom"}, keyboard_coverage=frozenset({"a"})),
        }
        assert upstream_stage4(passes)[0] == {"f"}


class TestUpstreamDeltaMatchesInstrumentTs:
    """`upstream_delta` must mirror instrument.ts `delta()`, nav rule included."""

    def _snap(self, **kw):
        base = {
            "dom": 1,
            "geometry": 2,
            "mutations": 0,
            "net": 0,
            "storage": 0,
            "console": 0,
            "canvas": 0,
            "nav": 0,
            "href": "u",
        }
        base.update(kw)
        return base

    def test_counters_fire_only_when_strictly_greater(self):
        from experiments.tabbing.runner.bakeoff import upstream_delta

        assert upstream_delta(self._snap(net=1), self._snap(net=1)) == set()
        assert upstream_delta(self._snap(net=1), self._snap(net=2)) == {"net"}

    def test_a_pushstate_to_the_same_url_still_counts_as_nav(self):
        """The case a href-only comparison misses entirely."""
        from experiments.tabbing.runner.bakeoff import upstream_delta

        assert upstream_delta(self._snap(nav=0), self._snap(nav=1)) == {"nav"}

    def test_an_href_change_counts_as_nav(self):
        from experiments.tabbing.runner.bakeoff import upstream_delta

        assert upstream_delta(self._snap(), self._snap(href="v")) == {"nav"}

    def test_digests_compare_unequal_in_either_direction(self):
        from experiments.tabbing.runner.bakeoff import upstream_delta

        assert upstream_delta(self._snap(dom=1), self._snap(dom=9)) == {"dom"}


class TestUpstreamStage4Wiring:
    """The filtered row must be a subset of what the differential found.

    An ordering slip once computed this row *after* scoring, so it was scored
    from an empty reported set and published as 0.0% recall with 39 false
    negatives — a number that looks like a finding and is a wiring bug.
    """

    def test_kept_is_a_subset_of_confirmed(self):
        from experiments.tabbing.runner.bakeoff import UpstreamPass, upstream_stage4

        passes = {
            "a": UpstreamPass(mouse_changed={"dom"}, mouse_coverage=frozenset({"x"})),
            "b": UpstreamPass(mouse_changed={"net"}, mouse_coverage=frozenset({"y"})),
            "k": UpstreamPass(
                keyboard_changed={"dom"}, keyboard_coverage=frozenset({"x"}), in_tab_order=True
            ),
        }
        confirmed = {pid for pid, up in passes.items() if up.reported}
        kept, dismissed = upstream_stage4(passes)
        assert kept <= confirmed
        assert kept | set(dismissed) == confirmed, "every finding is kept or dismissed, never lost"
        assert kept, "a pool with no equivalent control must keep something"
