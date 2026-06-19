"""Unit tests for the unified Issues view (`audit.web.issues`).

The Issues route is the operator's entry point — bugs here cascade to
every triager. These tests pin: row-shape unification across both
pipelines, filter semantics, sort ordering, deep-link URL building,
and the priority formula.
"""

from __future__ import annotations

import sqlite3

from audit.db import repo
from audit.synthesizer.findings import synthesize_findings
from audit.web import issues as issues_mod


def _seed_two_pipelines(conn: sqlite3.Connection) -> int:
    """Build a scan with one image-of-text issue + two axe issues."""
    cur = conn.execute(
        "INSERT INTO scans (seed_url, status, page_count, finding_count, "
        "config_json) VALUES ('http://example.com/', 'completed', 2, 0, '{}')"
    )
    scan_id = int(cur.lastrowid or 0)

    page_a = repo.upsert_page(
        conn,
        scan_id=scan_id,
        url_normalized="http://example.com/",
        status_code=200,
        title="Home",
        render_mode="js",
        html_hash="0" * 64,
    )
    page_b = repo.upsert_page(
        conn,
        scan_id=scan_id,
        url_normalized="http://example.com/about",
        status_code=200,
        title="About",
        render_mode="js",
        html_hash="1" * 64,
    )

    # Image: essential text, missing alt → should land as one issue row.
    img_id = repo.upsert_image(
        conn,
        content_hash="b" * 64,
        src_url="http://example.com/banner.png",
        mime="image/png",
        bytes_len=512,
        width=600,
        height=100,
        blob_path="bb/" + "b" * 64 + ".png",
        has_svg_text=False,
        scan_id=scan_id,
    )
    repo.upsert_page_image(
        conn,
        page_id=page_a,
        image_id=img_id,
        alt_text=None,
        role=None,
        context_snippet="Buy widgets",
        position=0,
        above_fold=True,
    )
    repo.upsert_analysis(
        conn,
        image_id=img_id,
        ocr_text="BUY WIDGETS NOW",
        ocr_confidence=92.5,
        vlm_classification="essential",
        vlm_rationale="Promo banner.",
        has_text=True,
        model_versions={"ocr": "tesseract-test", "vlm": "stub:1", "prompt": "v1-stub"},
    )
    synthesize_findings(conn, scan_id=scan_id)

    # Axe: color-contrast on 2 pages (high-spread).
    for i, pid in enumerate([page_a, page_b]):
        conn.execute(
            """
            INSERT INTO page_a11y_findings
                (page_id, scan_id, rule_id, wcag_sc, wcag_scs, wcag_level,
                 impact, help, help_url, target_selector, failure_summary,
                 html_snippet, target_hash, status)
            VALUES (?, ?, 'color-contrast', '1.4.3', '1.4.3', 'AA',
                'serious', 'Elements must meet color contrast',
                'https://dequeuniversity.com/rules/axe/4.10/color-contrast',
                ?, 'contrast 2.1', '<p class=mute>x</p>',
                ?, 'new')
            """,
            (pid, scan_id, f"p:nth-child({i})", f"hash-cc-{i}"),
        )
    # Axe: image-alt on one page (Critical).
    conn.execute(
        """
        INSERT INTO page_a11y_findings
            (page_id, scan_id, rule_id, wcag_sc, wcag_scs, wcag_level,
             impact, help, help_url, target_selector, failure_summary,
             html_snippet, target_hash, status)
        VALUES (?, ?, 'image-alt', '1.1.1', '1.1.1', 'A',
            'critical', 'Images must have alt text',
            'https://dequeuniversity.com/rules/axe/4.10/image-alt',
            'main > img', 'no alt', '<img src=x>',
            'hash-ia', 'new')
        """,
        (page_a, scan_id),
    )
    return scan_id


def test_list_issues_unifies_both_pipelines(tmp_db: sqlite3.Connection) -> None:
    """Image findings and axe findings produce IssueRow values side-by-side."""
    scan_id = _seed_two_pipelines(tmp_db)
    rows = issues_mod.list_issues(tmp_db, scan_id)
    pipelines = {r.pipeline for r in rows}
    assert pipelines == {"axe", "image"}
    # Three issues total: 1 image group, 2 axe rules.
    assert len(rows) >= 3


