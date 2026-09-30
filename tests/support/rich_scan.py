"""The rich export fixture: one completed scan that reaches every export path we pin.

``tests/unit/test_export_goldens.py`` records its goldens from this scan,
``tests/unit/test_export_diff_script.py`` renders it through
``scripts/export_diff.py``, and ``tests/ui/test_export_route_parity.py``
downloads it through the real export route. It lives under ``tests/support``
so those modules share one seed instead of importing it from each other.

The scan reaches the paths the small image-pipeline fixture does not: more
issues than the workbook has tabs for, non-card issues on several pages, an
inline SVG compared against its text snippet, an axe rule with no
documentation link, a CSV field holding a bare carriage return, an expert
evaluation with manual evidence (with and without references), a
click-through ledger, and retained evidence screenshots: one wider than the
workbook's evidence column, one narrower, one whose blob is missing, and one
on an issue pooled past the per-issue tab cap.

The screenshots are committed PNG files under ``tests/fixtures/evidence``
rather than images drawn at test time: the workbook embeds the bytes as
they are, and an image library's encoder output is not stable across
versions.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any

from audit import evaluation
from audit.blob_store import BlobStore
from audit.db import repo
from audit.synthesizer.findings import synthesize_findings

EVIDENCE_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "evidence"
# Wider than the workbook's evidence column (240 px), so it is scaled down.
EVIDENCE_WIDE = EVIDENCE_DIR / "wide-480x120.png"
# Narrower than the column, so it is embedded at its own size.
EVIDENCE_NARROW = EVIDENCE_DIR / "narrow-160x90.png"
# Recorded on a finding but absent from the blob store: the workbook must
# leave the evidence cell blank rather than fail.
MISSING_EVIDENCE_HASH = "e" * 64


def evidence_hash(path: Path) -> str:
    """The content hash the blob store files ``path`` under."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_evidence_blobs(blob_dir: Path) -> BlobStore:
    """Store the committed evidence screenshots in a blob store at ``blob_dir``."""
    store = BlobStore(blob_dir)
    for path in (EVIDENCE_WIDE, EVIDENCE_NARROW):
        store.store(path.read_bytes(), "image/png")
    return store


def database_path(conn: sqlite3.Connection) -> Path:
    """The file behind ``conn``'s main database, as SQLite reports it."""
    for row in conn.execute("PRAGMA database_list").fetchall():
        if row[1] == "main":
            return Path(row[2])
    raise LookupError("connection has no main database file")


_RICH_SEED = "https://example.org/"
_RICH_PAGES = (
    ("https://example.org/", "Home"),
    ("https://example.org/about", "About us"),
    ("https://example.org/contact", "Contact"),
    # No title: the workbook falls back to the URL for "Where".
    ("https://example.org/products", None),
    ("https://example.org/blog", "Blog"),
)
# Synthetic axe rules unknown to the rule book. Together with the named
# groups below they push the scan past the workbook's per-issue tab cap.
_SYNTHETIC_RULES = 36
_SYNTHETIC_IMPACTS = ("critical", "serious", "moderate", "minor")
_SYNTHETIC_CRITERIA = (("1.3.1", "A"), ("2.4.7", "AA"), ("3.3.2", "A"), ("2.5.8", "AA"))
_MODELS = {"ocr": "tesseract-test", "vlm": "stub:1", "prompt": "v1-stub"}
_AXE_DOCS = "https://dequeuniversity.com/rules/axe/4.10/{rule_id}"


