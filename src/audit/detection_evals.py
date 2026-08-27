"""Efficacy, efficiency, and scale evaluations for Axcess detection evidence.

The efficacy lane evaluates the versioned labeled detector-output corpus. The
performance lanes exercise the real local evidence boundary: repository writes
to a migrated SQLite database followed by the unified issue projection used by
the report UI. They intentionally do not present shared-runner timings as
browser, OCR, or model inference benchmarks.
"""

from __future__ import annotations

import argparse
import json
import tempfile
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any

from audit.db import repo
from audit.db.schema import connect, transaction
from audit.quality_benchmark import evaluate, gate_failures, load_corpus
from audit.web.issues import list_issues

_MIGRATIONS_DIR = Path(__file__).resolve().parent / "db" / "migrations"
_RULES = (
    ("color-contrast", "1.4.3", "AA", "serious"),
    ("image-alt", "1.1.1", "A", "critical"),
    ("label", "3.3.2", "A", "critical"),
    ("button-name", "4.1.2", "A", "critical"),
)


class DetectionEvalError(ValueError):
    """The evaluation configuration or generated workload is invalid."""


@dataclass(frozen=True, slots=True)
class PerformanceConfig:
    """Versioned workload and coarse regression thresholds."""

    page_counts: tuple[int, ...]
    findings_per_page: int
    efficiency_reference_pages: int
    min_write_findings_per_second: float
    max_projection_seconds: float
    max_per_finding_slowdown: float


@dataclass(frozen=True, slots=True)
class DetectionEvalConfig:
    """Validated configuration for all three evaluation lanes."""

    schema_version: int
    config_version: str
    corpus_path: Path
    performance: PerformanceConfig


@dataclass(frozen=True, slots=True)
class PerformancePoint:
    """One evidence-ingestion and issue-projection workload result."""

    pages: int
    findings_per_page: int
    findings: int
    stored_findings: int
    issue_groups: int
    write_seconds: float
    projection_seconds: float
    write_findings_per_second: float
    database_bytes: int


def load_eval_config(path: Path, *, project_root: Path | None = None) -> DetectionEvalConfig:
    """Load the schema-v1 JSON configuration and resolve its corpus path."""

    try:
        raw: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DetectionEvalError(f"could not read evaluation config: {exc}") from exc
    if not isinstance(raw, dict) or raw.get("schema_version") != 1:
        raise DetectionEvalError("evaluation config must use schema_version 1")
    config_version = _required_string(raw, "config_version")
    efficacy = _required_mapping(raw, "efficacy")
    corpus_value = _required_string(efficacy, "corpus")
    performance_raw = _required_mapping(raw, "performance")
    page_counts = _positive_int_tuple(performance_raw.get("page_counts"), "page_counts")
    if tuple(sorted(set(page_counts))) != page_counts:
        raise DetectionEvalError("page_counts must be unique and strictly increasing")
    reference_pages = _positive_int(
        performance_raw.get("efficiency_reference_pages"),
        "efficiency_reference_pages",
    )
    if reference_pages not in page_counts:
        raise DetectionEvalError("efficiency_reference_pages must be one of page_counts")
    root = project_root or path.resolve().parents[2]
    corpus_path = Path(corpus_value)
    if not corpus_path.is_absolute():
        corpus_path = root / corpus_path
    return DetectionEvalConfig(
        schema_version=1,
        config_version=config_version,
        corpus_path=corpus_path,
        performance=PerformanceConfig(
            page_counts=page_counts,
            findings_per_page=_positive_int(
                performance_raw.get("findings_per_page"), "findings_per_page"
            ),
            efficiency_reference_pages=reference_pages,
            min_write_findings_per_second=_positive_number(
                performance_raw.get("min_write_findings_per_second"),
                "min_write_findings_per_second",
            ),
            max_projection_seconds=_positive_number(
                performance_raw.get("max_projection_seconds"),
                "max_projection_seconds",
            ),
            max_per_finding_slowdown=_positive_number(
                performance_raw.get("max_per_finding_slowdown"),
                "max_per_finding_slowdown",
            ),
        ),
    )


