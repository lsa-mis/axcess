"""Hard quality gate for the versioned labeled detector-output corpus."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from audit.quality_benchmark import (
    BenchmarkError,
    BenchmarkObservation,
    DetectionLayer,
    ReferenceLabel,
    SystemDisposition,
    evaluate,
    format_report,
    gate_failures,
    load_corpus,
)

CORPUS_PATH = Path(__file__).parent / "corpora" / "detection_precision_v1.json"


def test_versioned_labeled_corpus_meets_less_than_five_percent_gate() -> None:
    corpus = load_corpus(CORPUS_PATH)
    report = evaluate(corpus)

    assert corpus.schema_version == 1
    assert corpus.corpus_version == "1.0.2"
    assert corpus.label_method == "synthetic_by_construction"
    assert gate_failures(corpus, report) == ()
    assert report.overall.false_discovery_rate is not None
    assert report.overall.false_discovery_rate < 0.05

    # The aggregate cannot hide a noisy model/probe family. Every report-facing
    # layer independently meets the strict (<, not <=) target and size floors.
    assert set(report.by_layer) == set(DetectionLayer)
    assert set(report.by_pipeline) == {
        "alfa",
        "axe",
        "focus",
        "image",
        "keyboard",
        "responsive",
        "semantic",
        "visual",
    }
    for metrics in report.by_layer.values():
        assert metrics.false_discovery_rate is not None
        assert metrics.false_discovery_rate < 0.05
        assert metrics.surfaced >= corpus.gate.min_surfaced_per_layer
        assert metrics.negative_controls >= corpus.gate.min_negative_controls_per_layer


def test_report_keeps_false_discovery_and_false_positive_rates_distinct() -> None:
    corpus = load_corpus(CORPUS_PATH)
    base = corpus.observations[0]
    observations = (
        base,
        replace(
            base,
            sample_id="false-positive",
            reference_label=ReferenceLabel.NOT_A_BARRIER,
        ),
        replace(
            base,
            sample_id="true-negative-1",
            reference_label=ReferenceLabel.NOT_A_BARRIER,
            system_disposition=SystemDisposition.SUPPRESSED,
        ),
        replace(
            base,
            sample_id="true-negative-2",
            reference_label=ReferenceLabel.NOT_A_BARRIER,
            system_disposition=SystemDisposition.SUPPRESSED,
        ),
        replace(
            base,
            sample_id="true-negative-3",
            reference_label=ReferenceLabel.NOT_A_BARRIER,
            system_disposition=SystemDisposition.SUPPRESSED,
        ),
    )
    metrics = evaluate(replace(corpus, observations=observations)).overall

    assert metrics.precision == pytest.approx(0.5)
    assert metrics.false_discovery_rate == pytest.approx(0.5)  # 1 / 2 surfaced
    assert metrics.false_positive_rate == pytest.approx(0.25)  # 1 / 4 negatives


def test_exactly_five_percent_fails_the_strict_target() -> None:
    corpus = load_corpus(CORPUS_PATH)
    axe = next(item for item in corpus.observations if item.layer is DetectionLayer.AXE)
    observations = (
        *(replace(axe, sample_id=f"strict-{index}") for index in range(19)),
        replace(
            axe,
            sample_id="strict-false-positive",
            reference_label=ReferenceLabel.NOT_A_BARRIER,
        ),
    )
    metrics_corpus = replace(corpus, observations=observations)
    failures = gate_failures(metrics_corpus, evaluate(metrics_corpus))

    assert any("overall: false-discovery rate 5.0% is not below 5.0%" in item for item in failures)


def test_quality_gate_cannot_pass_by_suppressing_everything() -> None:
    corpus = load_corpus(CORPUS_PATH)
    suppressed = tuple(
        replace(item, system_disposition=SystemDisposition.SUPPRESSED)
        for item in corpus.observations
    )
    changed = replace(corpus, observations=suppressed)
    failures = gate_failures(changed, evaluate(changed))

    assert any("no surfaced results" in item for item in failures)
    assert any("only 0 surfaced labels" in item for item in failures)
    assert any("recall 0.0%" in item for item in failures)


def test_rule_diagnostics_identify_the_pipeline_and_rule() -> None:
    corpus = load_corpus(CORPUS_PATH)
    semantic = next(
        item
        for item in corpus.observations
        if item.pipeline == "semantic" and item.rule_id == "semantic:2.4.6"
    )
    changed = replace(
        corpus,
        observations=(
            *corpus.observations,
            replace(
                semantic,
                sample_id="semantic-heading-known-fp",
                reference_label=ReferenceLabel.NOT_A_BARRIER,
            ),
        ),
    )
    report = evaluate(changed)
    rendered = format_report(changed, report)

    diagnostics = report.by_rule[("semantic", "semantic:2.4.6")]
    assert diagnostics.false_positives == 1
    assert "semantic     semantic:2.4.6" in rendered
    assert "Rule diagnostics" in rendered
    assert "image:informational_inadequate" in rendered


def test_loader_rejects_duplicate_sample_ids(tmp_path: Path) -> None:
    payload = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    duplicate = payload["cohorts"][0]["sample_ids"][0]
    payload["cohorts"][1]["sample_ids"][0] = duplicate
    path = tmp_path / "duplicate.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(BenchmarkError, match="duplicate sample_id"):
        load_corpus(path)


def test_loader_rejects_a_pipeline_masquerading_as_another_layer(tmp_path: Path) -> None:
    payload = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    payload["cohorts"][0]["pipeline"] = "semantic"
    path = tmp_path / "wrong-layer.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(BenchmarkError, match="not valid for layer"):
        load_corpus(path)


def test_loader_rejects_model_output_presented_as_a_conformance_finding(tmp_path: Path) -> None:
    payload = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    semantic = next(cohort for cohort in payload["cohorts"] if cohort["layer"] == "semantic")
    semantic["system_disposition"] = "finding"
    path = tmp_path / "semantic-verdict.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(BenchmarkError, match="must be review leads"):
        load_corpus(path)


def test_loader_rejects_behavioral_probe_presented_as_a_conformance_finding(
    tmp_path: Path,
) -> None:
    payload = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    behavioral = next(cohort for cohort in payload["cohorts"] if cohort["layer"] == "behavioral")
    behavioral["system_disposition"] = "finding"
    path = tmp_path / "behavioral-verdict.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(BenchmarkError, match="must be review leads"):
        load_corpus(path)


def test_observation_shape_remains_explicit() -> None:
    observation = BenchmarkObservation(
        sample_id="example",
        layer=DetectionLayer.SEMANTIC,
        pipeline="semantic",
        rule_id="semantic:2.4.4",
        reference_label=ReferenceLabel.CONFIRMED_BARRIER,
        system_disposition=SystemDisposition.REVIEW_LEAD,
        scenario="Ambiguous link purpose known from the constructed fixture.",
    )

    assert observation.system_disposition.surfaced
