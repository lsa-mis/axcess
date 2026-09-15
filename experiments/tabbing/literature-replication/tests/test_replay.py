"""Tests for the offline replay router.

Slice 3. The router answers browser requests from a capture and denies
everything else. Default-deny is the safety property: a capture that quietly
reached the live origin would make any later observation meaningless, and would
also be an unauthorized egress.

Resolution is pure and tested without a browser here; the Playwright binding is
exercised separately against the real captures.
"""

from __future__ import annotations

import pytest

from tools import flowfile, replay


def _exchange(url, body=b"ok", status=200, ctype="text/html"):
    return flowfile.Exchange(
        url=url,
        method="GET",
        status=status,
        headers={"content-type": ctype},
        body=body,
    )


def _with_method(url, method, body=b"ok"):
    return flowfile.Exchange(
        url=url,
        method=method,
        status=200,
        headers={"content-type": "text/html"},
        body=body,
    )


def _encoded(body, encoding, ctype="application/octet-stream"):
    return flowfile.Exchange(
        url="https://e.com/",
        method="GET",
        status=200,
        headers={"content-type": ctype, "content-encoding": encoding},
        body=body,
    )


def _router(*exchanges):
    index = flowfile.ExchangeIndex()
    for exchange in exchanges:
        index.add(exchange)
    return replay.ReplayRouter(index)


def test_resolves_an_exact_url():
    router = _router(_exchange("https://e.com/a", b"hello"))
    assert router.resolve("https://e.com/a").body == b"hello"


def test_denies_an_unknown_url():
    router = _router(_exchange("https://e.com/a"))
    assert router.resolve("https://e.com/b") is None


def test_denies_a_different_origin_even_for_the_same_path():
    router = _router(_exchange("https://e.com/a"))
    assert router.resolve("https://evil.com/a") is None


def test_strips_the_fragment_before_matching():
    router = _router(_exchange("https://e.com/a"))
    assert router.resolve("https://e.com/a#section") is not None


def test_query_string_is_significant():
    router = _router(_exchange("https://e.com/p?id=1", b"one"))
    assert router.resolve("https://e.com/p?id=1").body == b"one"
    assert router.resolve("https://e.com/p?id=2") is None


def test_repeated_url_serves_responses_in_capture_order_then_repeats_the_last():
    router = _router(
        _exchange("https://e.com/a", b"first"),
        _exchange("https://e.com/a", b"second"),
    )
    assert router.resolve("https://e.com/a").body == b"first"
    assert router.resolve("https://e.com/a").body == b"second"
    # A third request must still be answered rather than denied: browsers
    # re-request, and denying here would look like a broken capture.
    assert router.resolve("https://e.com/a").body == b"second"


def test_counts_served_and_denied():
    router = _router(_exchange("https://e.com/a"))
    router.resolve("https://e.com/a")
    router.resolve("https://e.com/missing")
    router.resolve("https://e.com/missing")
    assert router.served == 1
    assert router.denied == 2
    assert router.denied_urls["https://e.com/missing"] == 2


# --------------------------------------------------------------------------
# G4: a denied request is not automatically a broken capture
# --------------------------------------------------------------------------


def test_classifies_denied_requests_as_essential_or_benign():
    router = _router(_exchange("https://e.com/"))
    router.resolve("https://e.com/app.js")
    router.resolve("https://www.google-analytics.com/collect")
    router.resolve("https://e.com/hero.png")

    report = router.denial_report()
    assert report["essential"] == ["https://e.com/app.js"]
    assert "https://www.google-analytics.com/collect" in report["benign_tracking"]
    assert "https://e.com/hero.png" in report["benign_media"]


def test_a_capture_with_only_benign_denials_is_not_called_degraded():
    router = _router(_exchange("https://e.com/"))
    router.resolve("https://www.google-analytics.com/collect")
    assert router.denial_report()["essential"] == []
    assert router.is_functionally_degraded() is False


def test_a_capture_missing_a_script_is_called_degraded():
    router = _router(_exchange("https://e.com/"))
    router.resolve("https://e.com/app.js")
    assert router.is_functionally_degraded() is True


# --------------------------------------------------------------------------
# Content-encoding: mitmproxy stores raw bodies
# --------------------------------------------------------------------------
#
# Verified on all three captures: citiprogram br=2/gzip=6, coronavirus
# gzip=14/br=2, craigslist gzip=11/br=1. Serving those bytes with the encoding
# header stripped makes the browser render compressed noise as text, which is
# exactly what a first run of this harness did.


