"""The text side of saving a page's CSS: URLs, imports, media, bounds, cache.

The browser half (reading ``document.styleSheets``) is covered in
tests/integration/test_saved_copy_styles_crawl.py. Everything here is the
processing that decides whether the saved CSS means what it meant on the site.
"""

from __future__ import annotations

import asyncio
from typing import Any

from audit.crawler import style_snapshot as ss


def test_relative_urls_resolve_against_the_sheet_not_the_page() -> None:
    css = (
        "a{background:url(img/a.png)}"
        "b{background:url('../b.png')}"
        'c{background:url( "/c.png" )}'
        "@font-face{src:url(fonts/x.woff2) format('woff2')}"
    )
    out = ss.absolutize_urls(css, "https://cdn.test/css/site.css")
    assert 'url("https://cdn.test/css/img/a.png")' in out
    assert 'url("https://cdn.test/b.png")' in out
    assert 'url("https://cdn.test/c.png")' in out
    assert 'url("https://cdn.test/css/fonts/x.woff2")' in out


def test_absolute_data_and_fragment_urls_are_left_alone() -> None:
    css = (
        "a{background:url(https://other.test/a.png)}"
        "b{background:url(data:image/png;base64,AAAA)}"
        "c{clip-path:url(#clip)}"
        "d{background:url(//proto.test/d.png)}"
    )
    out = ss.absolutize_urls(css, "https://site.test/css/s.css")
    assert "url(https://other.test/a.png)" in out
    assert "url(data:image/png;base64,AAAA)" in out
    # An SVG reference into the document must stay a reference into it.
    assert "url(#clip)" in out
    assert 'url("https://proto.test/d.png")' in out


def test_no_usable_base_leaves_the_text_unchanged() -> None:
    css = "a{background:url(a.png)}"
    assert ss.absolutize_urls(css, None) == css
    assert ss.absolutize_urls(css, "about:blank") == css


def test_quotes_in_a_url_are_escaped_in_the_rewrite() -> None:
    out = ss.absolutize_urls("a{background:url('we\"ird.png')}", "https://s.test/")
    assert out == 'a{background:url("https://s.test/we\\"ird.png")}'


def test_charset_is_dropped() -> None:
    assert ss.strip_charset('@charset "utf-8";a{color:red}') == "a{color:red}"


def test_leading_imports_are_split_with_their_conditions() -> None:
    css = (
        '@charset "utf-8";\n'
        "/* comment */\n"
        '@import url("base.css");\n'
        "@import 'print.css' print;\n"
        "@import url(layered.css) layer(theme) supports(display: grid)"
        " screen and (min-width: 1px);\n"
        "a{color:red}\n"
        "@import 'late.css';\n"
    )
    imports, rest = ss.split_imports(css)
    assert [url for url, _ in imports] == ["base.css", "print.css", "layered.css"]
    assert imports[0][1] == []
    assert imports[1][1] == [{"kind": "media", "text": "print"}]
    assert imports[2][1] == [
        {"kind": "media", "text": "screen and (min-width: 1px)"},
        {"kind": "supports", "text": "display: grid"},
        {"kind": "layer", "text": "theme"},
    ]
    # A late @import is invalid in a browser and is not kept either.
    assert "@import" not in rest
    assert "a{color:red}" in rest


def test_conditions_wrap_outermost_first() -> None:
    wrapped = ss.wrap_conditions(
        "a{color:red}",
        [
            {"kind": "media", "text": "screen"},
            {"kind": "supports", "text": "display: grid"},
            {"kind": "layer", "text": ""},
        ],
    )
    assert wrapped.index("@media screen") < wrapped.index("@supports (display: grid)")
    assert wrapped.index("@supports") < wrapped.index("@layer {")
    assert wrapped.count("{") == wrapped.count("}")


def test_media_all_is_not_wrapped() -> None:
    assert ss.wrap_conditions("a{}", [{"kind": "media", "text": "all"}]) == "a{}"


def test_concatenate_wraps_each_sheet_with_media_in_order() -> None:
    out = ss.concatenate([("a{color:red}", ""), ("b{color:blue}", "print"), ("c{}", "all")])
    assert out.index("a{color:red}") < out.index("@media print")
    assert "@media print {\nb{color:blue}\n}" in out
    assert "@media all" not in out


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


async def _no_fetch(url: str) -> str | None:
    raise AssertionError(f"unexpected fetch of {url}")


def test_snapshot_keeps_order_media_and_absolutizes_inline_rules() -> None:
    raw = {
        "parts": [
            {
                "kind": "text",
                "text": "a{background:url(x.png)}",
                "base": "https://s.test/css/one.css",
                "href": "https://s.test/css/one.css",
                "media": "",
                "wrappers": [],
            },
            {
                "kind": "text",
                "text": "b{color:red}",
                "base": "https://s.test/page",
                "href": None,
                "media": "print",
                "wrappers": [{"kind": "media", "text": "screen"}],
            },
        ],
        "incomplete": False,
        "fingerprint": {"scheme": "light", "samples": []},
    }
    snapshot = _run(ss.build_snapshot(raw, _no_fetch))
    assert snapshot.complete
    assert [s.source_url for s in snapshot.sheets] == ["https://s.test/css/one.css", None]
    assert 'url("https://s.test/css/x.png")' in snapshot.sheets[0].css
    assert snapshot.sheets[1].media == "print"
    assert snapshot.sheets[1].css.startswith("@media screen {")
    assert snapshot.fingerprint == {"scheme": "light", "samples": []}


