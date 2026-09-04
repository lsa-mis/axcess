"""Search configuration bounds and report evidence isolation."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from pydantic import ValidationError

from audit.analyzer.axe import AxeAnalyzer
from audit.crawler.orchestrator import CrawlConfig, build_search_explorer
from audit.crawler.search import SearchConfig, SearchOutcome, search_url_allowed
from audit.db import repo


def config(**overrides: object) -> SearchConfig:
    return SearchConfig.model_validate(
        {
            "confirmed": True,
            "fields": [{"target": "Search", "value": "sample"}],
            **overrides,
        }
    )


@pytest.mark.parametrize(
    "overrides",
    [
        {"confirmed": False},
        {"fields": []},
        {"fields": [{"target": "", "value": "x"}]},
        {"max_results": 51},
        {"max_result_pages": 6},
        {"timeout_ms": 15001},
        {"unexpected": True},
    ],
)
def test_search_rejects_unconfirmed_or_unbounded_configuration(
    overrides: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        config(**overrides)


@pytest.mark.parametrize(
    "url",
    [
        "https://outside.test/",
        "javascript:alert(1)",
        "https://example.test/logout",
        "https://user:secret@example.test/",
        "https://example.test/other/",
    ],
)
def test_search_entry_must_be_safe_and_inside_path_scope(url: str) -> None:
    assert not search_url_allowed(
        config(page_url=url), "https://example.test/docs/", whole_host=False
    )


def test_search_accepts_hash_route_and_obeys_frontier_filters() -> None:
    search = config(page_url="https://example.test/docs/#/search")
    explorer = build_search_explorer(
        CrawlConfig(
            seed_url="https://example.test/docs/",
            search=search,
            excluded_scopes=("https://example.test/docs/private",),
        ),
        AxeAnalyzer.from_bundled(),
    )
    assert explorer is not None
    assert explorer.can_visit("https://example.test/docs/#/report/1")
    assert not explorer.can_visit("https://example.test/docs/#/logout")
    assert not explorer.can_visit("https://example.test/docs/private/1")
    assert not explorer.can_visit("https://example.test/other")
    assert not explorer.can_visit("https://user:secret@example.test/docs/")


def test_search_evidence_belongs_to_one_report_and_rolls_back(tmp_db: sqlite3.Connection) -> None:
    scans = [
        int(
            tmp_db.execute(
                "INSERT INTO scans (seed_url, status, config_json) "
                "VALUES ('https://example.test/', 'completed', '{}')"
            ).lastrowid
        )
        for _ in range(2)
    ]
    page_id = repo.upsert_page(
        tmp_db,
        scan_id=scans[0],
        url_normalized="https://example.test/",
        status_code=200,
        title="Search",
        render_mode="js",
        html_hash=None,
    )
    outcome = SearchOutcome(
        status="limited", states=2, discovered=8, detail="Result limit reached."
    )
    repo.record_search_run(tmp_db, scan_id=scans[0], page_id=page_id, outcome=outcome)
    with pytest.raises(ValueError, match="does not belong"):
        repo.record_search_run(tmp_db, scan_id=scans[1], page_id=page_id, outcome=outcome)
    assert tmp_db.execute("SELECT COUNT(*) FROM scan_search_runs").fetchone()[0] == 1
    migration = Path(__file__).parents[2] / "src/audit/db/migrations/0025_search_runs"
    tmp_db.executescript(migration.with_suffix(".rollback.sql").read_text())
    tmp_db.executescript(migration.with_suffix(".sql").read_text())
    assert tmp_db.execute("SELECT COUNT(*) FROM scan_search_runs").fetchone()[0] == 0
