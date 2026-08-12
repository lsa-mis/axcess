"""Versioned, labeled precision benchmark for Axcess detection outputs.

The benchmark deliberately measures the *share of surfaced results that are
wrong* (the false-discovery rate), because that is the number an auditor feels
as report noise.  It also reports the statistical false-positive rate
(``FP / (FP + TN)``) separately; calling the former an FPR would be misleading.

This module does not run a crawler or claim real-world conformance accuracy.
It evaluates frozen detector-output snapshots against independently recorded
labels.  The corpus metadata states how those labels were obtained and its
limitations.  A production claim requires a representative, expert-labeled
U-M corpus in addition to the synthetic regression corpus shipped here.
"""

from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, TypeAlias, TypeVar


class BenchmarkError(ValueError):
    """The benchmark corpus is malformed or cannot support its quality claim."""


class ReferenceLabel(StrEnum):
    """Binary reference decision assigned before benchmark scoring."""

    CONFIRMED_BARRIER = "confirmed_barrier"
    NOT_A_BARRIER = "not_a_barrier"


class SystemDisposition(StrEnum):
    """What Axcess did with one detector observation."""

    FINDING = "finding"
    REVIEW_LEAD = "review_lead"
    SUPPRESSED = "suppressed"

    @property
    def surfaced(self) -> bool:
        return self is not SystemDisposition.SUPPRESSED


class DetectionLayer(StrEnum):
    """Report-facing layers whose calibration must remain visible."""

    AXE = "axe"
    ALFA = "alfa"
    BEHAVIORAL = "behavioral"
    OCR_VLM = "ocr_vlm"
    SEMANTIC = "semantic"


_LAYER_PIPELINES: dict[DetectionLayer, frozenset[str]] = {
    DetectionLayer.AXE: frozenset({"axe"}),
    DetectionLayer.ALFA: frozenset({"alfa"}),
    DetectionLayer.BEHAVIORAL: frozenset({"keyboard", "responsive", "focus", "visual"}),
    DetectionLayer.OCR_VLM: frozenset({"image", "visual"}),
    DetectionLayer.SEMANTIC: frozenset({"semantic"}),
}
# Browser probes are repeatable observations, but their heuristics do not see
# the complete interaction state or assistive-technology behavior.  Keep them
# in the same expert-confirmation lane as model-assisted evidence.  This must
# stay aligned with ``audit.web.issues`` so a benchmark cannot bless stronger
# report language than the product actually permits.
_REVIEW_ONLY_LAYERS = frozenset(
    {DetectionLayer.BEHAVIORAL, DetectionLayer.OCR_VLM, DetectionLayer.SEMANTIC}
)
_FINDING_ONLY_LAYERS = frozenset({DetectionLayer.AXE})


@dataclass(frozen=True, slots=True)
class BenchmarkGate:
    """Point-estimate gate plus corpus-size anti-gaming guards."""

    max_false_discovery_rate_exclusive: float
    min_surfaced_per_layer: int
    min_negative_controls_per_layer: int
    min_recall: float


@dataclass(frozen=True, slots=True)
class BenchmarkObservation:
    """One independently named labeled observation in the frozen snapshot."""

    sample_id: str
    layer: DetectionLayer
    pipeline: str
    rule_id: str
    reference_label: ReferenceLabel
    system_disposition: SystemDisposition
    scenario: str


@dataclass(frozen=True, slots=True)
class BenchmarkCorpus:
    """Validated benchmark data and the limitations attached to its result."""

    schema_version: int
    corpus_id: str
    corpus_version: str
    label_method: str
    scope_statement: str
    limitations: tuple[str, ...]
    producers: dict[str, str]
    gate: BenchmarkGate
    observations: tuple[BenchmarkObservation, ...]


@dataclass(frozen=True, slots=True)
class QualityMetrics:
    """Binary classification metrics for one scope of observations."""

    total: int
    surfaced: int
    suppressed: int
    true_positives: int
    false_positives: int
    true_negatives: int
    false_negatives: int

    @property
    def precision(self) -> float | None:
        return _safe_ratio(self.true_positives, self.true_positives + self.false_positives)

    @property
    def false_discovery_rate(self) -> float | None:
        """Share of surfaced findings/leads that the reference label rejects."""

        return _safe_ratio(self.false_positives, self.true_positives + self.false_positives)

    @property
    def false_positive_rate(self) -> float | None:
        """Statistical FPR: rejected outputs divided by all negative controls."""

        return _safe_ratio(self.false_positives, self.false_positives + self.true_negatives)

    @property
    def recall(self) -> float | None:
        return _safe_ratio(self.true_positives, self.true_positives + self.false_negatives)

    @property
    def negative_controls(self) -> int:
        return self.false_positives + self.true_negatives


