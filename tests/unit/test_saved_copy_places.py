"""Name the element each occurrence came from, so the inspector can outline it exactly.

An image from the image text check and an AI review finding carry no selector
a browser can use. The saved copy is the document both read, so the server
runs their own walks over it again and names each element by its place among
elements of its kind, counted the way a browser counts them.
"""

from __future__ import annotations

import gzip
import json
import sqlite3

from audit.analyzer.semantic.extractor import extract_headings, extract_links, locate_ordinals
from audit.db import repo
from audit.evaluation import get_page_evidence
from audit.extractor.html_images import extract_image_refs, locate_image_refs
from audit.extractor.places import Place
from audit.extractor.svg_text import find_inline_svg_text, locate_inline_svg_text
from audit.web import image_findings_queries, issues

BASE = "https://example.com/page"


def test_image_places_follow_the_extractor_positions_in_document_order() -> None:
    body = (
        b"<html><body>"
        b'<picture><source srcset="/a.webp 1x, /a2.webp 2x"><img src="/a.png" alt="A"></picture>'
        b'<img src="/b.png" alt="">'
        b'<noscript><img src="/b.png" alt=""></noscript>'
        b'<template><img src="/c.png"></template>'
        b'<img src="data:image/png;base64,AAAA">'
        b"</body></html>"
    )
    refs = extract_image_refs(body, BASE)
    places = locate_image_refs(body, BASE)
    assert sorted(places) == [ref.position for ref in refs]
    by_candidate = {(p.tag, p.candidate): p for p in places.values()}
    # selectolax lists every img before any picture source; the places are
    # the browser's document order all the same.
    assert by_candidate[("img", "/a.png")].place == Place("img", 0, 3)
    assert by_candidate[("source", "/a.webp")].place == Place("picture > source", 0, 1)
    assert by_candidate[("source", "/a2.webp")].place == Place("picture > source", 0, 1)
    # The data: image is skipped by the extractor, so it takes no position,
    # but it is still an img a browser counts.
    b_places = [p.place for p in places.values() if p.candidate == "/b.png"]
    assert b_places == [Place("img", 1, 3), None]  # the <noscript> copy has no place
    assert [p.place for p in places.values() if p.candidate == "/c.png"] == [None]


def test_inline_svg_places_count_every_svg() -> None:
    body = (
        b"<html><body><svg><circle/></svg>"
        b"<svg><svg><text>Inner</text></svg><text>Outer</text></svg>"
        b"<noscript><svg><text>Fallback</text></svg></noscript>"
        b"</body></html>"
    )
    hits = find_inline_svg_text(body)
    places = locate_inline_svg_text(body)
    assert [hit.position for hit in hits] == sorted(places)
    assert [(p.place, p.visible_text) for p in places.values()] == [
        (Place("svg", 1, 3), "Inner Outer"),
        (None, "Fallback"),
    ]


def test_ai_review_ordinals_name_the_analyzed_element() -> None:
    body = (
        b"<html><body><h2>Second level first</h2><h1>Title</h1>"
        b'<p><a class="more" href="/one">More</a></p><p><a class="more" href="/two">More</a></p>'
        b"</body></html>"
    )
    headings = {record.text: record for record in extract_headings(body)}
    links = extract_links(body)
    findings = [
        ("2.4.6", headings["Second level first"].selector, headings["Second level first"].snippet),
        ("2.4.6", headings["Title"].selector, headings["Title"].snippet),
        ("2.4.4", links[1].selector, links[1].snippet),
        # The recorded element is not the one there any more.
        ("2.4.4", links[1].selector, '<a class="more" href="/elsewhere">More</a>'),
        ("2.4.4", "a.more[ord=9]", links[1].snippet),
        ("9.9.9", links[1].selector, links[1].snippet),
        ("2.4.4", "a#top", links[1].snippet),
    ]
    # selectolax lists h1 before h2, so the h2 that comes first is ord 1.
    assert headings["Second level first"].selector == "h2[ord=1]"
    assert locate_ordinals(body, findings) == [
        Place("h2", 0, 1),
        Place("h1", 0, 1),
        Place("a", 1, 2),
        None,
        None,
        None,
        None,
    ]


CAPTURE = (
    b"<!doctype html><html><head><title>Fixture</title></head><body>"
    b'<img src="/sale.png" alt="Sale ends Friday">'
    b'<img src="/logo.png" alt="Example">'
    b'<img src="/sale.png" alt="Sale ends Friday">'
    b'<noscript><img src="/sale.png" alt="Sale ends Friday"></noscript>'
    b'<p><a class="more" href="/one">More</a></p><p><a class="more" href="/two">More</a></p>'
    b"</body></html>"
)


