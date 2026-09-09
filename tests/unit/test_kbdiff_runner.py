"""Scoring and evidence must remain complete when the measurement harness fails."""

import json

# The optional experiment is outside the installed audit package.
import sys
from dataclasses import replace
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from audit.analyzer.keyboard.kbdiff.model import Effect, ModalityResult, ProbeOutcome, Verdict

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from experiments.tabbing.runner import main, run
from experiments.tabbing.runner.corpus import Corpus, Probe
from experiments.tabbing.runner.provenance import require_new_outputs, write_new
from experiments.tabbing.runner.serve import is_fixture_origin


@pytest.fixture
def corpus(tmp_path):
    return Corpus(
        root=tmp_path,
        probes={
            pid: Probe(pid, "page.html", label, "holdout", {})
            for pid, label in [("a", "violation"), ("b", "ok")]
        },
        pages={"page.html": ["a", "b"]},
        corpus_sha256="frozen",
    )


def outcome(pid="a", verdict=Verdict.VIOLATION, *, viewport="desktop"):
    return ProbeOutcome(
        pid,
        "page.html",
        viewport,
        False,
        None,
        ModalityResult(True, Effect(frozenset({"dom"}), {"dom": ("changed",)})),
        {},
        verdict,
    )


def all_score(scores, mode="oracle"):
    return next(s for s in scores if s.cohort == "all" and s.mode == mode)


def test_missing_entire_page_stays_in_denominator(corpus):
    state = run.RunState()
    scores = run.score_run(corpus, state, ["desktop"])
    score = all_score(scores)
    assert (score.total, score.unknown_positive, score.unknown_negative) == (2, 1, 1)
    assert score.recall == 0
    assert len(state.outcomes) == 2


def test_missing_positive_cannot_inflate_recall(corpus):
    corpus = replace(
        corpus, probes={k: replace(p, label="violation") for k, p in corpus.probes.items()}
    )
    state = run.RunState(outcomes=[outcome()], candidates_by_page={"page.html@desktop": ["a"]})
    score = all_score(run.score_run(corpus, state, ["desktop"]))
    assert (score.tp, score.unknown_positive, score.total, score.recall) == (1, 1, 2, 0.5)


def test_failed_discovery_is_unknown_not_absent(corpus):
    state = run.RunState(
        outcomes=[outcome(), outcome("b", Verdict.NO_LEAD)],
        candidates_by_page={"page.html@desktop": None},
    )
    scores = run.score_run(corpus, state, ["desktop"])
    assert all_score(scores).tp == 1
    assert all_score(scores, "end_to_end").unknown == 2


def test_successful_empty_discovery_withholds_alert(corpus):
    state = run.RunState(
        outcomes=[outcome(), outcome("b", Verdict.NO_LEAD)],
        candidates_by_page={"page.html@desktop": []},
    )
    scores = run.score_run(corpus, state, ["desktop"])
    assert all_score(scores, "end_to_end").fn == 1
    assert all_score(scores, "end_to_end").unknown == 0


def test_saved_outcomes_follow_equivalence_per_viewport(corpus):
    mouse = outcome()
    alternate = replace(
        outcome("b", Verdict.NO_LEAD),
        in_tab_order=True,
        tab_index=1,
        keyboard_by_key={"Enter": ModalityResult(True, mouse.mouse.effect)},
    )
    state = run.RunState(
        outcomes=[mouse, alternate], candidates_by_page={"page.html@desktop": ["a", "b"]}
    )
    scores = run.score_run(corpus, state, ["desktop"])
    assert state.outcomes[0].verdict is Verdict.NO_LEAD
    assert all_score(scores).tp == 0
    assert state.dismissals[0]["viewport"] == "desktop"
    assert state.dismissals[0]["page"] == "page.html"
    assert run.score_run(corpus, state, ["desktop"]) == scores
    saved = run.serialize_outcome(alternate)
    assert saved["schema_version"] == 2
    assert saved["mouse_effect"] == saved["keyboard_by_key"]["Enter"]["effect"]
    assert "keyboard_effect" not in saved