RuleKey: TypeAlias = tuple[str, str]
_EnumT = TypeVar("_EnumT", bound=StrEnum)


@dataclass(frozen=True, slots=True)
class BenchmarkReport:
    """Aggregate and diagnostic metrics for one corpus evaluation."""

    corpus_id: str
    corpus_version: str
    scope_statement: str
    limitations: tuple[str, ...]
    overall: QualityMetrics
    by_layer: dict[DetectionLayer, QualityMetrics]
    by_pipeline: dict[str, QualityMetrics]
    by_rule: dict[RuleKey, QualityMetrics]


def load_corpus(path: Path) -> BenchmarkCorpus:
    """Load and fully validate a schema-v1 JSON corpus."""

    try:
        raw: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BenchmarkError(f"could not read benchmark corpus: {exc}") from exc
    if not isinstance(raw, dict):
        raise BenchmarkError("benchmark root must be a JSON object")
    if raw.get("schema_version") != 1:
        raise BenchmarkError("unsupported benchmark schema_version; expected 1")

    corpus_id = _required_string(raw, "corpus_id")
    corpus_version = _required_string(raw, "corpus_version")
    label_method = _required_string(raw, "label_method")
    scope_statement = _required_string(raw, "scope_statement")
    limitations = _string_tuple(raw.get("limitations"), field="limitations", minimum=1)
    producers = _string_mapping(raw.get("producers"), field="producers")
    gate = _parse_gate(raw.get("gate"))

    raw_cohorts = raw.get("cohorts")
    if not isinstance(raw_cohorts, list) or not raw_cohorts:
        raise BenchmarkError("cohorts must be a non-empty array")
    observations: list[BenchmarkObservation] = []
    seen_samples: set[str] = set()
    for index, value in enumerate(raw_cohorts):
        if not isinstance(value, dict):
            raise BenchmarkError(f"cohorts[{index}] must be an object")
        layer = _enum_value(DetectionLayer, value.get("layer"), f"cohorts[{index}].layer")
        pipeline = _required_string(value, "pipeline", prefix=f"cohorts[{index}].")
        if pipeline not in _LAYER_PIPELINES[layer]:
            raise BenchmarkError(
                f"cohorts[{index}]: pipeline {pipeline!r} is not valid for layer {layer.value!r}"
            )
        rule_id = _required_string(value, "rule_id", prefix=f"cohorts[{index}].")
        scenario = _required_string(value, "scenario", prefix=f"cohorts[{index}].")
        reference = _enum_value(
            ReferenceLabel,
            value.get("reference_label"),
            f"cohorts[{index}].reference_label",
        )
        disposition = _enum_value(
            SystemDisposition,
            value.get("system_disposition"),
            f"cohorts[{index}].system_disposition",
        )
        if (
            disposition.surfaced
            and layer in _REVIEW_ONLY_LAYERS
            and disposition is not SystemDisposition.REVIEW_LEAD
        ):
            raise BenchmarkError(
                f"cohorts[{index}]: {layer.value} outputs must be review leads, "
                "not conformance findings"
            )
        if (
            disposition.surfaced
            and layer in _FINDING_ONLY_LAYERS
            and disposition is not SystemDisposition.FINDING
        ):
            raise BenchmarkError(
                f"cohorts[{index}]: {layer.value} deterministic outputs must be findings"
            )
        sample_ids = _string_tuple(
            value.get("sample_ids"),
            field=f"cohorts[{index}].sample_ids",
            minimum=1,
        )
        for sample_id in sample_ids:
            if sample_id in seen_samples:
                raise BenchmarkError(f"duplicate sample_id: {sample_id}")
            seen_samples.add(sample_id)
            observations.append(
                BenchmarkObservation(
                    sample_id=sample_id,
                    layer=layer,
                    pipeline=pipeline,
                    rule_id=rule_id,
                    reference_label=reference,
                    system_disposition=disposition,
                    scenario=scenario,
                )
            )

    missing_layers = set(DetectionLayer) - {item.layer for item in observations}
    if missing_layers:
        names = ", ".join(sorted(layer.value for layer in missing_layers))
        raise BenchmarkError(f"corpus is missing required detection layer(s): {names}")
    return BenchmarkCorpus(
        schema_version=1,
        corpus_id=corpus_id,
        corpus_version=corpus_version,
        label_method=label_method,
        scope_statement=scope_statement,
        limitations=limitations,
        producers=producers,
        gate=gate,
        observations=tuple(observations),
    )