def dom_finding(
    conn: sqlite3.Connection,
    *,
    scan_id: int,
    page_id: int,
    rule_id: str,
    help_text: str,
    target: str,
    impact: str | None,
    wcag_sc: str | None = None,
    wcag_level: str | None = None,
    pipeline: str = "axe",
    status: str = "new",
    help_url: str | None = _AXE_DOCS,
    failure_summary: str = "Fix any of the following: the rule's check failed.",
    html_snippet: str | None = None,
    engine_outcome: str = "failed",
    revealed_by: str | None = None,
    screenshot_hash: str | None = None,
) -> None:
    """Insert one ``page_a11y_findings`` row with fixture defaults."""
    if help_url:
        help_url = help_url.format(rule_id=rule_id)
    conn.execute(
        """
        INSERT INTO page_a11y_findings
            (page_id, scan_id, pipeline, criterion_sc, rule_id, wcag_sc, wcag_scs,
             wcag_level, impact, help, help_url, target_selector, failure_summary,
             html_snippet, target_hash, status, engine_outcome, revealed_by,
             screenshot_hash)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            page_id,
            scan_id,
            pipeline,
            wcag_sc if pipeline != "axe" else None,
            rule_id,
            wcag_sc,
            wcag_sc,
            wcag_level,
            impact,
            help_text,
            help_url,
            target,
            failure_summary,
            html_snippet,
            f"{rule_id}|{page_id}|{target}",
            status,
            engine_outcome,
            revealed_by,
            screenshot_hash,
        ),
    )


def seed_rich_scan(conn: sqlite3.Connection) -> int:
    """Seed one completed scan that reaches every export code path we pin.

    The evidence screenshots it references are stored separately, with
    :func:`write_evidence_blobs`; without them the workbook embeds nothing.
    """
    config = {
        "axe_level": "AA",
        "js_eager": True,
        "viewport": "1280x800",
        "interaction_checks_enabled": True,
        "interaction_coverage_version": 2,
    }
    cur = conn.execute(
        "INSERT INTO scans (seed_url, status, page_count, finding_count, error_count, "
        "config_json, started_at, finished_at, interaction_pages_probed, "
        "interaction_states_total) "
        "VALUES (?, 'completed', ?, 0, 1, ?, '2026-04-22 12:00:00', "
        "'2026-04-22 12:30:00', 2, 5)",
        (_RICH_SEED, len(_RICH_PAGES), json.dumps(config, sort_keys=True)),
    )
    scan_id = int(cur.lastrowid or 0)
    home, about, contact, products, blog = (
        repo.upsert_page(
            conn,
            scan_id=scan_id,
            url_normalized=url,
            status_code=200,
            title=title,
            render_mode="js",
            html_hash=str(index) * 64,
        )
        for index, (url, title) in enumerate(_RICH_PAGES)
    )
    all_pages = (home, about, contact, products, blog)

    def dom(page_id: int, rule_id: str, help_text: str, target: str, **kwargs: Any) -> None:
        dom_finding(
            conn,
            scan_id=scan_id,
            page_id=page_id,
            rule_id=rule_id,
            help_text=help_text,
            target=target,
            **kwargs,
        )

    # Rule-book axe card on three pages, one occurrence already rejected
    # (a "Triaged subset" receipt) and one revealed by a click. Its first
    # occurrence carries the wide screenshot, which the workbook scales down.
    contrast = {"impact": "serious", "wcag_sc": "1.4.3", "wcag_level": "AA"}
    contrast_help = "Elements must meet minimum color contrast"
    snippet = '<span class="muted">low text</span>'
    dom(
        home,
        "color-contrast",
        contrast_help,
        "p > span.muted",
        html_snippet=snippet,
        screenshot_hash=evidence_hash(EVIDENCE_WIDE),
        **contrast,
    )
    dom(home, "color-contrast", contrast_help, "footer small", **contrast)
    dom(about, "color-contrast", contrast_help, ".details p", revealed_by="Show more", **contrast)
    dom(contact, "color-contrast", contrast_help, "label.hint", status="false_positive", **contrast)
    dom(
        home,
        "image-alt",
        "Images must have alternative text",
        "main > img.banner",
        impact="critical",
        wcag_sc="1.1.1",
        wcag_level="A",
        html_snippet='<img class="banner" src="banner.png">',
    )
    # More locations on one page than a card, a tab, or a Page References
    # row lists: every overflow note renders. The first occurrence records a
    # screenshot whose blob is gone, so the tab embeds nothing.
    for index in range(1, 13):
        dom(
            home,
            "link-name",
            "Links must have discernible text",
            f"nav > a:nth-child({index})",
            impact="serious",
            wcag_sc="4.1.2",
            wcag_level="A",
            html_snippet=f'<a class="nav-{index}" href="/p{index}"></a>',
            screenshot_hash=MISSING_EVIDENCE_HASH if index == 1 else None,
        )
    # Fully triaged: Appendix A only.
    dom(
        contact,
        "label",
        "Form elements must have labels",
        "input[type=text]",
        impact="critical",
        wcag_sc="4.1.2",
        wcag_level="A",
        status="accepted_risk",
    )
    # Unknown to the rule book: the "human review needed" card.
    dom(
        about,
        "color-contrast-enhanced",
        "Elements must meet enhanced color contrast",
        "p.subtle",
        impact="serious",
        wcag_sc="1.4.6",
        wcag_level="AAA",
    )
    # Best-practice groups spanning pages: no card, so the workbook's Page
    # References sheet resolves their locations issue by page. Only the
    # heading group's second page has a screenshot (narrower than the
    # evidence column), so the tab must look past a page without one.
    for page_id in (home, about, products):
        dom(
            page_id,
            "page-has-heading-one",
            "Page should contain a level-one heading",
            "body",
            impact="moderate",
            screenshot_hash=evidence_hash(EVIDENCE_NARROW) if page_id == about else None,
        )
    for page_id in (products, blog):
        dom(
            page_id,
            "region",
            "All page content should be contained by landmarks",
            "div.promo",
            impact="moderate",
        )
    # An axe rule with no documentation link anywhere, NULL on one page and
    # empty on the other: the issue detail's last-resort help_url lookup.
    for page_id, url in ((home, None), (blog, "")):
        dom_finding(
            conn,
            scan_id=scan_id,
            page_id=page_id,
            rule_id="fixture-empty-help",
            help_text="Fixture rule without a documentation link",
            target="div.card",
            impact="moderate",
            wcag_sc="1.3.1",
            wcag_level="A",
            help_url=url,
        )
    # Enough distinct rules to overflow the per-issue tabs. One help text
    # carries characters Excel forbids in sheet names.
    for number in range(1, _SYNTHETIC_RULES + 1):
        sc, level = _SYNTHETIC_CRITERIA[number % len(_SYNTHETIC_CRITERIA)]
        help_text = (
            "Fixture: buttons [primary/secondary] need names?"
            if number == 1
            else f"Fixture rule {number:02d} synthetic check"
        )
        spread = (home, about) if number % 3 == 0 else (all_pages[number % len(all_pages)],)
        for page_id in spread:
            dom(
                page_id,
                f"fixture-rule-{number:02d}",
                help_text,
                f"#fixture-{number:02d}",
                impact=_SYNTHETIC_IMPACTS[number % len(_SYNTHETIC_IMPACTS)],
                wcag_sc=sc,
                wcag_level=level,
            )

    # Semantic 2.4.4: two unconfirmed leads on two pages plus one occurrence
    # an expert confirmed, so the group splits into a card and a lead.
    semantic = {"impact": "moderate", "wcag_sc": "2.4.4", "wcag_level": "A", "pipeline": "semantic"}
    link_help = "The link 'click here' doesn't say where it goes."
    link_url = "https://www.w3.org/WAI/WCAG22/Understanding/link-purpose-in-context.html"
    for page_id, status in ((home, "new"), (about, "new"), (contact, "in_progress")):
        dom(
            page_id,
            "semantic:2.4.4",
            link_help,
            "a.cta[ord=3]",
            status=status,
            help_url=link_url,
            html_snippet='<a class="cta" href="/x">click here</a>',
            **semantic,
        )
    # Keyboard trap behind a menu the click-through probe had to open. It
    # ranks past the per-issue tab cap, and the pooled sheet embeds no
    # screenshots, so its screenshot must not appear anywhere.
    dom(
        home,
        "keyboard-trap-stuck",
        "Keyboard users must be able to leave the component.",
        "#menu-trap",
        impact="critical",
        wcag_sc="2.1.2",
        wcag_level="A",
        pipeline="keyboard",
        help_url="https://www.w3.org/WAI/WCAG22/Understanding/no-keyboard-trap.html",
        failure_summary=(
            "Measured focus exit behavior: 4 Tab attempts and 4 Shift+Tab attempts "
            "remained on #menu-trap (8 failed exit attempts total)."
        ),
        revealed_by="Open menu",
        screenshot_hash=evidence_hash(EVIDENCE_NARROW),
    )
    # Alfa: a failed ACT rule with a structured target, and a cantTell.
    dom(
        home,
        "sia-r2",
        "1.1.1 Non-text Content",
        '{"path":["html","body","img"]}',
        impact=None,
        wcag_sc="1.1.1",
        wcag_level="A",
        pipeline="alfa",
        help_url="https://alfa.siteimprove.com/rules/sia-r2",
        failure_summary="The image has no accessible name.",
    )
    dom(
        about,
        "sia-r111",
        "2.5.8 Target Size (Minimum)",
        "button.tiny",
        impact=None,
        wcag_sc="2.5.8",
        wcag_level="AA",
        pipeline="alfa",
        help_url="https://alfa.siteimprove.com/rules/sia-r111",
        failure_summary="Alfa could not decide whether the target spacing is sufficient.",
        engine_outcome="cant_tell",
    )
    axe_rows = conn.execute(
        "SELECT COUNT(DISTINCT page_id) AS pages, COUNT(*) AS total "
        "FROM page_a11y_findings WHERE scan_id = ? AND pipeline = 'axe'",
        (scan_id,),
    ).fetchone()
    alfa_rows = conn.execute(
        "SELECT SUM(engine_outcome = 'failed') AS failed, SUM(engine_outcome = 'cant_tell') AS ct "
        "FROM page_a11y_findings WHERE scan_id = ? AND pipeline = 'alfa'",
        (scan_id,),
    ).fetchone()
    conn.execute(
        "UPDATE scans SET axe_pages_scanned = ?, axe_violations_total = ?, "
        "alfa_pages_scanned = 2, alfa_failed_total = ?, alfa_cant_tell_total = ? WHERE id = ?",
        (axe_rows["pages"], axe_rows["total"], alfa_rows["failed"], alfa_rows["ct"], scan_id),
    )

    # Images. An essential banner missing alt on two pages (a multi-page
    # review lead), an adequately described logo (informational), and an
    # unclassified OCR hit.
    def image(content: str, src: str, *, svg: bool = False) -> int:
        return repo.upsert_image(
            conn,
            content_hash=content * 64,
            src_url=src,
            mime="image/svg+xml" if svg else "image/png",
            bytes_len=None if svg else 512,
            width=None if svg else 600,
            height=None if svg else 100,
            blob_path=None if svg else f"{content * 2}/{content * 64}.png",
            has_svg_text=svg,
            scan_id=scan_id,
        )

    banner = image("b", "https://example.org/banner.png")
    for position, page_id in enumerate((home, about)):
        repo.upsert_page_image(
            conn,
            page_id=page_id,
            image_id=banner,
            alt_text=None,
            role=None,
            context_snippet="Buy widgets now",
            position=position,
            above_fold=page_id == home,
        )
    repo.upsert_analysis(
        conn,
        image_id=banner,
        ocr_text="BUY WIDGETS NOW",
        ocr_confidence=92.5,
        vlm_classification="essential",
        vlm_rationale="Promotional banner with text as image.",
        has_text=True,
        model_versions=_MODELS,
    )
    logo = image("c", "https://example.org/logo.png")
    repo.upsert_page_image(
        conn,
        page_id=home,
        image_id=logo,
        alt_text="Acme Corp",
        role=None,
        context_snippet=None,
        position=2,
    )
    repo.upsert_analysis(
        conn,
        image_id=logo,
        ocr_text="Acme Corp",
        ocr_confidence=88.0,
        vlm_classification="logo",
        vlm_rationale="Brand mark.",
        has_text=True,
        model_versions=_MODELS,
    )
    hours = image("d", "https://example.org/hours.png")
    repo.upsert_page_image(
        conn,
        page_id=contact,
        image_id=hours,
        alt_text=None,
        role=None,
        context_snippet="Opening hours",
        position=0,
    )
    repo.upsert_analysis(
        conn,
        image_id=hours,
        ocr_text="OPEN DAILY 9-5",
        ocr_confidence=71.0,
        has_text=True,
        model_versions=_MODELS,
    )
    # Inline SVG with no OCR analysis: the issue projection compares its alt
    # against the captured text snippet. The alt holds a bare carriage
    # return, which the CSV writers must quote and draft labeling must keep.
    svg = image("e", "inline-svg://https://example.org/#0", svg=True)
    for position, page_id in ((3, home), (1, blog)):
        repo.upsert_page_image(
            conn,
            page_id=page_id,
            image_id=svg,
            alt_text="Company\rlogo",
            role="img",
            context_snippet="Spring sale ends Friday",
            position=position,
        )
    synthesize_findings(conn, scan_id=scan_id)

    # Click-through ledger: one page stopped by the click budget.
    for page_id, found, operated, states, limits, detail in (
        (home, 12, 8, 3, "clicks", "Stopped after the click budget."),
        (about, 4, 4, 2, "", ""),
    ):
        conn.execute(
            "INSERT INTO scan_interaction_runs (scan_id, page_id, controls_found, "
            "clicks_attempted, clicks_succeeded, controls_operated, states, limits, detail) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (scan_id, page_id, found, operated, operated, operated, states, limits, detail),
        )

    # An expert evaluation in progress, with manual outcomes and evidence.
    evaluation.upsert_evaluation(
        conn,
        scan_id,
        {
            "status": "in_progress",
            "reviewer": "Fixture Reviewer",
            "purpose": "Pre-launch accessibility review.",
            "scope_included": "Public marketing pages.",
            "scope_excluded": "Checkout.",
            "sample_description": "Five representative templates.",
            "methods_note": "Automated scan plus keyboard and screen reader checks.",
            "limitations": "No mobile assistive technology testing.",
        },
    )
    for sc, outcome, rationale in (
        ("1.1.1", "fail", "Banner image has no text alternative."),
        ("2.4.7", "pass", "Focus indicator visible on every control tested."),
        ("1.2.1", "not_tested", "No prerecorded media on the sampled pages."),
    ):
        evaluation.update_manual_check(
            conn, scan_id=scan_id, criterion_sc=sc, outcome=outcome, rationale=rationale
        )
    evaluation.add_manual_evidence(
        conn,
        scan_id=scan_id,
        criterion_sc="1.1.1",
        note="Screen reader announced the file name.",
        page_id=home,
        evidence_url="https://evidence.example.org/1-1-1",
    )
    # No page and no external reference: the reports print their "n/a"
    # placeholders for both.
    evaluation.add_manual_evidence(
        conn,
        scan_id=scan_id,
        criterion_sc="2.4.7",
        note="Checked with the keyboard only.",
        page_id=None,
        evidence_url="",
    )
    return scan_id
