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


def test_issue_rows_include_bounded_exact_locations(tmp_db: sqlite3.Connection) -> None:
    """The primary table gets scan-scoped page and target samples inline."""
    scan_id = _seed_two_pipelines(tmp_db)
    rows = issues_mod.list_issues(tmp_db, scan_id)

    contrast = next(row for row in rows if row.issue_key == "axe:color-contrast")
    assert len(contrast.locations) == 2
    assert contrast.locations[0].page_url.startswith("http://example.com/")
    assert contrast.locations[0].target.startswith("p:nth-child(")
    assert contrast.locations[0].evidence_url.startswith(
        f"/scans/{scan_id}/pages/{contrast.locations[0].page_id}#finding-"
    )

    image = next(row for row in rows if row.pipeline == "image")
    assert len(image.locations) == 1
    assert image.locations[0].target == "Image occurrence 1 (above the fold)"
    assert "Buy widgets" in (image.locations[0].context or "")


def test_alfa_structured_target_is_humanized_for_the_location_column() -> None:
    raw = (
        '{"type":"element","name":"img","attributes":['
        '{"type":"attribute","name":"src","value":"/hero.svg"},'
        '{"type":"attribute","name":"width","value":"48"}]}'
    )
    assert issues_mod._humanize_location_target(raw) == 'img[src="/hero.svg"]'
    assert issues_mod._humanize_location_target('{"type":"document"}') == "Document root"


def test_issue_lanes_keep_review_leads_out_of_barrier_totals(
    tmp_db: sqlite3.Connection,
) -> None:
    """Only deterministic failures enter the likely-barrier lane."""
    scan_id = _seed_two_pipelines(tmp_db)
    rows = issues_mod.list_issues(tmp_db, scan_id)
    axe_rows = [row for row in rows if row.pipeline == "axe"]
    image_row = next(row for row in rows if row.pipeline == "image")

    assert all(row.review_lane == "likely_barrier" for row in axe_rows)
    assert all(row.evidence_confidence == "high" for row in axe_rows)
    assert all(row.high_confidence_occurrence_count == row.occurrence_count for row in axe_rows)
    assert image_row.review_lane == "expert_review"
    assert image_row.evidence_confidence == "medium"
    assert image_row.high_confidence_occurrence_count == 0

    lanes = issues_mod.review_lane_breakdown(rows)
    assert lanes["likely_barrier"] == len(axe_rows)
    assert lanes["expert_review"] >= 1


def test_adequate_unclassified_image_is_informational_with_real_page_count(
    tmp_db: sqlite3.Connection,
) -> None:
    """An adequate alt comparison is evidence, never an actionable issue."""
    scan_id = _seed_two_pipelines(tmp_db)
    tmp_db.execute("UPDATE page_images SET alt_text = 'BUY WIDGETS NOW'")
    tmp_db.execute("UPDATE analyses SET vlm_classification = NULL")

    row = next(row for row in issues_mod.list_issues(tmp_db, scan_id) if row.pipeline == "image")
    assert row.issue_key == "image:unclassified_adequate"
    assert row.review_lane == "informational"
    assert row.evidence_confidence == "low"
    assert row.wcag_sc is None
    assert row.conformance == "BP"
    assert row.page_count == 1
    assert row.occurrence_count == 1


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
    only_designer = issues_mod.list_issues(tmp_db, scan_id, responsibility=["designer"])
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
    detail = issues_mod.get_issue_detail(tmp_db, scan_id, "axe:color-contrast")
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


def test_issue_detail_exposes_each_captured_instance_screenshot(
    tmp_db: sqlite3.Connection,
) -> None:
    """Grouped issue pages retain every scan-time screenshot for the UI gallery."""
    scan_id = _seed_two_pipelines(tmp_db)
    hashes = ("a" * 64, "c" * 64)
    rows = tmp_db.execute(
        "SELECT id FROM page_a11y_findings "
        "WHERE scan_id = ? AND rule_id = 'color-contrast' ORDER BY id",
        (scan_id,),
    ).fetchall()
    assert len(rows) == 2
    for row, screenshot_hash in zip(rows, hashes, strict=True):
        tmp_db.execute(
            "UPDATE page_a11y_findings SET screenshot_hash = ? WHERE id = ?",
            (screenshot_hash, int(row["id"])),
        )

    detail = issues_mod.get_issue_detail(tmp_db, scan_id, "axe:color-contrast")

    assert detail is not None
    assert sum(len(page.screenshot_hashes) for page in detail.pages) == 2
    assert {shot for page in detail.pages for shot in page.screenshot_hashes} == set(hashes)