def evaluate(corpus: BenchmarkCorpus) -> BenchmarkReport:
    """Calculate overall, layer, pipeline, and rule-level diagnostics."""

    by_layer: defaultdict[DetectionLayer, list[BenchmarkObservation]] = defaultdict(list)
    by_pipeline: defaultdict[str, list[BenchmarkObservation]] = defaultdict(list)
    by_rule: defaultdict[RuleKey, list[BenchmarkObservation]] = defaultdict(list)
    for observation in corpus.observations:
        by_layer[observation.layer].append(observation)
        by_pipeline[observation.pipeline].append(observation)
        by_rule[(observation.pipeline, observation.rule_id)].append(observation)
    return BenchmarkReport(
        corpus_id=corpus.corpus_id,
        corpus_version=corpus.corpus_version,
        scope_statement=corpus.scope_statement,
        limitations=corpus.limitations,
        overall=_metrics(corpus.observations),
        by_layer={key: _metrics(value) for key, value in sorted(by_layer.items())},
        by_pipeline={key: _metrics(value) for key, value in sorted(by_pipeline.items())},
        by_rule={key: _metrics(value) for key, value in sorted(by_rule.items())},
    )


def gate_failures(corpus: BenchmarkCorpus, report: BenchmarkReport) -> tuple[str, ...]:
    """Return actionable gate failures; an empty tuple means the corpus passes."""

    failures: list[str] = []
    _check_metric_threshold(
        failures,
        scope="overall",
        metrics=report.overall,
        gate=corpus.gate,
        enforce_sample_floor=False,
    )
    for layer in DetectionLayer:
        metrics = report.by_layer.get(layer)
        if metrics is None:
            failures.append(f"{layer.value}: no labeled observations")
            continue
        _check_metric_threshold(
            failures,
            scope=layer.value,
            metrics=metrics,
            gate=corpus.gate,
            enforce_sample_floor=True,
        )
    return tuple(failures)


