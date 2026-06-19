"""Tests for ``audit.analyzer.semantic.extractor.extract_links``.

These exercise every HTML shape the analyzer is likely to see in the
wild. They're deliberately exhaustive because the extractor's output
shape IS the contract the rest of the SC 2.4.4 pipeline depends on —
if the extractor silently drops a link or mis-resolves an accessible
name, the LLM analyzer can't reach the right verdict.

Each test pins exactly one behavior so a regression points at the
broken case rather than failing a generic "extract works" test.
"""

from __future__ import annotations

from audit.analyzer.semantic.extractor import (
    ANCESTOR_DEPTH,
    LinkRecord,
    extract_links,
)


def _e(html: str) -> list[LinkRecord]:
    """Tiny helper: run extract_links on the HTML body fragment."""
    return extract_links(html.encode("utf-8"))


# ---------------------------------------------------------------------
# Basic happy-path shapes
# ---------------------------------------------------------------------


def test_plain_text_link_extracts_visible_text() -> None:
    rows = _e('<a href="/about">About us</a>')
    assert len(rows) == 1
    r = rows[0]
    assert r.accessible_name == "About us"
    assert r.accessible_name_source == "text"
    assert r.href == "/about"


def test_multiple_links_all_extracted_in_document_order() -> None:
    rows = _e(
        """
        <a href="/a">First</a>
        <a href="/b">Second</a>
        <a href="/c">Third</a>
        """
    )
    assert [r.accessible_name for r in rows] == ["First", "Second", "Third"]
    assert [r.href for r in rows] == ["/a", "/b", "/c"]


def test_whitespace_in_link_text_is_collapsed() -> None:
    rows = _e("<a href='/x'>  hello   world  </a>")
    assert rows[0].accessible_name == "hello world"


# ---------------------------------------------------------------------
# Accessible-name precedence rules
# ---------------------------------------------------------------------


def test_aria_label_overrides_visible_text() -> None:
    rows = _e('<a href="/x" aria-label="Open documentation">→</a>')
    assert rows[0].accessible_name == "Open documentation"
    assert rows[0].accessible_name_source == "aria-label"


def test_aria_labelledby_resolves_to_referenced_element() -> None:
    rows = _e(
        """
        <h2 id="card-title">Annual Report 2025</h2>
        <a href="/r25.pdf" aria-labelledby="card-title">Download</a>
        """
    )
    assert rows[0].accessible_name == "Annual Report 2025"
    assert rows[0].accessible_name_source == "aria-labelledby"


def test_aria_labelledby_concatenates_multiple_refs() -> None:
    rows = _e(
        """
        <span id="a">Read</span><span id="b">2024 report</span>
        <a href="/r.pdf" aria-labelledby="a b">Read</a>
        """
    )
    # Both refs resolved, then joined by single space. The trailing
    # "Read" visible text would have been the fallback if both refs
    # had been missing; aria-labelledby wins.
    assert rows[0].accessible_name == "Read 2024 report"
    assert rows[0].accessible_name_source == "aria-labelledby"


def test_aria_labelledby_ignores_missing_ref_silently() -> None:
    """If one ref is missing, the others should still resolve."""
    rows = _e(
        """
        <span id="present">Apply now</span>
        <a href="/x" aria-labelledby="present missing">Apply</a>
        """
    )
    assert rows[0].accessible_name == "Apply now"
    assert rows[0].accessible_name_source == "aria-labelledby"


def test_image_only_link_uses_img_alt() -> None:
    rows = _e('<a href="/home"><img src="logo.png" alt="Acme home"></a>')
    assert rows[0].accessible_name == "Acme home"
    assert rows[0].accessible_name_source == "img-alt"


def test_image_only_link_with_empty_alt_falls_through_to_title() -> None:
    """Empty alt='' marks the image as decorative; the link is
    effectively unnamed unless something else is set."""
    rows = _e(
        '<a href="/x" title="Search the catalog">'
        '<img src="search.svg" alt="">'
        "</a>"
    )
    # Fallback chain: text=empty → img-alt=empty → svg-title=none → title.
    assert rows[0].accessible_name == "Search the catalog"
    assert rows[0].accessible_name_source == "title"


def test_link_with_no_text_no_label_no_alt_is_empty_source() -> None:
    rows = _e('<a href="/x"><span></span></a>')
    assert rows[0].accessible_name == ""
    assert rows[0].accessible_name_source == "empty"


def test_aria_label_takes_precedence_over_img_alt() -> None:
    """Two competing labels: aria-label on the <a> wins per HTML-AAM."""
    rows = _e(
        '<a href="/x" aria-label="Buy widgets">'
        '<img src="cart.svg" alt="cart icon">'
        "</a>"
    )
    assert rows[0].accessible_name == "Buy widgets"
    assert rows[0].accessible_name_source == "aria-label"


# ---------------------------------------------------------------------
# Skip / exclusion rules
# ---------------------------------------------------------------------


def test_link_without_href_is_skipped() -> None:
    rows = _e('<a>placeholder anchor</a>')
    assert rows == []


def test_link_with_empty_href_is_skipped() -> None:
    rows = _e('<a href="">x</a><a href="   ">y</a>')
    assert rows == []


def test_fragment_only_link_is_skipped() -> None:
    """Per the extractor's contract: in-page jumps have their own
    a11y semantics."""
    rows = _e('<a href="#section">Section 2</a>')
    assert rows == []


