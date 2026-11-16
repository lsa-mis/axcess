"""A stored page code check finding shows up as an issue like any other check's.

The page code check stores one occurrence per element in page_a11y_findings
with pipeline 'markup'. Each rule is its own issue type, ``markup:<rule_id>``,
with its own guidance card (``markup_rules`` in audit_report.yaml) and its own
"How sure", read from ``audit.analyzer.markup.base.RULES``.
"""

from __future__ import annotations

import sqlite3
from typing import Any

import pytest

from audit.analyzer.markup import RULES, MarkupFinding, MarkupProbe
from audit.analyzer.markup import probe as markup_probe
from audit.db import repo
from audit.web import issues


def _scan(conn: sqlite3.Connection, url: str = "https://x.test/") -> tuple[int, int]:
    cursor = conn.execute(
        "INSERT INTO scans (seed_url, status, config_json) VALUES (?, 'completed', ?)",
        (url, '{"markup_checks_enabled": true}'),
    )
    scan_id = int(cursor.lastrowid or 0)
    page_id = repo.upsert_page(
        conn,
        scan_id=scan_id,
        url_normalized=url + "contact",
        status_code=200,
        title="Contact",
        render_mode="js",
        html_hash="0" * 64,
    )
    return scan_id, page_id


def _store(conn: sqlite3.Connection, scan_id: int, page_id: int, **kwargs: Any) -> None:
    repo.upsert_markup_finding(conn, page_id=page_id, scan_id=scan_id, **kwargs)
    conn.commit()


def _markup_rows(conn: sqlite3.Connection, scan_id: int) -> list[issues.IssueRow]:
    return [r for r in issues.list_issues(conn, scan_id) if r.pipeline == "markup"]


def _finding(rule_id: str, selector: str = "#email") -> MarkupFinding:
    return MarkupFinding(
        rule_id=rule_id,
        target_selector=selector,
        html_snippet=f'<input id="{selector.lstrip("#")}">',
        failure_summary="What the check saw.",
    )


def test_a_rule_this_version_does_not_know_is_not_sure(tmp_db: sqlite3.Connection) -> None:
    """A report made by a later version keeps the cautious default."""
    scan_id, page_id = _scan(tmp_db)
    _store(
        tmp_db,
        scan_id,
        page_id,
        rule_id="markup-from-the-future",
        wcag_sc=None,
        wcag_scs=None,
        wcag_level=None,
        impact="moderate",
        help="Something new",
        help_url="https://www.w3.org/WAI/",
        target_selector="p",
        failure_summary="",
        html_snippet="<p>x</p>",
        target_hash="h",
        criterion_sc=None,
    )

    [row] = _markup_rows(tmp_db, scan_id)

    assert row.issue_key == "markup:markup-from-the-future"
    assert row.review_lane == "expert_review"
    assert row.conformance == "BP"
    assert row.title == "Something new"


@pytest.mark.parametrize("rule_id", sorted(RULES))
def test_each_rule_has_its_lane_card_and_key(tmp_db: sqlite3.Connection, rule_id: str) -> None:
    rule = RULES[rule_id]
    scan_id, page_id = _scan(tmp_db)
    _store(tmp_db, scan_id, page_id, **_finding(rule_id).to_repo_kwargs())

    [row] = _markup_rows(tmp_db, scan_id)

    assert row.issue_key == f"markup:{rule_id}"
    assert row.review_lane == rule.review_lane
    assert row.evidence_confidence == rule.evidence_confidence
    assert row.title == rule.title
    assert row.wcag_sc == rule.criterion_sc
    assert row.conformance == (rule.wcag_level or "BP")
    assert row.high_confidence_occurrence_count == (
        1 if rule.review_lane == "likely_barrier" else 0
    )
    assert row.description, "the guidance card's what_happening"
    assert row.fix_steps, "the guidance card's fix steps"
    detail = issues.get_issue_detail(tmp_db, scan_id, row.issue_key)
    assert detail is not None
    assert [p.page_title for p in detail.pages] == ["Contact"]


@pytest.mark.parametrize("rule_id", sorted(RULES))
def test_rows_stay_in_their_own_report(tmp_db: sqlite3.Connection, rule_id: str) -> None:
    """Report A never shows report B's occurrences, for the same rule and site."""
    scan_a, page_a = _scan(tmp_db)
    scan_b, page_b = _scan(tmp_db)
    _store(tmp_db, scan_a, page_a, **_finding(rule_id, "#a").to_repo_kwargs())
    _store(tmp_db, scan_b, page_b, **_finding(rule_id, "#b").to_repo_kwargs())
    _store(tmp_db, scan_b, page_b, **_finding(rule_id, "#c").to_repo_kwargs())

    [row_a] = _markup_rows(tmp_db, scan_a)
    [row_b] = _markup_rows(tmp_db, scan_b)

    assert row_a.occurrence_count == 1
    assert row_b.occurrence_count == 2
    owners = {
        tmp_db.execute("SELECT scan_id FROM page_a11y_findings WHERE id = ?", (i,)).fetchone()[0]
        for i in row_a.finding_ids
    }
    assert owners == {scan_a}
    detail_a = issues.get_issue_detail(tmp_db, scan_a, row_b.issue_key)
    assert detail_a is not None
    assert detail_a.row.occurrence_count == 1
    assert {p.page_id for p in detail_a.pages} == {page_a}


class _BrokenPage:
    """A page whose every script fails, as a crashed or navigating tab does."""

    async def evaluate(self, *_args: Any) -> Any:
        raise RuntimeError("Execution context was destroyed")


class _JunkPage:
    """A page that returns the wrong shape (a site that overrides built-ins)."""

    def __init__(self, value: Any) -> None:
        self.value = value

    async def evaluate(self, *_args: Any) -> Any:
        return self.value


async def test_the_check_never_raises_and_keeps_going(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(markup_probe._RULE_JS, "markup-test", "return [];")
    monkeypatch.setitem(markup_probe._SUMMARIES, "markup-test", lambda _d: "")
    assert await MarkupProbe().run(_BrokenPage()) == []  # type: ignore[arg-type]


@pytest.mark.parametrize("value", [None, "text", 5, [None, "x", {"selector": ""}]])
async def test_wrong_shapes_are_dropped(value: Any) -> None:
    for rule_id in RULES:
        findings = await MarkupProbe()._run_rule(
            _JunkPage(value),  # type: ignore[arg-type]
            rule_id,
            markup_probe._RULE_JS[rule_id],
        )
        assert findings == []


async def test_results_are_capped_per_rule_and_snippets_are_cut() -> None:
    for rule_id, rule in RULES.items():
        many = [
            {"selector": f"#e{i}", "html": "<p>" + "x" * 9000 + "</p>", "detail": {}}
            for i in range(rule.max_results + 30)
        ]
        findings = await MarkupProbe()._run_rule(
            _JunkPage(many),  # type: ignore[arg-type]
            rule_id,
            markup_probe._RULE_JS[rule_id],
        )
        assert len(findings) == rule.max_results
        assert all(len(f.html_snippet) <= 4000 for f in findings)