def run_detection_evals(config: DetectionEvalConfig) -> dict[str, Any]:
    """Run all lanes and return a serializable report with explicit failures."""

    corpus = load_corpus(config.corpus_path)
    efficacy_report = evaluate(corpus)
    efficacy_failures = list(gate_failures(corpus, efficacy_report))
    points = [
        _run_performance_point(pages, config.performance.findings_per_page)
        for pages in config.performance.page_counts
    ]
    efficiency_failures, scale_failures = performance_failures(config.performance, points)
    failures = [
        *(f"efficacy: {failure}" for failure in efficacy_failures),
        *(f"efficiency: {failure}" for failure in efficiency_failures),
        *(f"scale: {failure}" for failure in scale_failures),
    ]
    reference = next(
        point for point in points if point.pages == config.performance.efficiency_reference_pages
    )
    smallest = points[0]
    largest = points[-1]
    slowdown = _seconds_per_finding(largest) / _seconds_per_finding(smallest)
    return {
        "schema_version": 1,
        "config_version": config.config_version,
        "generated_at": datetime.now(UTC).isoformat(),
        "status": "pass" if not failures else "fail",
        "efficacy": {
            "corpus_id": corpus.corpus_id,
            "corpus_version": corpus.corpus_version,
            "label_method": corpus.label_method,
            "scope_statement": corpus.scope_statement,
            "overall": _quality_metrics_dict(efficacy_report.overall),
            "by_layer": {
                layer.value: _quality_metrics_dict(metrics)
                for layer, metrics in efficacy_report.by_layer.items()
            },
            "failures": efficacy_failures,
            "limitations": list(corpus.limitations),
        },
        "efficiency": {
            "reference_pages": reference.pages,
            "findings": reference.findings,
            "write_findings_per_second": reference.write_findings_per_second,
            "projection_seconds": reference.projection_seconds,
            "thresholds": {
                "min_write_findings_per_second": (config.performance.min_write_findings_per_second),
                "max_projection_seconds": config.performance.max_projection_seconds,
            },
            "failures": efficiency_failures,
        },
        "scale": {
            "points": [asdict(point) for point in points],
            "normalized_per_finding_slowdown": slowdown,
            "thresholds": {"max_per_finding_slowdown": config.performance.max_per_finding_slowdown},
            "failures": scale_failures,
        },
        "limitations": [
            "Performance points cover local evidence writes and unified issue projection.",
            "They exclude crawling, browser rendering, OCR, and model inference latency.",
            "Shared-runner timings are coarse regression guards, not hardware-neutral claims.",
        ],
        "failures": failures,
    }


def performance_failures(
    config: PerformanceConfig, points: list[PerformancePoint]
) -> tuple[list[str], list[str]]:
    """Separate efficiency and scale failures for clear CI diagnostics."""

    if not points:
        return ["no performance points were produced"], ["no scale points were produced"]
    by_pages = {point.pages: point for point in points}
    if set(by_pages) != set(config.page_counts):
        return [], ["performance points do not match configured page_counts"]
    reference = by_pages[config.efficiency_reference_pages]
    efficiency: list[str] = []
    scale: list[str] = []
    if reference.write_findings_per_second < config.min_write_findings_per_second:
        efficiency.append(
            f"write throughput {reference.write_findings_per_second:.1f}/s is below "
            f"{config.min_write_findings_per_second:.1f}/s"
        )
    if reference.projection_seconds > config.max_projection_seconds:
        efficiency.append(
            f"projection took {reference.projection_seconds:.3f}s; maximum is "
            f"{config.max_projection_seconds:.3f}s"
        )
    for point in points:
        if point.stored_findings != point.findings:
            scale.append(
                f"{point.pages} pages stored {point.stored_findings} of {point.findings} findings"
            )
        if point.issue_groups != len(_RULES):
            scale.append(
                f"{point.pages} pages produced {point.issue_groups} issue groups; "
                f"expected {len(_RULES)}"
            )
    slowdown = _seconds_per_finding(points[-1]) / _seconds_per_finding(points[0])
    if slowdown > config.max_per_finding_slowdown:
        scale.append(
            f"normalized write slowdown {slowdown:.2f}x exceeds "
            f"{config.max_per_finding_slowdown:.2f}x"
        )
    return efficiency, scale


