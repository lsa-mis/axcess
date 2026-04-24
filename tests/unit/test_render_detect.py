"""Unit tests for the static-vs-JS render heuristic."""

from __future__ import annotations

from audit.crawler.render_detect import is_challenge_response, is_js_only


def _html(body: str) -> bytes:
    return f"<!doctype html><html><body>{body}</body></html>".encode()


def test_empty_body_is_not_flagged() -> None:
    assert is_js_only(b"") is False


def test_rich_static_page_is_not_flagged() -> None:
    body = "".join(f"<p>paragraph {i}</p>" for i in range(30))
    assert is_js_only(_html(body)) is False


def test_sparse_body_is_flagged() -> None:
    assert is_js_only(_html("<p>tiny</p>")) is True


def test_noscript_meta_refresh_is_flagged() -> None:
    # Enough nodes to pass the node-count gate, but the noscript redirect still trips.
    filler = "".join(f"<p>para {i}</p>" for i in range(30))
    body = f'<noscript><meta http-equiv="refresh" content="0; url=/nojs"></noscript>{filler}'
    assert is_js_only(_html(body)) is True


def test_next_data_with_empty_root_is_flagged() -> None:
    filler = "".join(f"<div>{i}</div>" for i in range(30))
    body = f'<div id="root"></div>{filler}<script id="__NEXT_DATA__">{{}}</script>'
    assert is_js_only(_html(body)) is True


def test_next_data_with_hydrated_root_is_not_flagged() -> None:
    hydrated = "".join(f"<p>{i}</p>" for i in range(30))
    body = f'<div id="root">{hydrated}</div><script>__NEXT_DATA__ = {{}}</script>'
    assert is_js_only(_html(body)) is False


def test_challenge_response_cloudflare_interstitial() -> None:
    body = b"<html><head><title>Just a moment...</title></head></html>"
    assert is_challenge_response(403, body) is True
    assert is_challenge_response(503, body) is True
    assert is_challenge_response(429, body) is True


def test_challenge_response_cdn_cgi_marker() -> None:
    body = (
        b"<html><body>"
        b'<script src="/cdn-cgi/challenge-platform/v3/b/orchestrate"></script>'
        b"</body></html>"
    )
    assert is_challenge_response(403, body) is True


def test_challenge_response_aws_waf() -> None:
    body = b"<html><body>captcha-delivery.com</body></html>"
    assert is_challenge_response(403, body) is True


def test_real_403_is_not_a_challenge() -> None:
    """A plain 403 Forbidden page without challenge markers stays a real 403."""
    body = b"<html><body><h1>403 Forbidden</h1></body></html>"
    assert is_challenge_response(403, body) is False


def test_200_with_challenge_marker_is_not_a_challenge() -> None:
    # Markers in a 200 response body are not a challenge — it's just HTML
    # that happens to contain the string (e.g. docs about Cloudflare).
    body = b"<html>Just a moment... is a Cloudflare page</html>"
    assert is_challenge_response(200, body) is False


def test_challenge_response_404_ignored() -> None:
    body = b"<html><title>Just a moment...</title></html>"
    assert is_challenge_response(404, body) is False


def test_challenge_response_empty_body() -> None:
    assert is_challenge_response(403, b"") is False
    assert is_challenge_response(503, b"") is False
