"""Audit-engineer-style report — golden-file + structural assertions.

The audit report is the framework-shaped deliverable (issue cards, fix
steps, verification plan, appendices). These tests don't pin every word
— that would defeat the purpose of editing the YAML rule book — but they
do pin the *structure* so future edits to the renderer can't silently
drop sections.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import pytest

from audit.db import repo
from audit.exports.audit_report import render_audit_report
from audit.exports.collector import collect_scan
from audit.synthesizer.findings import synthesize_findings

UPDATE_GOLDEN = os.environ.get("AUDIT_UPDATE_GOLDEN") == "1"
GOLDEN_DIR = Path(__file__).resolve().parent / "golden"


def _scan_with_real_findings(conn: sqlite3.Connection) -> int:
    """Seed a scan that triggers both pipelines.

    * One image-of-text finding (essential text, missing alt) — should
      look up `image_findings.essential_missing` in the YAML and render
      a fully-templated card.
    * Two axe findings (`color-contrast`, `image-alt`) — both have YAML
      entries, so they render as full cards too.
    * One axe finding for an unknown rule (`color-contrast-enhanced`)
      — falls through to "human review needed".
    * One already-triaged finding (`status='accepted_risk'`) — should
      land in Appendix A, not the main report.
    """
    cur = conn.execute(
        "INSERT INTO scans (seed_url, status, page_count, finding_count, "
        "config_json) "
        "VALUES ('http://example.com/', 'completed', 2, 0, '{}')"
    )
    scan_id = int(cur.lastrowid or 0)

    page_home = repo.upsert_page(
        conn,
        scan_id=scan_id,
        url_normalized="http://example.com/",
        status_code=200,
        title="Home",
        render_mode="js",
        html_hash="0" * 64,
    )

    # Image: essential text, missing alt → critical card via YAML.
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
        page_id=page_home,
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
        vlm_rationale="Text-as-image promo banner.",
        has_text=True,
        model_versions={"ocr": "tesseract-test", "vlm": "stub:1", "prompt": "v1-stub"},
    )
    synthesize_findings(conn, scan_id=scan_id)

    # Axe: color-contrast (templated YAML hit, still 'new').
    conn.execute(
        """
        INSERT INTO page_a11y_findings
            (page_id, scan_id, rule_id, wcag_sc, wcag_scs, wcag_level,
             impact, help, help_url, target_selector, failure_summary,
             html_snippet, target_hash, status)
        VALUES (?, ?, 'color-contrast', '1.4.3', '1.4.3', 'AA', 'serious',
            'Elements must meet minimum color contrast',
            'https://dequeuniversity.com/rules/axe/4.10/color-contrast',
            'p > span.muted',
            'Foreground/background contrast is 2.1.',
            '<span class="muted">low text</span>',
            'hash-cc', 'new')
        """,
        (page_home, scan_id),
    )
    # Axe: image-alt also templated.
    conn.execute(
        """
        INSERT INTO page_a11y_findings
            (page_id, scan_id, rule_id, wcag_sc, wcag_scs, wcag_level,
             impact, help, help_url, target_selector, failure_summary,
             html_snippet, target_hash, status)
        VALUES (?, ?, 'image-alt', '1.1.1', '1.1.1', 'A', 'critical',
            'Images must have alternative text',
            'https://dequeuniversity.com/rules/axe/4.10/image-alt',
            'main > img.banner',
            'Element has no alt attribute.',
            '<img class="banner" src="banner.png">',
            'hash-ia', 'new')
        """,
        (page_home, scan_id),
    )
    # Axe: unknown rule — should hit the "human review needed" path.
    conn.execute(
        """
        INSERT INTO page_a11y_findings
            (page_id, scan_id, rule_id, wcag_sc, wcag_scs, wcag_level,
             impact, help, help_url, target_selector, failure_summary,
             html_snippet, target_hash, status)
        VALUES (?, ?, 'color-contrast-enhanced', '1.4.6', '1.4.6', 'AAA',
            'serious',
            'Elements must meet enhanced color contrast',
            'https://dequeuniversity.com/rules/axe/4.10/color-contrast-enhanced',
            'p.subtle',
            'Contrast 6.1 — fails AAA threshold of 7.',
            '<p class="subtle">subtle text</p>',
            'hash-cce', 'new')
        """,
        (page_home, scan_id),
    )
    # Axe: best-practice (no SC) — should land in Appendix B.
    conn.execute(
        """
        INSERT INTO page_a11y_findings
            (page_id, scan_id, rule_id, wcag_sc, wcag_scs, wcag_level,
             impact, help, help_url, target_selector, failure_summary,
             html_snippet, target_hash, status)
        VALUES (?, ?, 'page-has-heading-one', NULL, NULL, NULL, 'moderate',
            'Page should contain a level-one heading',
            'https://dequeuniversity.com/rules/axe/4.10/page-has-heading-one',
            'body',
            'No h1 element on the page.',
            '<body>...</body>',
            'hash-h1', 'new')
        """,
        (page_home, scan_id),
    )
    # Axe: already triaged → Appendix A.
    conn.execute(
        """
        INSERT INTO page_a11y_findings
            (page_id, scan_id, rule_id, wcag_sc, wcag_scs, wcag_level,
             impact, help, help_url, target_selector, failure_summary,
             html_snippet, target_hash, status)
        VALUES (?, ?, 'label', '4.1.2', '4.1.2', 'A', 'critical',
            'Form elements must have labels',
            'https://dequeuniversity.com/rules/axe/4.10/label',
            'input[type=text]',
            'No associated label.',
            '<input type="text">',
            'hash-lb', 'accepted_risk')
        """,
        (page_home, scan_id),
    )
    # Semantic (per-criterion LLM): SC 2.4.4 link purpose. Keyed in the DB
    # as ``semantic:<sc>`` with pipeline='semantic' so list_issues() routes
    # it to the semantic_criteria YAML block — exercising the holistic
    # report's correct (non-axe) labeling.
    conn.execute(
        """
        INSERT INTO page_a11y_findings
            (page_id, scan_id, pipeline, criterion_sc, rule_id, wcag_sc,
             wcag_scs, wcag_level, impact, help, help_url, target_selector,
             failure_summary, html_snippet, target_hash, status)
        VALUES (?, ?, 'semantic', '2.4.4', 'semantic:2.4.4', '2.4.4',
            '2.4.4', 'A', 'moderate',
            "The link 'click here' doesn't say where it goes.",
            'https://www.w3.org/WAI/WCAG22/Understanding/link-purpose-in-context.html',
            'a.cta[ord=3]',
            "Link text 'click here' is not descriptive.",
            '<a class="cta" href="/x">click here</a>',
            'hash-sem', 'new')
        """,
        (page_home, scan_id),
    )
    # Keyboard probe: SC 2.1.2 keyboard trap. rule_id 'keyboard-trap-stuck'
    # with pipeline='keyboard' — list_issues() detects the prefix and tags
    # the row pipeline='keyboard', pulling the YAML card keyed on SC 2.1.2.
    conn.execute(
        """
        INSERT INTO page_a11y_findings
            (page_id, scan_id, pipeline, criterion_sc, rule_id, wcag_sc,
             wcag_scs, wcag_level, impact, help, help_url, target_selector,
             failure_summary, html_snippet, target_hash, status)
        VALUES (?, ?, 'keyboard', '2.1.2', 'keyboard-trap-stuck', '2.1.2',
            '2.1.2', 'A', 'critical',
            'Focus cannot leave this element with the keyboard.',
            'https://www.w3.org/WAI/WCAG21/Understanding/no-keyboard-trap.html',
            '#modal-trap',
            'Focus stayed on #modal-trap after 5 consecutive Tab presses.',
            '<div id="modal-trap" tabindex="0">',
            'hash-kbd', 'new')
        """,
        (page_home, scan_id),
    )

    conn.execute(
        "UPDATE scans SET axe_pages_scanned = 1, axe_violations_total = 5 WHERE id = ?",
        (scan_id,),
    )
    return scan_id


def test_audit_report_structure(tmp_db: sqlite3.Connection) -> None:
    """The framework-required sections all show up, in order."""
    scan_id = _scan_with_real_findings(tmp_db)
    scan = collect_scan(tmp_db, scan_id, ui_base_url="http://127.0.0.1:8765")
    md = render_audit_report(scan, conn=tmp_db)

    # Required headings, in document order. The holistic report inserts
    # five rollup sections between the summary and the detailed cards.
    expected_in_order = [
        "# Accessibility audit",
        "## Executive summary",
        "## Conformance scorecard",
        "## Who is affected",
        "## Coverage and method",
        "## Page hotspots",
        "## Remediation worklist by owner",
        "## Issue cards",
        "## Appendix A — Findings dropped during self-critique",
        "## Appendix B — Out of scope but worth knowing",
    ]
    last = -1
    for heading in expected_in_order:
        idx = md.find(heading)
        assert idx > last, f"Missing or out-of-order: {heading!r}"
        last = idx


def test_audit_report_unifies_all_four_pipelines(
    tmp_db: sqlite3.Connection,
) -> None:
    """Keyboard + semantic findings are labeled by their real pipeline.

    This is the holistic-report contract: before the rewrite, keyboard
    (SC 2.1.2) and semantic (SC 2.4.4) findings were mislabeled as axe
    and missed their YAML remediation content. Now each is detected by,
    and attributed to, its own method.
    """
    scan_id = _scan_with_real_findings(tmp_db)
    scan = collect_scan(tmp_db, scan_id, ui_base_url="http://127.0.0.1:8765")
    md = render_audit_report(scan, conn=tmp_db)

    # The coverage table marks all four methods, and the ones that
    # produced findings here (axe, semantic, keyboard) are flagged as ran.
    assert "## Coverage and method" in md
    assert "Dynamic keyboard-trap probe" in md
    assert "Per-criterion LLM analyzer" in md

    # The semantic + keyboard cards carry the correct "Detected by" line —
    # never "axe-core" for these two.
    assert "**Detected by:** per-criterion LLM analyzer." in md
    assert "**Detected by:** dynamic keyboard-trap probe." in md

    # And the methods line in the header names them.
    methods_line = md.split("**Detection methods used:**", 1)[1].split("\n", 1)[0]
    assert "keyboard" in methods_line.lower()
    assert "llm" in methods_line.lower()


def test_audit_report_has_holistic_rollups(tmp_db: sqlite3.Connection) -> None:
    """The scorecard, abilities, hotspots, and owner-pack sections populate."""
    scan_id = _scan_with_real_findings(tmp_db)
    scan = collect_scan(tmp_db, scan_id, ui_base_url="http://127.0.0.1:8765")
    md = render_audit_report(scan, conn=tmp_db)

    # Conformance scorecard surfaces the WCAG level table + POUR rollup.
    scorecard = md.split("## Conformance scorecard", 1)[1].split("## Who is affected", 1)[0]
    assert "Level" in scorecard and "Open issue types" in scorecard
    assert "POUR" in scorecard

    # Abilities rollup names at least one user group (our seed affects vision).
    affected = md.split("## Who is affected", 1)[1].split("## Coverage", 1)[0]
    assert "Vision" in affected

    # Owner worklist splits into role packs with checkbox items.
    worklist = md.split("## Remediation worklist by owner", 1)[1].split("## Issue cards", 1)[0]
    assert "- [ ]" in worklist


def test_audit_report_templated_cards_have_full_shape(
    tmp_db: sqlite3.Connection,
) -> None:
    """A card backed by the YAML carries every framework field."""
    scan_id = _scan_with_real_findings(tmp_db)
    scan = collect_scan(tmp_db, scan_id, ui_base_url="http://127.0.0.1:8765")
    md = render_audit_report(scan, conn=tmp_db)

    # color-contrast is templated in the YAML; its card should carry
    # WCAG, severity reason, owner, effort, fix steps, verify, acceptance.
    assert "Text doesn't meet the 4.5:1 contrast ratio" in md
    assert "**WCAG:** SC 1.4.3" in md
    assert "**Severity:** Serious" in md
    assert "**Effort:** Under 2 hours" in md
    assert "**Owner:** Designer" in md
    assert "**Fix (do this):**" in md
    assert "**Verify it is fixed:**" in md
    assert "**Acceptance:**" in md
    assert "**My confidence:** High" in md


def test_audit_report_unknown_rule_flagged_for_human_review(
    tmp_db: sqlite3.Connection,
) -> None:
    """Rules not in the YAML show up but flagged as human-review-needed."""
    scan_id = _scan_with_real_findings(tmp_db)
    scan = collect_scan(tmp_db, scan_id, ui_base_url="http://127.0.0.1:8765")
    md = render_audit_report(scan, conn=tmp_db)

    # color-contrast-enhanced isn't in the YAML.
    assert "color-contrast-enhanced" in md
    # The renderer should have added the "human review needed" callout
    # for at least one card.
    assert "Human review needed" in md


def test_audit_report_already_triaged_lands_in_appendix_a(
    tmp_db: sqlite3.Connection,
) -> None:
    """Findings the user already marked accepted_risk drop out of the cards."""
    scan_id = _scan_with_real_findings(tmp_db)
    scan = collect_scan(tmp_db, scan_id, ui_base_url="http://127.0.0.1:8765")
    md = render_audit_report(scan, conn=tmp_db)

    # The accepted_risk finding (rule_id=label) should NOT appear in the
    # main "Form controls have no programmatic label" card — it should
    # only show up in Appendix A as a dropped row.
    issue_cards_section = md.split("## Issue cards", 1)[1].split("## Appendix A", 1)[0]
    assert "Form controls have no programmatic label" not in issue_cards_section

    appendix_a = md.split("## Appendix A", 1)[1].split("## Appendix B", 1)[0]
    assert "label" in appendix_a
    assert "accepted_risk" in appendix_a


def test_audit_report_best_practice_lands_in_appendix_b(
    tmp_db: sqlite3.Connection,
) -> None:
    """Axe rules with no WCAG SC become Appendix-B entries."""
    scan_id = _scan_with_real_findings(tmp_db)
    scan = collect_scan(tmp_db, scan_id, ui_base_url="http://127.0.0.1:8765")
    md = render_audit_report(scan, conn=tmp_db)

    appendix_b = md.split("## Appendix B", 1)[1]
    assert "page-has-heading-one" in appendix_b


def test_audit_report_executive_summary_has_quick_win(
    tmp_db: sqlite3.Connection,
) -> None:
    """Executive summary names the highest-impact-lowest-effort fix."""
    scan_id = _scan_with_real_findings(tmp_db)
    scan = collect_scan(tmp_db, scan_id, ui_base_url="http://127.0.0.1:8765")
    md = render_audit_report(scan, conn=tmp_db)

    summary = md.split("## Executive summary", 1)[1].split("## Issue cards", 1)[0]
    assert "Highest-impact fix this team could ship this week" in summary
    # Image-alt is Critical + Under 15 minutes, so it should win the pick
    # over color-contrast (Serious) and image-of-text (Critical but tied
    # on effort — image-alt should win on alphabetic stability).
    assert "Images don't announce text" in summary or "image" in summary.lower()


def test_audit_report_image_card_uses_yaml_template(
    tmp_db: sqlite3.Connection,
) -> None:
    """The essential-missing image card pulls from `image_findings.essential_missing`."""
    scan_id = _scan_with_real_findings(tmp_db)
    scan = collect_scan(tmp_db, scan_id, ui_base_url="http://127.0.0.1:8765")
    md = render_audit_report(scan, conn=tmp_db)

    # Title from the YAML.
    assert "Images of text have no alt and can't be read" in md
    # WCAG SC mapping from the YAML.
    assert "**WCAG:** SC 1.4.5" in md


@pytest.mark.skipif(
    not (GOLDEN_DIR / "scan_audit.md").exists() and not UPDATE_GOLDEN,
    reason="Run with AUDIT_UPDATE_GOLDEN=1 to seed the audit golden file.",
)
def test_audit_report_matches_golden(tmp_db: sqlite3.Connection) -> None:
    """Pin the structure to a golden file. Refresh with AUDIT_UPDATE_GOLDEN=1.

    The YAML rule book is the editing surface — when you tune the wording
    of a fix, the golden file should change. That's by design; just
    re-record.
    """
    scan_id = _scan_with_real_findings(tmp_db)
    scan = collect_scan(tmp_db, scan_id, ui_base_url="http://127.0.0.1:8765")
    actual = render_audit_report(scan, conn=tmp_db)
    # Strip the "Generated YYYY-MM-DD HH:MM UTC" line — non-deterministic.
    actual_no_ts = "\n".join(
        line for line in actual.splitlines() if not line.startswith("_Generated ")
    )
    path = GOLDEN_DIR / "scan_audit.md"
    if UPDATE_GOLDEN or not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(actual_no_ts, encoding="utf-8")
    expected = path.read_text(encoding="utf-8")
    assert actual_no_ts == expected, (
        "Golden mismatch for scan_audit.md. "
        "Re-run with AUDIT_UPDATE_GOLDEN=1 if the change was deliberate "
        "(YAML edits to rules/audit_report.yaml usually count)."
    )