def test_unreadable_sheets_are_fetched_and_failures_mark_it_incomplete() -> None:
    fetched: list[str] = []

    async def fetch(url: str) -> str | None:
        fetched.append(url)
        return "c{color:green}" if url.endswith("ok.css") else None

    raw = {
        "parts": [
            {"kind": "fetch", "href": "https://cdn.test/ok.css", "media": "", "wrappers": []},
            {"kind": "fetch", "href": "https://cdn.test/gone.css", "media": "", "wrappers": []},
        ],
        "incomplete": False,
    }
    snapshot = _run(ss.build_snapshot(raw, fetch))
    assert fetched == ["https://cdn.test/ok.css", "https://cdn.test/gone.css"]
    assert [s.css for s in snapshot.sheets] == ["c{color:green}"]
    assert not snapshot.complete


def test_bounds_skip_what_is_over_and_record_it() -> None:
    big = "a{content:'" + "x" * (ss.MAX_SHEET_BYTES + 10) + "'}"
    part = {"kind": "text", "base": None, "href": None, "media": "", "wrappers": []}
    over_sheet = _run(
        ss.build_snapshot({"parts": [{**part, "text": big}, {**part, "text": "b{}"}]}, _no_fetch)
    )
    assert [s.css for s in over_sheet.sheets] == ["b{}"]
    assert not over_sheet.complete

    chunk = "a{content:'" + "x" * (ss.MAX_SHEET_BYTES - 100) + "'}"
    over_page = _run(ss.build_snapshot({"parts": [{**part, "text": chunk}] * 5}, _no_fetch))
    assert len(over_page.sheets) == ss.MAX_PAGE_BYTES // ss.MAX_SHEET_BYTES
    assert not over_page.complete

    many = _run(
        ss.build_snapshot({"parts": [{**part, "text": "a{}"}] * (ss.MAX_SHEETS + 5)}, _no_fetch)
    )
    assert len(many.sheets) == ss.MAX_SHEETS
    assert not many.complete

    # The page itself reported a bound it hit.
    flagged = _run(ss.build_snapshot({"parts": [], "incomplete": True}, _no_fetch))
    assert not flagged.complete


def test_a_malformed_evaluate_result_is_no_snapshot() -> None:
    assert _run(ss.build_snapshot(None, _no_fetch)) is None
    assert _run(ss.build_snapshot("nope", _no_fetch)) is None


class _Response:
    def __init__(self, status: int, body: str) -> None:
        self.status = status
        self.ok = 200 <= status < 300
        self._body = body.encode()
        self.headers: dict[str, str] = {}

    async def body(self) -> bytes:
        return self._body

    async def dispose(self) -> None:
        return None


class _Request:
    def __init__(self, sheets: dict[str, tuple[int, str]]) -> None:
        self.sheets = sheets
        self.calls: list[str] = []

    async def get(self, url: str, **_: Any) -> _Response:
        self.calls.append(url)
        await asyncio.sleep(0)
        status, body = self.sheets.get(url, (404, ""))
        return _Response(status, body)


def test_the_cache_fetches_each_sheet_once_and_inlines_its_imports() -> None:
    request = _Request(
        {
            "https://cdn.test/css/site.css": (
                200,
                "@import 'parts/base.css' screen;\na{background:url(a.png)}",
            ),
            "https://cdn.test/css/parts/base.css": (200, "b{background:url(b.png)}"),
        }
    )
    cache = ss.SheetCache()

    async def run() -> list[str | None]:
        url = "https://cdn.test/css/site.css"
        together = await asyncio.gather(*(cache.get(request, url) for _ in range(3)))  # type: ignore[arg-type]
        later = await cache.get(request, url)  # type: ignore[arg-type]
        return [*together, later]

    results = asyncio.run(run())
    assert len(set(results)) == 1
    text = results[0]
    assert text is not None
    assert request.calls == ["https://cdn.test/css/site.css", "https://cdn.test/css/parts/base.css"]
    # The import, in place, wrapped in its media, with its own URLs resolved
    # against its own address.
    assert text.index("@media screen") < text.index("a{background")
    assert 'url("https://cdn.test/css/parts/b.png")' in text
    assert 'url("https://cdn.test/css/a.png")' in text


def test_the_cache_remembers_http_failures_and_refuses_other_schemes() -> None:
    request = _Request({})
    cache = ss.SheetCache()

    async def run() -> tuple[str | None, str | None, str | None]:
        first = await cache.get(request, "https://cdn.test/missing.css")  # type: ignore[arg-type]
        second = await cache.get(request, "https://cdn.test/missing.css")  # type: ignore[arg-type]
        local = await cache.get(request, "file:///etc/passwd")  # type: ignore[arg-type]
        return first, second, local

    assert asyncio.run(run()) == (None, None, None)
    assert request.calls == ["https://cdn.test/missing.css"]


def test_an_oversized_fetched_sheet_is_refused() -> None:
    request = _Request({"https://cdn.test/big.css": (200, "x" * (ss.MAX_SHEET_BYTES + 1))})
    cache = ss.SheetCache()
    assert asyncio.run(cache.get(request, "https://cdn.test/big.css")) is None  # type: ignore[arg-type]
