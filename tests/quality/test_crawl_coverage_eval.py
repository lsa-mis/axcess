"""The crawl-coverage lane of ``make detection-evals`` on the committed test site.

Runs the real crawler against ``tests/fixtures/site/coverage`` three times
(about a second in all) and holds it to the committed pass marks, so a
regression in link discovery, sitemap reading, deduplication or the
unvisited counts fails here as well as in the eval.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from audit.crawl_coverage_eval import (
    CoverageEvalError,
    load_answer_key,
    parse_coverage_config,
    run_coverage_eval,
)
from audit.detection_evals import load_eval_config

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = PROJECT_ROOT / "tests" / "quality" / "detection_eval_config.json"


def test_committed_config_includes_the_coverage_lane() -> None:
    config = load_eval_config(CONFIG_PATH, project_root=PROJECT_ROOT)
    assert config.crawl_coverage is not None
    assert config.crawl_coverage.min_recall == 1.0
    assert config.crawl_coverage.max_wrong_pages == 0
    assert config.crawl_coverage.max_fetches_per_page == 1.1


def test_answer_key_has_the_tickets_nine_hard_cases() -> None:
    key = load_answer_key(PROJECT_ROOT / "tests" / "fixtures" / "site" / "coverage")
    assert [case.id for case in key.hard_cases] == [
        "sitemap_only",
        "deep_page",
        "button_only",
        "image_map",
        "url_variants",
        "redirect",
        "out_of_scope",
        "sign_out",
        "robots_disallowed",
    ]


def test_coverage_eval_passes_on_the_test_site() -> None:
    config = load_eval_config(CONFIG_PATH, project_root=PROJECT_ROOT)
    assert config.crawl_coverage is not None
    report = run_coverage_eval(config.crawl_coverage)

    assert report["failures"] == []
    assert report["recall"] == 1.0
    assert report["wrong_pages"] == 0
    assert report["efficiency"]["fetches_per_page"] <= 1.1
    assert all(case["passed"] for case in report["hard_cases"])
    honesty = report["honesty"]
    assert honesty["default_limits"]["unvisited_depth_limit"] == 1
    assert honesty["default_limits"]["unvisited_blocked"] == 2
    assert honesty["default_limits"]["unvisited_page_limit"] == 0
    assert honesty["page_capped"]["unvisited_page_limit"] > 0


def test_coverage_eval_fails_when_a_pass_mark_is_out_of_reach() -> None:
    config = load_eval_config(CONFIG_PATH, project_root=PROJECT_ROOT)
    assert config.crawl_coverage is not None
    strict = parse_coverage_config(
        {
            "site": str(config.crawl_coverage.site_dir),
            "full_max_depth": 15,
            "capped_max_pages": 8,
            "min_recall": 1.0,
            "max_wrong_pages": 0,
            # One request per page is impossible here: the site has a redirect
            # and a letter-case variant that can only be recognized by fetching.
            "max_fetches_per_page": 1.0,
        },
        PROJECT_ROOT,
    )
    report = run_coverage_eval(strict)
    assert report["status"] == "fail"
    assert any("page fetches per unique page" in f for f in report["failures"])


def test_config_rejects_a_negative_pass_mark(tmp_path: Path) -> None:
    payload = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    payload["crawl_coverage"]["max_wrong_pages"] = -1
    with pytest.raises(CoverageEvalError):
        parse_coverage_config(payload["crawl_coverage"], PROJECT_ROOT)
