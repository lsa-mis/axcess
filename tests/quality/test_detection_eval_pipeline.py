from __future__ import annotations

import json
from pathlib import Path

import pytest

from audit.detection_evals import (
    DetectionEvalError,
    PerformanceConfig,
    PerformancePoint,
    format_markdown,
    load_eval_config,
    performance_failures,
    run_detection_evals,
    write_reports,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = PROJECT_ROOT / "tests" / "quality" / "detection_eval_config.json"


def test_committed_eval_config_covers_three_increasing_workloads() -> None:
    config = load_eval_config(CONFIG_PATH, project_root=PROJECT_ROOT)

    assert config.config_version == "1.0.0"
    assert config.corpus_path.is_file()
    assert config.performance.page_counts == (100, 500, 1000)
    assert config.performance.efficiency_reference_pages in config.performance.page_counts


def test_config_rejects_reference_size_outside_scale_points(tmp_path: Path) -> None:
    payload = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    payload["performance"]["efficiency_reference_pages"] = 250
    path = tmp_path / "config.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(DetectionEvalError, match="must be one of page_counts"):
        load_eval_config(path, project_root=PROJECT_ROOT)


def test_performance_failures_separate_efficiency_from_scale() -> None:
    config = PerformanceConfig(
        page_counts=(10, 100),
        findings_per_page=2,
        efficiency_reference_pages=10,
        min_write_findings_per_second=100.0,
        max_projection_seconds=1.0,
        max_per_finding_slowdown=2.0,
    )
    points = [
        PerformancePoint(10, 2, 20, 20, 4, 1.0, 2.0, 20.0, 4096),
        PerformancePoint(100, 2, 200, 199, 3, 30.0, 0.1, 6.7, 8192),
    ]

    efficiency, scale = performance_failures(config, points)

    assert any("throughput" in failure for failure in efficiency)
    assert any("projection" in failure for failure in efficiency)
    assert any("stored 199 of 200" in failure for failure in scale)
    assert any("produced 3 issue groups" in failure for failure in scale)
    assert any("slowdown" in failure for failure in scale)


def test_small_pipeline_run_writes_both_artifacts(tmp_path: Path) -> None:
    config_payload = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    config_payload["performance"] = {
        "page_counts": [2, 4],
        "findings_per_page": 4,
        "efficiency_reference_pages": 2,
        "min_write_findings_per_second": 0.01,
        "max_projection_seconds": 60.0,
        "max_per_finding_slowdown": 1000.0,
    }
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(config_payload), encoding="utf-8")
    config = load_eval_config(config_path, project_root=PROJECT_ROOT)

    report = run_detection_evals(config)
    write_reports(report, tmp_path / "artifacts")

    assert report["status"] == "pass"
    assert report["efficacy"]["overall"]["false_discovery_rate"] < 0.05
    assert report["efficacy"]["thresholds"]["min_recall"] == 0.8
    assert report["scale"]["points"][-1]["stored_findings"] == 16
    assert (tmp_path / "artifacts" / "report.json").is_file()
    markdown = (tmp_path / "artifacts" / "report.md").read_text(encoding="utf-8")
    assert markdown == format_markdown(report)
    assert "# Axcess detection evaluation" in markdown
    assert "## What this workflow tests" in markdown
    assert "### What the efficacy metrics mean" in markdown
    assert "`repo.upsert_axe_violation`" in markdown
    assert "## What this run does not test" in markdown
    assert "All configured gates passed." in markdown