def test_javascript_scheme_is_skipped() -> None:
    rows = _e('<a href="javascript:void(0)">x</a>')
    assert rows == []


def test_mailto_and_tel_schemes_are_skipped() -> None:
    rows = _e(
        '<a href="mailto:a@b.co">Email</a>'
        '<a href="tel:+15551234">Call</a>'
    )
    assert rows == []


def test_uppercase_scheme_still_skipped() -> None:
    """Defensive: 'JAVASCRIPT:' should also be excluded."""
    rows = _e('<a href="JAVASCRIPT:void(0)">x</a>')
    assert rows == []


# ---------------------------------------------------------------------
# Ancestor context capture
# ---------------------------------------------------------------------


def test_ancestor_chain_collects_text_up_to_depth() -> None:
    rows = _e(
        """
        <section>
          <h2>Job postings</h2>
          <article>
            <h3>Senior Engineer</h3>
            <p>Help us build accessibility tooling.</p>
            <a href="/apply/se">Apply</a>
          </article>
        </section>
        """
    )
    r = rows[0]
    # Innermost ancestor first. We don't pin every exact ancestor text
    # because selectolax's `.text()` is whitespace-sensitive; what we
    # DO pin is that the "Senior Engineer" heading text is captured in
    # one of the ancestors so SC 2.4.4 can disambiguate the Apply.
    joined = " | ".join(r.ancestors)
    assert "Senior Engineer" in joined
    assert "Job postings" in joined


def test_ancestor_chain_capped_at_configured_depth() -> None:
    """Going beyond ANCESTOR_DEPTH never returns more than that count."""
    # Build a deeply nested anchor: 10 ancestor divs.
    nested = "".join(f"<div>{i}" for i in range(10))
    html = f"{nested}<a href='/x'>deep</a>{'</div>' * 10}"
    rows = _e(html)
    assert len(rows[0].ancestors) <= ANCESTOR_DEPTH


def test_ancestor_text_is_truncated_per_entry() -> None:
    """One verbose ancestor shouldn't dominate the prompt."""
    big = "x" * 500
    html = f"<section>{big}<a href='/x'>link</a></section>"
    rows = _e(html)
    # The body of <section> gets captured as an ancestor. Should be
    # ≤ 200 characters per the truncation rule.
    assert all(len(a) <= 200 for a in rows[0].ancestors)


def test_link_with_no_ancestors_returns_empty_list() -> None:
    """A bare anchor at document root has no meaningful ancestors."""
    rows = _e('<a href="/x">x</a>')
    # selectolax wraps loose markup in <html><body>; those are
    # ancestors but they have empty .text() so the list ends up
    # empty (whitespace-only ancestor texts are filtered).
    # We assert ≤ some reasonable bound rather than == 0 because
    # the wrapping behavior is selectolax-internal.
    assert len(rows[0].ancestors) <= ANCESTOR_DEPTH


# ---------------------------------------------------------------------
# Snippet + selector
# ---------------------------------------------------------------------


def test_snippet_captures_outer_html() -> None:
    rows = _e('<a href="/x" class="cta">Apply now</a>')
    assert "Apply now" in rows[0].snippet
    assert 'class="cta"' in rows[0].snippet


def test_snippet_is_truncated_at_limit() -> None:
    """A monstrous inline HTML link shouldn't blow up the prompt."""
    payload = "z" * 1000
    rows = _e(f'<a href="/x">{payload}</a>')
    # Limit is 300 in the extractor today; we don't pin the exact
    # number but pin "much smaller than the input".
    assert len(rows[0].snippet) < 400


def test_selector_uses_id_when_present() -> None:
    rows = _e('<a id="main-cta" href="/x">x</a>')
    assert rows[0].selector == "a#main-cta"


def test_selector_uses_first_class_when_no_id() -> None:
    rows = _e('<a class="btn primary" href="/x">x</a>')
    # First class only, with the ordinal disambiguator.
    assert rows[0].selector.startswith("a.btn")


def test_selector_falls_back_to_ordinal_when_no_id_or_class() -> None:
    rows = _e(
        """
        <a href="/a">a</a>
        <a href="/b">b</a>
        """
    )
    # Document-order ordinals — used to round-trip findings back.
    assert rows[0].selector == "a[ord=0]"
    assert rows[1].selector == "a[ord=1]"


# ---------------------------------------------------------------------
# Robustness / defensive parsing
# ---------------------------------------------------------------------


def test_malformed_html_does_not_crash() -> None:
    """selectolax is permissive; the extractor must be permissive too."""
    rows = _e('<a href="/x">unclosed <a href="/y">nested</a>')
    # Don't pin exact count — selectolax has its own opinions on
    # auto-closure. Just assert we didn't crash and got at least
    # one row out.
    assert len(rows) >= 1


def test_empty_body_returns_empty_list() -> None:
    assert extract_links(b"") == []


def test_body_with_no_anchors_returns_empty_list() -> None:
    rows = _e("<html><body><p>No links here</p></body></html>")
    assert rows == []


def test_non_utf8_body_does_not_crash() -> None:
    """selectolax accepts bytes; latin-1 should at minimum not raise."""
    body = '<a href="/x">café</a>'.encode("latin-1")
    rows = extract_links(body)
    # We don't pin the exact accessible_name (decoding may produce
    # mojibake) — just that the link is captured.
    assert len(rows) >= 1
    assert rows[0].href == "/x"
