"""axe "needs review" (incomplete) results are stored as Not sure, never as failures.

axe-core sorts each node into violations, passes, incomplete or inapplicable.
"Incomplete" means axe could not decide, for example the contrast of text over
a background image. Axcess used to drop those. It now stores them with
``engine_outcome = 'cant_tell'``, the outcome Alfa's "cannot tell" already
uses, and shows them as their own Not sure issue type.
"""

from __future__ import annotations

import sqlite3

from audit.analyzer.axe import AxeViolation, _flatten
from audit.db import repo
from audit.web import issues as issues_mod

_RAW_RULE = {
    "id": "color-contrast",
    "impact": "serious",
    "help": "Elements must meet minimum color contrast ratio thresholds",
    "helpUrl": "https://dequeuniversity.com/rules/axe/4.10/color-contrast",
    "tags": ["wcag2aa", "wcag143"],
    "nodes": [
        {
            "target": [".hero h1"],
            "html": '<h1 class="hero">Welcome</h1>',
            "failureSummary": (
                "Fix any of the following:\n  Element's background color could not be "
                "determined due to a background image"
            ),
        }
    ],
}


def test_incomplete_nodes_flatten_as_cant_tell() -> None:
    (failed,) = _flatten([_RAW_RULE])
    (unsure,) = _flatten([_RAW_RULE], outcome="cant_tell")

    assert failed.outcome == "failed"
    assert unsure.outcome == "cant_tell"
    assert unsure.wcag_sc == "1.4.3"
    assert "background image" in unsure.failure_summary


def test_cant_tell_never_shares_a_row_with_a_failure_and_failures_keep_their_hash() -> None:
    """The database dedupes on (page, rule, target_hash).

    A cant_tell result's hash differs from a failure of the same element, so a
    menu that turns a load-time "needs review" into a failure keeps both. A
    failure's hash is what it always was, so older scans still compare.
    """
    (failed,) = _flatten([_RAW_RULE])
    (unsure,) = _flatten([_RAW_RULE], outcome="cant_tell")
    legacy = AxeViolation(
        rule_id=failed.rule_id,
        impact=failed.impact,
        help=failed.help,
        help_url=failed.help_url,
        wcag_sc=failed.wcag_sc,
        wcag_scs=failed.wcag_scs,
        wcag_level=failed.wcag_level,
        target_selector=failed.target_selector,
        failure_summary=failed.failure_summary,
        html_snippet=failed.html_snippet,
    )

    assert unsure.target_hash != failed.target_hash
    assert legacy.target_hash == failed.target_hash


def _seed(conn: sqlite3.Connection) -> tuple[int, dict[str, int]]:
    cur = conn.execute(
        "INSERT INTO scans (seed_url, status, page_count, finding_count, config_json) "
        "VALUES ('http://example.com/', 'completed', 2, 0, '{}')"
    )
    scan_id = int(cur.lastrowid or 0)
    pages = [
        repo.upsert_page(
            conn,
            scan_id=scan_id,
            url_normalized=f"http://example.com/{name}",
            status_code=200,
            title=name,
            render_mode="js",
            html_hash=str(index) * 64,
        )
        for index, name in enumerate(("home", "about"))
    ]
    ids: dict[str, int] = {}
    for page_id, selector, outcome in (
        (pages[0], ".low-contrast", "failed"),
        (pages[0], ".hero h1", "cant_tell"),
        (pages[1], ".banner p", "cant_tell"),
    ):
        (violation,) = _flatten(
            [{**_RAW_RULE, "nodes": [{**_RAW_RULE["nodes"][0], "target": [selector]}]}],
            outcome=outcome,  # type: ignore[arg-type]
        )
        ids[selector] = repo.upsert_axe_violation(
            conn,
            page_id=page_id,
            scan_id=scan_id,
            rule_id=violation.rule_id,
            wcag_sc=violation.wcag_sc,
            wcag_scs=violation.wcag_scs,
            wcag_level=violation.wcag_level,
            impact=violation.impact,
            help=violation.help,
            help_url=violation.help_url,
            target_selector=violation.target_selector,
            failure_summary=violation.failure_summary,
            html_snippet=violation.html_snippet,
            target_hash=violation.target_hash,
            engine_outcome=violation.outcome,
        )
    return scan_id, ids


def test_needs_review_is_its_own_not_sure_issue_type(tmp_db: sqlite3.Connection) -> None:
    scan_id, ids = _seed(tmp_db)
    rows = {r.issue_key: r for r in issues_mod.list_issues(tmp_db, scan_id) if r.pipeline == "axe"}

    assert set(rows) == {"axe:color-contrast", "axe:color-contrast:cant_tell"}
    failed = rows["axe:color-contrast"]
    unsure = rows["axe:color-contrast:cant_tell"]

    # The failure is what it was: Mostly sure, one occurrence, its own id.
    assert failed.review_lane == "likely_barrier"
    assert failed.finding_ids == (ids[".low-contrast"],)
    assert failed.title == "Text does not stand out enough from its background"

    # What axe could not decide: Not sure, with no ids in common.
    assert unsure.review_lane == "expert_review"
    assert unsure.evidence_confidence == "medium"
    assert unsure.high_confidence_occurrence_count == 0
    assert set(unsure.finding_ids) == {ids[".hero h1"], ids[".banner p"]}
    assert unsure.title == (
        "Text does not stand out enough from its background, a person must decide"
    )
    assert "could not decide on 2 occurrences" in unsure.evidence_summary
    assert "That is not a failure" in unsure.evidence_summary
    # Same criterion and impact as the rule, but Not sure lowers the priority.
    assert unsure.wcag_sc == "1.4.3"
    assert unsure.priority < issues_mod._priority("serious", 2, 2, "high")


def test_needs_review_detail_does_not_say_the_rule_failed(tmp_db: sqlite3.Connection) -> None:
    scan_id, _ids = _seed(tmp_db)

    detail = issues_mod.get_issue_detail(tmp_db, scan_id, "axe:color-contrast:cant_tell")

    assert detail is not None
    assert "could not decide" in (detail.description or "")
    assert "too low" not in (detail.description or "")
    assert detail.fix_steps[0].startswith("Check each element on the page by hand.")
    # The rest of the card's steps still apply once a person confirms it.
    assert len(detail.fix_steps) > 1
    assert {p.page_url for p in detail.pages} == {
        "http://example.com/home",
        "http://example.com/about",
    }

    failed = issues_mod.get_issue_detail(tmp_db, scan_id, "axe:color-contrast")
    assert failed is not None
    assert "too low" in (failed.description or "")
    assert [p.page_url for p in failed.pages] == ["http://example.com/home"]


def test_axe_rule_id_strips_the_outcome() -> None:
    assert issues_mod.axe_rule_id("axe:color-contrast") == "color-contrast"
    assert issues_mod.axe_rule_id("axe:color-contrast:cant_tell") == "color-contrast"