def test_gzip_body_is_decoded_and_the_header_removed():
    import gzip as gzip_mod

    raw = gzip_mod.compress(b"<html><body>hi</body></html>")
    body, headers = replay.prepare_response(
        _encoded(raw, "gzip", ctype="text/html")
    )
    assert body == b"<html><body>hi</body></html>"
    assert "content-encoding" not in headers


def test_deflate_body_is_decoded():
    import zlib

    raw = zlib.compress(b"data")
    body, headers = replay.prepare_response(
        _encoded(raw, "deflate")
    )
    assert body == b"data"
    assert "content-encoding" not in headers


def test_brotli_body_is_passed_through_with_its_header_for_the_browser_to_decode():
    raw = b"\x1b\x00\x00brotli-ish"
    body, headers = replay.prepare_response(
        _encoded(raw, "br")
    )
    assert body == raw
    assert headers["content-encoding"] == "br"


def test_unencoded_body_is_untouched():
    body, headers = replay.prepare_response(_exchange("https://e.com/", b"plain"))
    assert body == b"plain"
    assert "content-encoding" not in headers


def test_corrupt_gzip_is_passed_through_rather_than_raising():
    body, headers = replay.prepare_response(
        _encoded(b"not-gzip", "gzip")
    )
    assert body == b"not-gzip"
    assert headers["content-encoding"] == "gzip"


def test_stale_content_length_is_always_dropped():
    _, headers = replay.prepare_response(
        flowfile.Exchange(url="https://e.com/", method="GET", status=200,
                          headers={"content-length": "999"}, body=b"abc")
    )
    assert "content-length" not in headers


# --------------------------------------------------------------------------
# HTTP method must participate in matching
# --------------------------------------------------------------------------
#
# The manager found `resolve()` accepting a `method` argument and never reading
# it, so a POST was answered with a GET's captured response. Latent on the three
# authorized captures (all GET, no duplicate URLs), but a correctness bug the
# moment a subject posts a form -- which is precisely what keyboard interaction
# reaches. A wrong 200 here is worse than a denial: it fabricates a page state
# the capture never observed.


def test_denies_a_method_the_capture_does_not_have():
    router = _router(_with_method("https://e.com/f", "GET"))
    assert router.resolve("https://e.com/f", "POST") is None


def test_serves_a_post_when_the_capture_has_one():
    router = _router(_with_method("https://e.com/f", "POST", b"posted"))
    assert router.resolve("https://e.com/f", "POST").body == b"posted"


def test_method_matching_is_case_insensitive():
    router = _router(_with_method("https://e.com/f", "GET"))
    assert router.resolve("https://e.com/f", "get") is not None


def test_same_url_with_two_methods_keeps_them_apart():
    router = _router(
        _with_method("https://e.com/f", "GET", b"form"),
        _with_method("https://e.com/f", "POST", b"result"),
    )
    assert router.resolve("https://e.com/f", "GET").body == b"form"
    assert router.resolve("https://e.com/f", "POST").body == b"result"


def test_a_method_mismatch_counts_as_a_denial():
    router = _router(_with_method("https://e.com/f", "GET"))
    router.resolve("https://e.com/f", "POST")
    assert router.denied == 1
    assert router.served == 0


def test_repeat_ordering_is_per_method_not_per_url():
    router = _router(
        _with_method("https://e.com/f", "GET", b"g1"),
        _with_method("https://e.com/f", "POST", b"p1"),
        _with_method("https://e.com/f", "GET", b"g2"),
    )
    assert router.resolve("https://e.com/f", "GET").body == b"g1"
    assert router.resolve("https://e.com/f", "POST").body == b"p1"
    assert router.resolve("https://e.com/f", "GET").body == b"g2"


# --------------------------------------------------------------------------
# Neutral ID census (G1): tagging must be label-independent
# --------------------------------------------------------------------------


def test_census_script_is_label_independent():
    """The census must not mention the experiment's own label vocabulary."""
    source = replay.NEUTRAL_CENSUS_JS
    for forbidden in ("data-probe", "truth", "violation", "decoy"):
        assert forbidden not in source


def test_census_attribute_name_is_namespaced_and_stable():
    assert replay.CENSUS_ATTR.startswith("data-litrep-")
    assert replay.CENSUS_ATTR == "data-litrep-eid"


@pytest.mark.parametrize("scope", ["document", "shadow"])
def test_census_script_walks_the_supported_scopes(scope):
    source = replay.NEUTRAL_CENSUS_JS
    assert ("shadowRoot" in source) if scope == "shadow" else ("document" in source)
