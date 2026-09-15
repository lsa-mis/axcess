"""Tests for the tnetstring reader and mitmproxy flow extraction.

Slice 2. The KAFE subjects turned out to be mitmproxy flow dumps (verified:
every sample begins `<len>:7:version;1:7#4:mode;11:transparent;`), so reading
them is the precondition for any offline replay. mitmproxy's tnetstring variant
differs from the published spec in one way that matters: `;` is a unicode
string and `,` is raw bytes.

No network, no browser, no files: every case here is built in memory.
"""

from __future__ import annotations

import pytest

from tools import flowfile


# --------------------------------------------------------------------------
# tnetstring primitives
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        (b"1:7#", 7),
        (b"3:123#", 123),
        (b"7:version;", "version"),
        (b"0:;", ""),
        (b"5:hello,", b"hello"),
        (b"0:,", b""),
        (b"0:~", None),
        (b"4:true!", True),
        (b"5:false!", False),
        (b"0:}", {}),
        (b"0:]", []),
    ],
)
def test_parse_primitives(payload, expected):
    value, rest = flowfile.parse(payload)
    assert value == expected
    assert rest == b""


def test_parse_list_of_integers():
    value, _ = flowfile.parse(b"12:1:1#1:2#1:3#]")
    assert value == [1, 2, 3]


def test_parse_dict_with_unicode_keys():
    # {"mode": "transparent"}
    value, _ = flowfile.parse(b"22:4:mode;11:transparent;}")
    assert value == {"mode": "transparent"}


def test_parse_nested_dict_matching_the_real_header_shape():
    encoded = flowfile.dump({"headers": [[b"Host", b"example.com"]]})
    # Guard the fixture itself: this is the byte layout mitmproxy writes.
    assert encoded == b"40:7:headers;26:22:4:Host,11:example.com,]]}"
    value, rest = flowfile.parse(encoded)
    assert value == {"headers": [[b"Host", b"example.com"]]}
    assert rest == b""


def test_parse_rejects_an_unknown_type_character():
    with pytest.raises(ValueError):
        flowfile.parse(b"1:7&")


def test_parse_rejects_a_truncated_payload():
    with pytest.raises(ValueError):
        flowfile.parse(b"99:short;")


def test_iter_values_yields_each_top_level_flow():
    stream = b"1:1#" b"1:2#" b"1:3#"
    assert list(flowfile.iter_values(stream)) == [1, 2, 3]


# --------------------------------------------------------------------------
# Flow -> exchange extraction
# --------------------------------------------------------------------------


def _flow(scheme=b"https", host=b"example.com", port=443, path=b"/index.html",
          status=200, content=b"<html></html>", headers=None):
    return {
        "version": 7,
        "request": {
            "scheme": scheme,
            "host": host,
            "port": port,
            "path": path,
            "method": b"GET",
            "headers": [],
            "content": b"",
        },
        "response": {
            "status_code": status,
            "headers": headers if headers is not None else [[b"Content-Type", b"text/html"]],
            "content": content,
        },
    }


def test_exchange_builds_an_absolute_url():
    exchange = flowfile.to_exchange(_flow())
    assert exchange.url == "https://example.com/index.html"


def test_exchange_omits_the_default_port_but_keeps_a_custom_one():
    assert flowfile.to_exchange(_flow(port=443)).url.startswith("https://example.com/")
    assert ":8443" in flowfile.to_exchange(_flow(port=8443)).url


def test_exchange_carries_status_headers_and_body():
    exchange = flowfile.to_exchange(_flow(status=404, content=b"missing"))
    assert exchange.status == 404
    assert exchange.body == b"missing"
    assert exchange.headers["content-type"] == "text/html"


def test_exchange_is_none_when_the_flow_never_got_a_response():
    flow = _flow()
    flow["response"] = None
    assert flowfile.to_exchange(flow) is None


def test_load_exchanges_indexes_by_url_and_counts_duplicates():
    stream = b"".join(
        flowfile.dump(f)
        for f in (
            _flow(path=b"/a", content=b"first"),
            _flow(path=b"/b"),
            _flow(path=b"/a", content=b"second"),
        )
    )
    index = flowfile.load_exchanges(stream)
    assert set(index.by_url) == {
        "https://example.com/a",
        "https://example.com/b",
    }
    # A repeated URL keeps every response, in capture order.
    assert [e.body for e in index.by_url["https://example.com/a"]] == [
        b"first",
        b"second",
    ]
    assert index.flow_count == 3