def test_list_issues_priority_sort_default(tmp_db: sqlite3.Connection) -> None:
    """Default sort is priority_desc — highest-impact row appears first."""
    scan_id = _seed_two_pipelines(tmp_db)
    rows = issues_mod.list_issues(tmp_db, scan_id)
    priorities = [r.priority for r in rows]
    assert priorities == sorted(priorities, reverse=True)


def test_list_issues_filters_by_conformance(tmp_db: sqlite3.Connection) -> None:
    """Conformance=A returns only Level-A rows."""
    scan_id = _seed_two_pipelines(tmp_db)
    only_a = issues_mod.list_issues(tmp_db, scan_id, conformance=["A"])
    assert all(r.conformance == "A" for r in only_a)
    # image-alt (A), essential_missing (AA → no match)
    rule_ids = {r.issue_key for r in only_a}
    assert "axe:image-alt" in rule_ids
    assert "axe:color-contrast" not in rule_ids


def test_list_issues_filters_by_responsibility(tmp_db: sqlite3.Connection) -> None:
    """Responsibility filter narrows to the named owner."""
    scan_id = _seed_two_pipelines(tmp_db)
    only_designer = issues_mod.list_issues(
        tmp_db, scan_id, responsibility=["designer"]
    )
    # color-contrast is owned by designer in the YAML.
    assert any(r.issue_key == "axe:color-contrast" for r in only_designer)
    # image-alt is owned by editor — should NOT appear.
    assert not any(r.issue_key == "axe:image-alt" for r in only_designer)


def test_list_issues_filters_by_abilities(tmp_db: sqlite3.Connection) -> None:
    """Abilities filter passes a row if ANY listed ability matches."""
    scan_id = _seed_two_pipelines(tmp_db)
    # Vision is on color-contrast, image-alt, and the image-of-text issue.
    vision = issues_mod.list_issues(tmp_db, scan_id, abilities=["vision"])
    assert {r.issue_key for r in vision} >= {"axe:color-contrast", "axe:image-alt"}


def test_list_issues_search_matches_title_and_sc(
    tmp_db: sqlite3.Connection,
) -> None:
    """Search is case-insensitive and matches title or WCAG SC."""
    scan_id = _seed_two_pipelines(tmp_db)
    by_title = issues_mod.list_issues(tmp_db, scan_id, search="contrast")
    assert all("contrast" in r.title.lower() for r in by_title)
    by_sc = issues_mod.list_issues(tmp_db, scan_id, search="1.4.3")
    assert all((r.wcag_sc or "") == "1.4.3" for r in by_sc)


def test_list_issues_deep_link_to_dedicated_detail(
    tmp_db: sqlite3.Connection,
) -> None:
    """Each row links to the dedicated /issues/{key} detail page.

    Earlier iterations linked to the grouped views with a filter
    param; the recursive-critique pass found that landed the operator
    in the middle of a long list. The new contract: the row points at
    a dedicated single-issue page (Siteimprove "page 2" shape).
    """
    scan_id = _seed_two_pipelines(tmp_db)
    rows = issues_mod.list_issues(tmp_db, scan_id)
    cc_row = next(r for r in rows if r.issue_key == "axe:color-contrast")
    assert cc_row.detail_url == f"/scans/{scan_id}/issues/axe:color-contrast"
    img_row = next(r for r in rows if r.pipeline == "image")
    # Image rows point at the same dedicated detail route.
    assert img_row.detail_url.startswith(f"/scans/{scan_id}/issues/image:")


def test_priority_rewards_spread(tmp_db: sqlite3.Connection) -> None:
    """A serious issue on 2 pages outranks a serious issue on 1.

    The formula is severity_weight * log(1 + page_count). This is the
    test that pins it: same severity, more pages -> higher priority.
    """
    scan_id = _seed_two_pipelines(tmp_db)
    rows = issues_mod.list_issues(tmp_db, scan_id)
    cc = next(r for r in rows if r.issue_key == "axe:color-contrast")
    ia = next(r for r in rows if r.issue_key == "axe:image-alt")
    # color-contrast affects 2 pages and is serious (weight 3.0);
    # image-alt affects 1 page and is critical (weight 4.0).
    # 3.0 * log(3) ~= 3.30 vs 4.0 * log(2) ~= 2.77 -> cc wins on spread.
    assert cc.priority > ia.priority