def format_markdown(report: dict[str, Any]) -> str:
    """Render the combined report for local review and GitHub job summaries."""

    efficacy = report["efficacy"]
    efficiency = report["efficiency"]
    scale = report["scale"]
    overall = efficacy["overall"]
    lines = [
        "# Axcess detection evaluation",
        "",
        f"**Status:** {str(report['status']).upper()}",
        "",
        "## Efficacy",
        "",
        f"Corpus: `{efficacy['corpus_id']}@{efficacy['corpus_version']}`",
        "",
        "| Precision | FDR | FPR | Recall | Surfaced |",
        "| ---: | ---: | ---: | ---: | ---: |",
        (
            f"| {_percent(overall['precision'])} | "
            f"{_percent(overall['false_discovery_rate'])} | "
            f"{_percent(overall['false_positive_rate'])} | "
            f"{_percent(overall['recall'])} | {overall['surfaced']} |"
        ),
        "",
        "## Efficiency",
        "",
        (
            f"At {efficiency['reference_pages']} pages / {efficiency['findings']} findings: "
            f"**{efficiency['write_findings_per_second']:.1f} findings/s** written; "
            f"issue projection took **{efficiency['projection_seconds']:.3f}s**."
        ),
        "",
        "## Scale",
        "",
        "| Pages | Findings | Stored | Write seconds | Findings/s | Projection seconds |",
        "| ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for point in scale["points"]:
        lines.append(
            f"| {point['pages']} | {point['findings']} | {point['stored_findings']} | "
            f"{point['write_seconds']:.3f} | {point['write_findings_per_second']:.1f} | "
            f"{point['projection_seconds']:.3f} |"
        )
    lines.extend(
        [
            "",
            (
                "Normalized largest/smallest per-finding slowdown: "
                f"**{scale['normalized_per_finding_slowdown']:.2f}x**."
            ),
            "",
            "## Scope limitations",
            "",
            *(f"- {item}" for item in report["limitations"]),
            "",
        ]
    )
    if report["failures"]:
        lines.extend(["## Failures", "", *(f"- {item}" for item in report["failures"]), ""])
    return "\n".join(lines)


def write_reports(report: dict[str, Any], output_dir: Path) -> None:
    """Write deterministic artifact names consumed by GitHub Actions."""

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (output_dir / "report.md").write_text(format_markdown(report), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    """Run the versioned evaluation configuration and produce CI artifacts."""

    parser = argparse.ArgumentParser(description="Run Axcess detection evaluations")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("tests/quality/detection_eval_config.json"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("artifacts/detection-evals"),
    )
    args = parser.parse_args(argv)
    try:
        config = load_eval_config(args.config, project_root=Path.cwd())
        report = run_detection_evals(config)
    except (DetectionEvalError, ValueError) as exc:
        parser.error(str(exc))
    write_reports(report, args.output_dir)
    print(format_markdown(report))
    return 0 if report["status"] == "pass" else 1


def _run_performance_point(pages: int, findings_per_page: int) -> PerformancePoint:
    with tempfile.TemporaryDirectory(prefix="axcess-detection-eval-") as tmp:
        db_path = Path(tmp) / "audit.db"
        conn = connect(db_path)
        try:
            _apply_migrations(conn)
            scan_id = _create_scan(conn, pages)
            write_started = perf_counter()
            with transaction(conn):
                for page_index in range(pages):
                    page_id = repo.upsert_page(
                        conn,
                        scan_id=scan_id,
                        url_normalized=f"https://eval.invalid/page-{page_index}",
                        status_code=200,
                        title=f"Evaluation page {page_index}",
                        render_mode="js",
                        html_hash=f"eval-{page_index:08d}",
                    )
                    for finding_index in range(findings_per_page):
                        rule_id, wcag_sc, wcag_level, impact = _RULES[finding_index % len(_RULES)]
                        repo.upsert_axe_violation(
                            conn,
                            page_id=page_id,
                            scan_id=scan_id,
                            rule_id=rule_id,
                            wcag_sc=wcag_sc,
                            wcag_scs=wcag_sc,
                            wcag_level=wcag_level,
                            impact=impact,
                            help=f"Synthetic {rule_id} benchmark evidence",
                            help_url=f"https://eval.invalid/rules/{rule_id}",
                            target_selector=f"main > :nth-child({finding_index + 1})",
                            failure_summary="Synthetic benchmark observation",
                            html_snippet="<div>benchmark</div>",
                            target_hash=f"{page_index:08d}-{finding_index:04d}",
                        )
            write_seconds = perf_counter() - write_started
            projection_started = perf_counter()
            issue_rows = list_issues(conn, scan_id)
            projection_seconds = perf_counter() - projection_started
            stored_row = conn.execute(
                "SELECT COUNT(*) AS total FROM page_a11y_findings WHERE scan_id = ?",
                (scan_id,),
            ).fetchone()
            stored_findings = int(stored_row["total"])
        finally:
            conn.close()
        findings = pages * findings_per_page
        return PerformancePoint(
            pages=pages,
            findings_per_page=findings_per_page,
            findings=findings,
            stored_findings=stored_findings,
            issue_groups=len(issue_rows),
            write_seconds=write_seconds,
            projection_seconds=projection_seconds,
            write_findings_per_second=findings / max(write_seconds, 1e-9),
            database_bytes=db_path.stat().st_size,
        )


def _apply_migrations(conn: Any) -> None:
    for path in sorted(_MIGRATIONS_DIR.glob("*.sql")):
        if not path.name.endswith(".rollback.sql"):
            conn.executescript(path.read_text(encoding="utf-8"))


def _create_scan(conn: Any, pages: int) -> int:
    cursor = conn.execute(
        """
        INSERT INTO scans (seed_url, status, page_count, finding_count, config_json)
        VALUES ('https://eval.invalid/', 'completed', ?, 0, '{}')
        """,
        (pages,),
    )
    return int(cursor.lastrowid or 0)


def _seconds_per_finding(point: PerformancePoint) -> float:
    return point.write_seconds / max(point.findings, 1)


def _quality_metrics_dict(metrics: Any) -> dict[str, int | float | None]:
    return {
        "total": metrics.total,
        "surfaced": metrics.surfaced,
        "suppressed": metrics.suppressed,
        "true_positives": metrics.true_positives,
        "false_positives": metrics.false_positives,
        "true_negatives": metrics.true_negatives,
        "false_negatives": metrics.false_negatives,
        "precision": metrics.precision,
        "false_discovery_rate": metrics.false_discovery_rate,
        "false_positive_rate": metrics.false_positive_rate,
        "recall": metrics.recall,
    }


def _required_mapping(value: dict[str, Any], field: str) -> dict[str, Any]:
    result = value.get(field)
    if not isinstance(result, dict):
        raise DetectionEvalError(f"{field} must be an object")
    return result


def _required_string(value: dict[str, Any], field: str) -> str:
    result = value.get(field)
    if not isinstance(result, str) or not result.strip():
        raise DetectionEvalError(f"{field} must be a non-empty string")
    return result.strip()


def _positive_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise DetectionEvalError(f"{field} must be a positive integer")
    return int(value)


def _positive_int_tuple(value: Any, field: str) -> tuple[int, ...]:
    if not isinstance(value, list) or len(value) < 2:
        raise DetectionEvalError(f"{field} must contain at least two positive integers")
    return tuple(_positive_int(item, field) for item in value)


def _positive_number(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        raise DetectionEvalError(f"{field} must be a positive number")
    return float(value)


def _percent(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.1%}"


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