def test_get_issue_detail_returns_none_for_stale_key(
    tmp_db: sqlite3.Connection,
) -> None:
    """Stale issue keys (e.g. after rescan) return None — caller 404s."""
    scan_id = _seed_two_pipelines(tmp_db)
    detail = issues_mod.get_issue_detail(tmp_db, scan_id, "axe:rule-that-never-existed")
    assert detail is None


def test_get_issue_detail_pages_sort_order(tmp_db: sqlite3.Connection) -> None:
    """The pages-with-issue table honors the `sort` argument."""
    scan_id = _seed_two_pipelines(tmp_db)
    by_url = issues_mod.get_issue_detail(tmp_db, scan_id, "axe:color-contrast", sort="url")
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
        tmp_db,
        scan_id=scan_id,
        url_normalized="http://x/",
        status_code=200,
        title="x",
        render_mode="js",
        html_hash="0" * 64,
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


def _seed_keyboard_finding(
    conn: sqlite3.Connection,
    scan_id: int,
    page_id: int,
    *,
    rule_id: str,
    failure_summary: str,
) -> None:
    conn.execute(
        """
        INSERT INTO page_a11y_findings
            (page_id, scan_id, pipeline, criterion_sc, rule_id, wcag_sc,
             wcag_scs, wcag_level, impact, help, help_url, target_selector,
             failure_summary, html_snippet, target_hash, status)
        VALUES (?, ?, 'keyboard', '2.1.2', ?, '2.1.2', '2.1.2', 'A',
            'critical', 'Keyboard users must be able to leave the component.',
            'https://www.w3.org/WAI/WCAG22/Understanding/no-keyboard-trap.html',
            'button#editor', ?, '<button id="editor">Editor</button>', ?, 'new')
        """,
        (page_id, scan_id, rule_id, failure_summary, f"hash-{rule_id}"),
    )


def test_legacy_keyboard_heuristic_is_informational_not_a_barrier(
    tmp_db: sqlite3.Connection,
) -> None:
    scan_id = _seed_two_pipelines(tmp_db)
    page = tmp_db.execute("SELECT id FROM pages WHERE scan_id = ? LIMIT 1", (scan_id,)).fetchone()
    _seed_keyboard_finding(
        tmp_db,
        scan_id,
        int(page["id"]),
        rule_id="keyboard-trap-iframe",
        failure_summary="Iframe is reachable by Tab but has no title.",
    )

    row = next(r for r in issues_mod.list_issues(tmp_db, scan_id) if r.pipeline == "keyboard")
    assert row.review_lane == "informational"
    assert row.evidence_confidence == "low"
    assert row.wcag_sc is None
    assert row.conformance == "BP"
    assert "not a confirmed trap" in row.title.lower()
    assert "do not report it as a barrier" in row.evidence_summary.lower()


def test_bidirectional_keyboard_measurement_remains_an_expert_review_lead(
    tmp_db: sqlite3.Connection,
) -> None:
    scan_id = _seed_two_pipelines(tmp_db)
    page = tmp_db.execute("SELECT id FROM pages WHERE scan_id = ? LIMIT 1", (scan_id,)).fetchone()
    _seed_keyboard_finding(
        tmp_db,
        scan_id,
        int(page["id"]),
        rule_id="keyboard-trap-stuck",
        failure_summary=(
            "Measured focus exit behavior: 4 Tab attempts and 4 Shift+Tab attempts "
            "remained on the same element."
        ),
    )

    row = next(r for r in issues_mod.list_issues(tmp_db, scan_id) if r.pipeline == "keyboard")
    assert row.review_lane == "expert_review"
    assert row.evidence_confidence == "medium"
    assert row.wcag_sc == "2.1.2"
    assert row.conformance == "A"
    assert row.title == "Keyboard users can't escape this element"
    assert "both remained" in row.evidence_summary


def _seed_visual_motion_finding(
    conn: sqlite3.Connection,
    scan_id: int,
    page_id: int,
    *,
    failure_summary: str,
) -> None:
    conn.execute(
        """
        INSERT INTO page_a11y_findings
            (page_id, scan_id, pipeline, criterion_sc, rule_id, wcag_sc,
             wcag_scs, wcag_level, impact, help, help_url, target_selector,
             failure_summary, html_snippet, target_hash, status)
        VALUES (?, ?, 'visual', '2.2.2', 'visual-motion-no-pause', '2.2.2',
            '2.2.2', 'A', 'serious', 'Provide a pause control.',
            'https://www.w3.org/WAI/WCAG22/Understanding/pause-stop-hide.html',
            'video#hero', ?, '<video id="hero" autoplay></video>', ?, 'new')
        """,
        (page_id, scan_id, failure_summary, f"visual-{failure_summary}"),
    )


