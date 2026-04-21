"""Unit tests for the static-vs-JS render heuristic."""

from __future__ import annotations

from audit.crawler.render_detect import is_js_only


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