def test_get_issue_detail_axe_pipeline(tmp_db: sqlite3.Connection) -> None:
    """Detail loads the row + page list + YAML template for an axe issue."""
    scan_id = _seed_two_pipelines(tmp_db)
    detail = issues_mod.get_issue_detail(
        tmp_db, scan_id, "axe:color-contrast"
    )
    assert detail is not None
    assert detail.row.issue_key == "axe:color-contrast"
    assert detail.row.pipeline == "axe"
    # YAML metadata pulled through (the color-contrast entry exists).
    assert detail.description is not None
    assert "contrast" in detail.description.lower()
    assert detail.fix_steps  # has fix steps from YAML
    # Pages list: 2 pages affected the seed.
    assert len(detail.pages) == 2
    page_urls = {p.page_url for p in detail.pages}
    assert page_urls == {
        "http://example.com/",
        "http://example.com/about",
    }
    # Help URL pulled from the axe data, not the YAML.
    assert detail.help_url and "dequeuniversity" in detail.help_url


def test_get_issue_detail_returns_none_for_stale_key(
    tmp_db: sqlite3.Connection,
) -> None:
    """Stale issue keys (e.g. after rescan) return None — caller 404s."""
    scan_id = _seed_two_pipelines(tmp_db)
    detail = issues_mod.get_issue_detail(
        tmp_db, scan_id, "axe:rule-that-never-existed"
    )
    assert detail is None


def test_get_issue_detail_pages_sort_order(tmp_db: sqlite3.Connection) -> None:
    """The pages-with-issue table honors the `sort` argument."""
    scan_id = _seed_two_pipelines(tmp_db)
    by_url = issues_mod.get_issue_detail(
        tmp_db, scan_id, "axe:color-contrast", sort="url"
    )
    assert by_url is not None
    urls = [p.page_url for p in by_url.pages]
    assert urls == sorted(urls)


def test_issue_row_carries_inline_what_why_how(
    tmp_db: sqlite3.Connection,
) -> None:
    """IssueRow includes description / why_matters / fix_steps / acceptance.

    The Issues list cards need the longform content inline so the
    operator can read "what / why / how" without round-tripping
    through the detail page. The YAML lookup that powered the detail
    view now also populates the IssueRow.
    """
    scan_id = _seed_two_pipelines(tmp_db)
    rows = issues_mod.list_issues(tmp_db, scan_id)
    cc = next(r for r in rows if r.issue_key == "axe:color-contrast")
    # color-contrast IS in the YAML, so the longform content rides along.
    assert cc.description is not None
    assert "contrast" in cc.description.lower()
    assert cc.why_matters is not None
    assert len(cc.fix_steps) >= 1
    # Help URL falls back to the axe-supplied URL when the YAML doesn't pin one.
    assert cc.help_url and "dequeuniversity" in cc.help_url


def test_issue_row_empty_longform_for_un_templated_rule(
    tmp_db: sqlite3.Connection,
) -> None:
    """Rules without a YAML card still get a row — just empty longform.

    The card layout degrades gracefully: the row renders with title +
    metadata, the body shows "No templated card yet" instead of fix
    steps. This is the contract that lets us ship a new axe rule
    before its YAML entry lands.
    """
    cur = tmp_db.execute(
        "INSERT INTO scans (seed_url, status, page_count, finding_count, "
        "config_json) VALUES ('http://x/', 'completed', 1, 0, '{}')"
    )
    scan_id = int(cur.lastrowid or 0)
    page = repo.upsert_page(
        tmp_db, scan_id=scan_id, url_normalized="http://x/",
        status_code=200, title="x", render_mode="js", html_hash="0" * 64,
    )
    tmp_db.execute(
        """
        INSERT INTO page_a11y_findings
            (page_id, scan_id, rule_id, wcag_sc, wcag_scs, wcag_level,
             impact, help, help_url, target_selector, failure_summary,
             html_snippet, target_hash, status)
        VALUES (?, ?, 'made-up-rule-id', NULL, NULL, NULL,
            'serious', 'no template', '', 'p', '', '', 'h', 'new')
        """,
        (page, scan_id),
    )
    rows = issues_mod.list_issues(tmp_db, scan_id)
    new_row = next(r for r in rows if r.issue_key == "axe:made-up-rule-id")
    assert new_row.description is None
    assert new_row.why_matters is None
    assert new_row.fix_steps == ()