def test_duplicate_or_out_of_scope_measurement_rejected(corpus):
    with pytest.raises(ValueError, match="duplicate"):
        run.complete_outcomes(corpus, [outcome(), outcome()], ["desktop"])
    with pytest.raises(ValueError, match="scope"):
        run.complete_outcomes(corpus, [replace(outcome(), page="wrong.html")], ["desktop"])


@pytest.mark.asyncio
async def test_tab_order_exception_produces_unknown_rows(corpus, monkeypatch):
    runner = AsyncMock()
    runner.tab_order.side_effect = RuntimeError("instrument unavailable")
    monkeypatch.setattr(run, "DifferentialRunner", lambda *args: runner)
    factory = AsyncMock()
    state = run.RunState()
    await run._run_page(
        state, corpus, factory, "page.html", ["a", "b"], "desktop", max_tabs=10, settle_ms=0
    )
    assert len(state.outcomes) == 2
    assert all(o.verdict is Verdict.UNKNOWN for o in state.outcomes)
    assert state.errors[0]["stage"] == "tab_order"
    assert factory.close_open_contexts.await_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("changed", [False, True])
async def test_cli_serializes_complete_evidence_and_rejects_source_drift(
    corpus, tmp_path, monkeypatch, changed
):
    before = {"detector": {"_combined": "a"}, "runner": {"_combined": "b"}}
    after = (
        {"detector": {"_combined": "changed"}, "runner": {"_combined": "b"}} if changed else before
    )
    monkeypatch.setattr(main, "IMPORT_FINGERPRINT", before)
    versions = iter([before, after])
    monkeypatch.setattr(main, "source_sha256", lambda: next(versions))
    monkeypatch.setattr(main, "load_corpus", lambda path: corpus)
    state = run.RunState(
        outcomes=[outcome(), outcome("b", Verdict.NO_LEAD)],
        candidates_by_page={"page.html@desktop": ["a"]},
        browser_version="browser-test",
    )
    monkeypatch.setattr(main, "run_corpus", AsyncMock(return_value=state))
    args = main.parser().parse_args(
        ["--out", str(tmp_path), "--label", "test", "--viewport", "desktop"]
    )
    status = await main._main(args)
    payload = json.loads((tmp_path / "test.raw.json").read_text())
    assert status == int(changed)
    assert payload["run"]["valid"] is not changed
    assert payload["run"]["started_utc"] <= payload["run"]["finished_utc"]
    assert payload["run"]["versions"]["chromium"] == "browser-test"
    assert payload["candidates_by_page"] == {"page.html@desktop": ["a"]}
    assert len(payload["probes"]) == len(payload["candidate_gated_probes"]) == 2
    assert bool(payload["scores"]) is not changed


def test_existing_result_is_never_overwritten(tmp_path):
    path = tmp_path / "result.json"
    write_new(path, "first")
    with pytest.raises(FileExistsError):
        require_new_outputs(path)
    with pytest.raises(FileExistsError):
        write_new(path, "second")
    assert path.read_text() == "first"


@pytest.mark.parametrize(
    "args",
    [["--max-tabs", "0"], ["--settle-ms", "-1"], ["--label", "../old"], ["--run-timeout", "99999"]],
)
def test_cli_rejects_invalid_bounds_and_labels(args):
    with pytest.raises(SystemExit):
        main.parser().parse_args(args)


@pytest.mark.parametrize(
    "url",
    [
        "https://tabbing.axcess.test.evil.invalid/a",
        "https://tabbing.axcess.test@evil.invalid/a",
        "http://tabbing.axcess.test/a",
        "https://tabbing.axcess.test:444/a",
    ],
)
def test_lookalike_origins_are_rejected(url):
    assert not is_fixture_origin(url)


def test_exact_https_origin_is_allowed():
    assert is_fixture_origin("https://tabbing.axcess.test:443/a?b=1")