def format_report(corpus: BenchmarkCorpus, report: BenchmarkReport) -> str:
    """Render a deterministic terminal report with rule-level diagnostics."""

    failures = gate_failures(corpus, report)
    lines = [
        f"Axcess labeled detector benchmark: {report.corpus_id}@{report.corpus_version}",
        f"Scope: {report.scope_statement}",
        (
            "Gate: false-discovery rate must be < "
            f"{corpus.gate.max_false_discovery_rate_exclusive:.1%} in every layer; "
            "this is a labeled-corpus point estimate, not a real-world accuracy claim."
        ),
        "",
        "Layer          Surfaced  TP  FP  Precision    FDR    FPR  Recall",
    ]
    for layer in DetectionLayer:
        metrics = report.by_layer[layer]
        lines.append(_format_metric_row(layer.value, metrics))
    pipeline_width = max(12, *(len(pipeline) for pipeline, _ in report.by_rule))
    rule_width = max(28, *(len(rule_id) for _, rule_id in report.by_rule))
    lines.extend(
        [
            "",
            "Rule diagnostics",
            (
                f"{'Pipeline':<{pipeline_width}} {'Rule':<{rule_width}} "
                " N  Sh  TP  FP  TN  FN    FDR"
            ),
        ]
    )
    for (pipeline, rule_id), metrics in report.by_rule.items():
        lines.append(
            f"{pipeline:<{pipeline_width}} {rule_id:<{rule_width}} {metrics.total:>2} "
            f"{metrics.surfaced:>3} {metrics.true_positives:>3} "
            f"{metrics.false_positives:>3} {metrics.true_negatives:>3} "
            f"{metrics.false_negatives:>3} "
            f"{_percent(metrics.false_discovery_rate):>6}"
        )
    lines.extend(["", "Limitations"])
    lines.extend(f"- {limitation}" for limitation in report.limitations)
    lines.append("")
    if failures:
        lines.append("FAIL")
        lines.extend(f"- {failure}" for failure in failures)
    else:
        lines.append("PASS — all labeled-corpus quality gates met.")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point used by ``make quality-gate``."""

    parser = argparse.ArgumentParser(description="Evaluate an Axcess labeled detector corpus")
    parser.add_argument("corpus", type=Path)
    args = parser.parse_args(argv)
    try:
        corpus = load_corpus(args.corpus)
        report = evaluate(corpus)
    except BenchmarkError as exc:
        parser.error(str(exc))
    print(format_report(corpus, report))
    return 1 if gate_failures(corpus, report) else 0


def _metrics(
    observations: tuple[BenchmarkObservation, ...] | list[BenchmarkObservation],
) -> QualityMetrics:
    tp = fp = tn = fn = surfaced = 0
    for observation in observations:
        if observation.system_disposition.surfaced:
            surfaced += 1
            if observation.reference_label is ReferenceLabel.CONFIRMED_BARRIER:
                tp += 1
            else:
                fp += 1
        elif observation.reference_label is ReferenceLabel.CONFIRMED_BARRIER:
            fn += 1
        else:
            tn += 1
    return QualityMetrics(
        total=len(observations),
        surfaced=surfaced,
        suppressed=len(observations) - surfaced,
        true_positives=tp,
        false_positives=fp,
        true_negatives=tn,
        false_negatives=fn,
    )


def _check_metric_threshold(
    failures: list[str],
    *,
    scope: str,
    metrics: QualityMetrics,
    gate: BenchmarkGate,
    enforce_sample_floor: bool,
) -> None:
    fdr = metrics.false_discovery_rate
    if fdr is None:
        failures.append(f"{scope}: no surfaced results, so precision is undefined")
    elif fdr >= gate.max_false_discovery_rate_exclusive:
        failures.append(
            f"{scope}: false-discovery rate {_percent(fdr)} is not below "
            f"{_percent(gate.max_false_discovery_rate_exclusive)}"
        )
    recall = metrics.recall
    if recall is None or recall < gate.min_recall:
        failures.append(f"{scope}: recall {_percent(recall)} is below {_percent(gate.min_recall)}")
    if enforce_sample_floor and metrics.surfaced < gate.min_surfaced_per_layer:
        failures.append(
            f"{scope}: only {metrics.surfaced} surfaced labels; need {gate.min_surfaced_per_layer}"
        )
    if enforce_sample_floor and metrics.negative_controls < gate.min_negative_controls_per_layer:
        failures.append(
            f"{scope}: only {metrics.negative_controls} negative controls; "
            f"need {gate.min_negative_controls_per_layer}"
        )


def _parse_gate(value: Any) -> BenchmarkGate:
    if not isinstance(value, dict):
        raise BenchmarkError("gate must be an object")
    max_fdr = _finite_rate(value.get("max_false_discovery_rate_exclusive"), "gate FDR")
    if not 0 < max_fdr < 1:
        raise BenchmarkError("gate FDR must be greater than 0 and less than 1")
    min_recall = _finite_rate(value.get("min_recall"), "gate recall")
    minimum_surfaced = _positive_int(value.get("min_surfaced_per_layer"), "gate surfaced")
    minimum_negatives = _positive_int(
        value.get("min_negative_controls_per_layer"), "gate negative controls"
    )
    return BenchmarkGate(max_fdr, minimum_surfaced, minimum_negatives, min_recall)


def _required_string(value: dict[str, Any], field: str, *, prefix: str = "") -> str:
    result = value.get(field)
    if not isinstance(result, str) or not result.strip():
        raise BenchmarkError(f"{prefix}{field} must be a non-empty string")
    return result.strip()


def _string_tuple(value: Any, *, field: str, minimum: int) -> tuple[str, ...]:
    if not isinstance(value, list) or len(value) < minimum:
        raise BenchmarkError(f"{field} must contain at least {minimum} string(s)")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise BenchmarkError(f"{field} entries must be non-empty strings")
        result.append(item.strip())
    if len(set(result)) != len(result):
        raise BenchmarkError(f"{field} contains duplicate entries")
    return tuple(result)


def _string_mapping(value: Any, *, field: str) -> dict[str, str]:
    if not isinstance(value, dict) or not value:
        raise BenchmarkError(f"{field} must be a non-empty string mapping")
    result: dict[str, str] = {}
    for key, item in value.items():
        if (
            not isinstance(key, str)
            or not key.strip()
            or not isinstance(item, str)
            or not item.strip()
        ):
            raise BenchmarkError(f"{field} keys and values must be non-empty strings")
        result[key.strip()] = item.strip()
    return result


def _enum_value(enum_type: type[_EnumT], value: Any, field: str) -> _EnumT:
    try:
        return enum_type(value)
    except (TypeError, ValueError) as exc:
        allowed = ", ".join(item.value for item in enum_type)
        raise BenchmarkError(f"{field} must be one of: {allowed}") from exc


def _finite_rate(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise BenchmarkError(f"{field} must be a number")
    result = float(value)
    if not math.isfinite(result) or not 0 <= result <= 1:
        raise BenchmarkError(f"{field} must be a finite rate between 0 and 1")
    return result


def _positive_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise BenchmarkError(f"{field} must be a positive integer")
    return int(value)


def _safe_ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _percent(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.1%}"


def _format_metric_row(label: str, metrics: QualityMetrics) -> str:
    return (
        f"{label[:14]:<14} {metrics.surfaced:>8} {metrics.true_positives:>3} "
        f"{metrics.false_positives:>3} {_percent(metrics.precision):>10} "
        f"{_percent(metrics.false_discovery_rate):>6} "
        f"{_percent(metrics.false_positive_rate):>6} {_percent(metrics.recall):>7}"
    )


if __name__ == "__main__":  # pragma: no cover - exercised through the Make target
    raise SystemExit(main())