def test_legacy_autoplay_markup_is_informational_not_a_barrier(
    tmp_db: sqlite3.Connection,
) -> None:
    scan_id = _seed_two_pipelines(tmp_db)
    page_id = int(
        tmp_db.execute("SELECT id FROM pages WHERE scan_id = ? LIMIT 1", (scan_id,)).fetchone()[
            "id"
        ]
    )
    _seed_visual_motion_finding(
        tmp_db,
        scan_id,
        page_id,
        failure_summary="video autoplays with no controls (no pause mechanism)",
    )

    row = next(r for r in issues_mod.list_issues(tmp_db, scan_id) if r.pipeline == "visual")
    assert row.review_lane == "informational"
    assert row.evidence_confidence == "low"
    assert row.wcag_sc is None
    assert row.conformance == "BP"
    assert "playback not verified" in row.title.lower()


def test_runtime_motion_measurement_remains_an_expert_review_lead(
    tmp_db: sqlite3.Connection,
) -> None:
    scan_id = _seed_two_pipelines(tmp_db)
    page_id = int(
        tmp_db.execute("SELECT id FROM pages WHERE scan_id = ? LIMIT 1", (scan_id,)).fetchone()[
            "id"
        ]
    )
    _seed_visual_motion_finding(
        tmp_db,
        scan_id,
        page_id,
        failure_summary=(
            "Runtime playback measurement: video currentTime advanced 0.34 seconds; "
            "duration is 12.00 seconds"
        ),
    )

    row = next(r for r in issues_mod.list_issues(tmp_db, scan_id) if r.pipeline == "visual")
    assert row.review_lane == "expert_review"
    assert row.evidence_confidence == "medium"
    assert row.wcag_sc == "2.2.2"
    assert row.wcag_name == "Pause, Stop, Hide"


def test_alfa_rows_expose_rule_name_diagnostic_and_outcome_boundary(
    tmp_db: sqlite3.Connection,
) -> None:
    scan_id = _seed_two_pipelines(tmp_db)
    page_id = int(
        tmp_db.execute("SELECT id FROM pages WHERE scan_id = ? LIMIT 1", (scan_id,)).fetchone()[
            "id"
        ]
    )
    for outcome, summary in (
        (
            "failed",
            "The test target fails the following requirements: - The link does not have an "
            "accessible name",
        ),
        ("cant_tell", "The rule has outstanding questions that must be answered"),
    ):
        tmp_db.execute(
            """
            INSERT INTO page_a11y_findings
                (page_id, scan_id, pipeline, engine_outcome, criterion_sc, rule_id, wcag_sc,
                 wcag_scs, wcag_level, help, help_url, target_selector, failure_summary,
                 target_hash, status)
            VALUES (?, ?, 'alfa', ?, '2.4.4', 'sia-r11', '2.4.4', '2.4.4', 'A',
                'WCAG 2.4.4: Link Purpose (In Context)',
                'https://alfa.siteimprove.com/rules/sia-r11',
                '{"type":"element","name":"a","attributes":[]}', ?, ?, 'new')
            """,
            (page_id, scan_id, outcome, summary, f"alfa-{outcome}"),
        )

    alfa_rows = [row for row in issues_mod.list_issues(tmp_db, scan_id) if row.pipeline == "alfa"]
    assert len(alfa_rows) == 2
    failed = next(row for row in alfa_rows if row.issue_key.endswith(":failed"))
    review = next(row for row in alfa_rows if row.issue_key.endswith(":cant_tell"))
    assert failed.review_lane == "likely_barrier"
    assert failed.wcag_name == "Link Purpose (In Context)"
    assert "link does not have an accessible name" in failed.title.lower()
    assert review.review_lane == "expert_review"
    assert "this is not a failure" in review.evidence_summary.lower()


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
    page = tmp_db.execute("SELECT id FROM pages WHERE scan_id = ? LIMIT 1", (scan_id,)).fetchone()
    _seed_responsive_finding(tmp_db, scan_id, int(page["id"]))

    rows = issues_mod.list_issues(tmp_db, scan_id)
    resp_rows = [r for r in rows if r.pipeline == "responsive"]
    assert len(resp_rows) == 1, (
        f"expected exactly one responsive issue; pipelines seen: {[r.pipeline for r in rows]}"
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

    detail = issues_mod.get_issue_detail(tmp_db, scan_id, "responsive:responsive-reflow-overflow")
    assert detail is not None
    assert len(detail.pages) == 1
    assert detail.pages[0].page_url == page["url_normalized"]
    # Verify steps come through from the YAML card.
    assert detail.verify_manual
    assert detail.help_url and "w3.org" in detail.help_url