def test_breakdowns_count_unique_buckets(tmp_db: sqlite3.Connection) -> None:
    """The breakdown helpers count rows correctly per bucket."""
    scan_id = _seed_two_pipelines(tmp_db)
    rows = issues_mod.list_issues(tmp_db, scan_id)
    cmap = issues_mod.conformance_breakdown(rows)
    # Should have at least one Level-A row (image-alt).
    assert cmap.get("A", 0) >= 1
    # Sum of buckets equals total rows.
    assert sum(cmap.values()) == len(rows)
    abilities = issues_mod.abilities_breakdown(rows)
    # Vision shows up at least once (multiple rules contribute).
    assert abilities.get("vision", 0) >= 1


def _seed_responsive_finding(conn: sqlite3.Connection, scan_id: int, page_id: int) -> None:
    """Insert one responsive-probe row (SC 1.4.10 reflow) directly."""
    conn.execute(
        """
        INSERT INTO page_a11y_findings
            (page_id, scan_id, pipeline, criterion_sc, rule_id, wcag_sc,
             wcag_scs, wcag_level, impact, help, help_url, target_selector,
             failure_summary, html_snippet, target_hash, status)
        VALUES (?, ?, 'responsive', '1.4.10', 'responsive-reflow-overflow',
            '1.4.10', '1.4.10', 'AA', 'serious',
            'Content must reflow to a 320px-wide viewport without horizontal scrolling.',
            'https://www.w3.org/WAI/WCAG21/Understanding/reflow.html',
            'div#fixed-width',
            'At a 320px viewport this element is 900px wide.',
            '<div id="fixed-width">wide</div>',
            'hash-reflow', 'new')
        """,
        (page_id, scan_id),
    )


def test_responsive_rows_get_their_own_pipeline_label(
    tmp_db: sqlite3.Connection,
) -> None:
    """responsive-* rule_ids label as pipeline='responsive', never 'axe'.

    Mirrors the keyboard-probe routing: the SC-keyed YAML fallback
    resolves the card (title/what/why/fix from the 1.4.10 entry in
    semantic_criteria), and the issue_key gets the responsive: prefix
    so the detail route can resolve pages from page_a11y_findings.
    """
    scan_id = _seed_two_pipelines(tmp_db)
    page = tmp_db.execute(
        "SELECT id FROM pages WHERE scan_id = ? LIMIT 1", (scan_id,)
    ).fetchone()
    _seed_responsive_finding(tmp_db, scan_id, int(page["id"]))

    rows = issues_mod.list_issues(tmp_db, scan_id)
    resp_rows = [r for r in rows if r.pipeline == "responsive"]
    assert len(resp_rows) == 1, (
        f"expected exactly one responsive issue; pipelines seen: "
        f"{[r.pipeline for r in rows]}"
    )
    row = resp_rows[0]
    assert row.issue_key == "responsive:responsive-reflow-overflow"
    assert row.wcag_sc == "1.4.10"
    assert row.conformance == "AA"
    # The YAML card (semantic_criteria["1.4.10"]) supplies the curated
    # title + longform what/why/fix via the SC fallback.
    assert "reflow" in row.title.lower() or "320" in row.title
    assert row.description, "what_happening should come from the YAML card"
    assert row.fix_steps, "fix steps should come from the YAML card"
    assert row.responsibility == "dev"


def test_responsive_issue_detail_resolves_pages(
    tmp_db: sqlite3.Connection,
) -> None:
    """get_issue_detail() finds the affected pages for a responsive issue.

    Regression guard for the pages-resolution bug this change fixed:
    non-axe/semantic pipelines used to fall into the image branch and
    query the wrong table, returning zero pages.
    """
    scan_id = _seed_two_pipelines(tmp_db)
    page = tmp_db.execute(
        "SELECT id, url_normalized FROM pages WHERE scan_id = ? LIMIT 1",
        (scan_id,),
    ).fetchone()
    _seed_responsive_finding(tmp_db, scan_id, int(page["id"]))

    detail = issues_mod.get_issue_detail(
        tmp_db, scan_id, "responsive:responsive-reflow-overflow"
    )
    assert detail is not None
    assert len(detail.pages) == 1
    assert detail.pages[0].page_url == page["url_normalized"]
    # Verify steps come through from the YAML card.
    assert detail.verify_manual
    assert detail.help_url and "w3.org" in detail.help_url
