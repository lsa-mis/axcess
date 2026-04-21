"""Unit tests for html_images.extract_image_refs."""

from __future__ import annotations

from audit.extractor.html_images import extract_image_refs


def _doc(body: str) -> bytes:
    return f"<!doctype html><html><body>{body}</body></html>".encode()


def test_simple_img_with_alt() -> None:
    refs = extract_image_refs(
        _doc('<img src="/logo.png" alt="Acme logo">'),
        "https://example.com/",
    )
    assert len(refs) == 1
    ref = refs[0]
    assert ref.url == "https://example.com/logo.png"
    assert ref.alt == "Acme logo"
    assert ref.via_srcset is False
    assert ref.via_picture is False


def test_empty_alt_preserved() -> None:
    refs = extract_image_refs(_doc('<img src="deco.png" alt="">'), "https://example.com/")
    assert refs[0].alt == ""


def test_missing_alt_is_none() -> None:
    refs = extract_image_refs(_doc('<img src="x.png">'), "https://example.com/")
    assert refs[0].alt is None


def test_srcset_expands_to_multiple_refs() -> None:
    html = _doc('<img src="s.png" srcset="s1.png 1x, s2.png 2x, s3.png 3x">')
    refs = extract_image_refs(html, "https://example.com/")
    urls = [r.url for r in refs]
    assert urls == [
        "https://example.com/s.png",
        "https://example.com/s1.png",
        "https://example.com/s2.png",
        "https://example.com/s3.png",
    ]
    assert refs[0].via_srcset is False
    assert refs[1].via_srcset is True


def test_picture_collects_sources_and_fallback_img() -> None:
    html = _doc(
        "<picture>"
        '<source srcset="large.webp" media="(min-width: 800px)">'
        '<source srcset="small.webp">'
        '<img src="fallback.jpg" alt="A cat">'
        "</picture>"
    )
    refs = extract_image_refs(html, "https://example.com/")
    urls = [r.url for r in refs]
    assert "https://example.com/large.webp" in urls
    assert "https://example.com/small.webp" in urls
    assert "https://example.com/fallback.jpg" in urls
    # The <img> inside <picture> is marked via_picture.
    img_ref = next(r for r in refs if r.url.endswith("fallback.jpg"))
    assert img_ref.via_picture is True
    assert img_ref.alt == "A cat"


def test_aria_labels_and_role_captured() -> None:
    html = _doc(
        '<img src="a.png" alt="Alt" role="presentation" '
        'aria-label="ARIA label" aria-labelledby="hdr">'
    )
    ref = extract_image_refs(html, "https://example.com/")[0]
    assert ref.role == "presentation"
    assert ref.aria_label == "ARIA label"
    assert ref.aria_labelledby == "hdr"


def test_figcaption_collected() -> None:
    html = _doc(
        "<figure>"
        '<img src="f.png" alt="Chart">'
        "<figcaption>Q4 revenue by region</figcaption>"
        "</figure>"
    )
    ref = extract_image_refs(html, "https://example.com/")[0]
    assert ref.figcaption == "Q4 revenue by region"


def test_context_snippet_captured_and_collapsed() -> None:
    html = _doc("<p>Some context here.  <img src='x.png' alt='x'>  Some text after.</p>")
    ref = extract_image_refs(html, "https://example.com/")[0]
    assert ref.context_snippet is not None
    assert "Some context here." in ref.context_snippet
    assert "Some text after." in ref.context_snippet


def test_context_snippet_truncated() -> None:
    long_text = "word " * 100
    html = _doc(f"<p>{long_text}<img src='x.png' alt='x'></p>")
    ref = extract_image_refs(html, "https://example.com/")[0]
    assert ref.context_snippet is not None
    assert ref.context_snippet.endswith("…")
    assert len(ref.context_snippet) <= 201  # 200 chars + "…"


def test_data_and_javascript_urls_skipped() -> None:
    html = _doc(
        '<img src="data:image/png;base64,AAA" alt="data">'
        '<img src="javascript:void(0)" alt="js">'
        '<img src="/ok.png" alt="ok">'
    )
    refs = extract_image_refs(html, "https://example.com/")
    urls = [r.url for r in refs]
    assert urls == ["https://example.com/ok.png"]


def test_relative_urls_resolved_against_base() -> None:
    html = _doc('<img src="../img/a.png" alt="x">')
    ref = extract_image_refs(html, "https://example.com/blog/post/")[0]
    assert ref.url == "https://example.com/blog/img/a.png"


def test_position_increments_in_document_order() -> None:
    html = _doc('<img src="/a.png"><img src="/b.png"><img src="/c.png">')
    refs = extract_image_refs(html, "https://example.com/")
    positions = [r.position for r in refs]
    assert positions == [0, 1, 2]