def _seed_page(conn: sqlite3.Connection) -> tuple[int, int]:
    scan_id = int(
        conn.execute(
            "INSERT INTO scans(seed_url,status,config_json,started_at,page_count) "
            "VALUES('https://example.com/','completed',?,'2026-09-26 12:00:00',1)",
            (json.dumps({"method_coverage_version": 1}),),
        ).lastrowid
        or 0
    )
    page_id = int(
        conn.execute(
            "INSERT INTO pages(scan_id,url_normalized,status_code,render_mode,rendered_html) "
            "VALUES(?,?,200,'js',?)",
            (scan_id, BASE, gzip.compress(CAPTURE)),
        ).lastrowid
        or 0
    )
    image_ids: dict[str, int] = {}
    for ref in extract_image_refs(CAPTURE, BASE):
        if ref.url not in image_ids:
            image_ids[ref.url] = repo.upsert_image(
                conn,
                content_hash=ref.url.ljust(64, "x")[:64],
                src_url=ref.url,
                mime="image/png",
                bytes_len=10,
                width=100,
                height=20,
                blob_path=None,
                has_svg_text=False,
                scan_id=scan_id,
            )
        repo.upsert_page_image(
            conn,
            page_id=page_id,
            image_id=image_ids[ref.url],
            alt_text=ref.alt,
            role=None,
            context_snippet=None,
            position=ref.position,
        )
    sale = image_ids["https://example.com/sale.png"]
    repo.upsert_analysis(
        conn,
        image_id=sale,
        ocr_text="Sale ends Friday",
        ocr_confidence=99,
        vlm_classification="informational",
        vlm_rationale="Text",
        has_text=True,
        model_versions={"test": "v1"},
    )
    repo.upsert_finding(
        conn,
        image_id=sale,
        scan_id=scan_id,
        severity="minor",
        priority_score=2,
        remediation_hint=None,
    )
    link = extract_links(CAPTURE)[1]
    conn.execute(
        "INSERT INTO page_a11y_findings (page_id, scan_id, pipeline, rule_id, wcag_sc, "
        "wcag_level, impact, help, target_selector, failure_summary, html_snippet, target_hash) "
        "VALUES (?, ?, 'semantic', 'semantic:2.4.4', '2.4.4', 'A', 'moderate', 'Link purpose', "
        "?, 'unclear', ?, 'semantic-1')",
        (page_id, scan_id, link.selector, link.snippet),
    )
    conn.commit()
    return scan_id, page_id


def test_page_evidence_names_each_image_and_ai_review_element(tmp_db: sqlite3.Connection) -> None:
    scan_id, page_id = _seed_page(tmp_db)
    evidence = get_page_evidence(tmp_db, scan_id=scan_id, page_id=page_id)
    assert evidence is not None

    # The key is the Issues page's key for the image's group.
    image_keys = {
        row.issue_key
        for row in issues.list_issues(tmp_db, scan_id)
        if row.issue_key.startswith("image:")
    }
    sale = [i for i in evidence["image_occurrences"] if i["src_url_canonical"].endswith("sale.png")]
    assert {i["issue_key"] for i in sale} == image_keys == {"image:informational_adequate"}
    logo = [i for i in evidence["image_occurrences"] if i["src_url_canonical"].endswith("logo.png")]
    assert [i["issue_key"] for i in logo] == [None]

    assert [(i["locator"], i["hidden_in_copy"]) for i in sale] == [
        (
            {"kind": "img", "index": 0, "total": 3, "candidate": "/sale.png", "text": None},
            False,
        ),
        (
            {"kind": "img", "index": 2, "total": 3, "candidate": "/sale.png", "text": None},
            False,
        ),
        (None, True),
    ]
    (semantic,) = evidence["a11y_findings"]
    assert semantic["element_place"] == {"selector": "a", "index": 1, "total": 2}


def test_page_evidence_without_a_saved_copy_names_nothing(tmp_db: sqlite3.Connection) -> None:
    scan_id, page_id = _seed_page(tmp_db)
    tmp_db.execute("UPDATE pages SET rendered_html = NULL WHERE id = ?", (page_id,))
    evidence = get_page_evidence(tmp_db, scan_id=scan_id, page_id=page_id)
    assert evidence is not None
    assert {i["locator"] for i in evidence["image_occurrences"]} == {None}
    assert {i["hidden_in_copy"] for i in evidence["image_occurrences"]} == {False}
    assert [f["element_place"] for f in evidence["a11y_findings"]] == [None]


def test_image_issue_key_matches_the_issue_rows() -> None:
    assert image_findings_queries.image_issue_key(None, None) == "image:unclassified_unknown"
    assert image_findings_queries.image_issue_key("logo", "missing") == "image:logo_missing"
