"""Read mitmproxy flow dumps with the standard library only.

The KAFE subjects (ESEC/FSE 2021, §5.2: "captured a complete version of each
subject web page using an interactive HTTP proxy") are mitmproxy flow files: a
concatenation of tnetstring-encoded dicts. Verified on all three authorized
samples, each of which begins `<len>:7:version;1:7#4:mode;11:transparent;`.

mitmproxy's tnetstring differs from the published spec in one respect that
matters here: `;` marks a unicode string and `,` marks raw bytes. Header names,
values and bodies arrive as bytes; keys arrive as unicode.

This module only *reads*. It installs nothing, opens no socket, and never
contacts the origin the capture came from.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field

# Default ports that are omitted when rebuilding an absolute URL.
_DEFAULT_PORTS = {"http": 80, "https": 443, "ws": 80, "wss": 443}


def _text(value: object) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def parse(data: bytes) -> tuple[object, bytes]:
    """Parse one tnetstring from ``data``; return it and the unconsumed tail."""
    head, sep, tail = data.partition(b":")
    if not sep:
        raise ValueError("tnetstring: missing length separator")
    try:
        length = int(head)
    except ValueError as exc:
        raise ValueError(f"tnetstring: bad length {head!r}") from exc
    if len(tail) < length + 1:
        raise ValueError("tnetstring: truncated payload")

    payload, kind, rest = tail[:length], tail[length : length + 1], tail[length + 1 :]

    if kind == b"#":
        return int(payload), rest
    if kind == b";":
        return payload.decode("utf-8"), rest
    if kind == b",":
        return payload, rest
    if kind == b"~":
        return None, rest
    if kind == b"!":
        return payload == b"true", rest
    if kind == b"^":
        return float(payload), rest
    if kind == b"]":
        items: list[object] = []
        while payload:
            item, payload = parse(payload)
            items.append(item)
        return items, rest
    if kind == b"}":
        mapping: dict[str, object] = {}
        while payload:
            key, payload = parse(payload)
            value, payload = parse(payload)
            mapping[_text(key)] = value
        return mapping, rest

    raise ValueError(f"tnetstring: unknown type {kind!r}")


def iter_values(stream: bytes) -> Iterator[object]:
    """Yield every top-level tnetstring in a concatenated stream."""
    rest = stream
    while rest:
        value, rest = parse(rest)
        yield value


def dump(value: object) -> bytes:
    """Encode a value. Used by the tests to build fixtures; not needed to read."""
    if isinstance(value, bool):
        body, kind = (b"true" if value else b"false"), b"!"
    elif value is None:
        body, kind = b"", b"~"
    elif isinstance(value, int):
        body, kind = str(value).encode(), b"#"
    elif isinstance(value, float):
        body, kind = repr(value).encode(), b"^"
    elif isinstance(value, bytes):
        body, kind = value, b","
    elif isinstance(value, str):
        body, kind = value.encode("utf-8"), b";"
    elif isinstance(value, list):
        body, kind = b"".join(dump(v) for v in value), b"]"
    elif isinstance(value, dict):
        body = b"".join(dump(k) + dump(v) for k, v in value.items())
        kind = b"}"
    else:
        raise TypeError(f"cannot encode {type(value)!r}")
    return b"%d:%s%s" % (len(body), body, kind)


@dataclass(frozen=True)
class Exchange:
    """One captured request/response pair, reduced to what a replay needs."""

    url: str
    method: str
    status: int
    headers: dict[str, str]
    body: bytes


def to_exchange(flow: dict) -> Exchange | None:
    """Reduce one flow dict to an ``Exchange``, or ``None`` if it has no response."""
    request = flow.get("request")
    response = flow.get("response")
    if not isinstance(request, dict) or not isinstance(response, dict):
        return None

    scheme = _text(request.get("scheme", b"https"))
    host = _text(request.get("host", b""))
    path = _text(request.get("path", b"/"))
    port = request.get("port")

    netloc = host
    if isinstance(port, int) and port != _DEFAULT_PORTS.get(scheme):
        netloc = f"{host}:{port}"

    headers: dict[str, str] = {}
    for pair in response.get("headers") or []:
        if isinstance(pair, (list, tuple)) and len(pair) == 2:
            headers[_text(pair[0]).lower()] = _text(pair[1])

    content = response.get("content")
    return Exchange(
        url=f"{scheme}://{netloc}{path}",
        method=_text(request.get("method", b"GET")).upper(),
        status=int(response.get("status_code") or 0),
        headers=headers,
        body=content if isinstance(content, bytes) else b"",
    )


@dataclass
class ExchangeIndex:
    """Every exchange in a capture, indexed by absolute URL in capture order."""

    by_url: dict[str, list[Exchange]] = field(default_factory=dict)
    flow_count: int = 0
    responseless: int = 0
    unreadable: int = 0

    def add(self, exchange: Exchange) -> None:
        self.by_url.setdefault(exchange.url, []).append(exchange)

    @property
    def exchange_count(self) -> int:
        return sum(len(v) for v in self.by_url.values())


def load_exchanges(stream: bytes) -> ExchangeIndex:
    """Build an ``ExchangeIndex`` from a flow dump.

    A flow that cannot be parsed stops the scan — the stream is sequential, so
    a bad length makes everything after it meaningless — but whatever was read
    before that point is kept and counted, rather than discarded.
    """
    index = ExchangeIndex()
    rest = stream
    while rest:
        try:
            flow, rest = parse(rest)
        except ValueError:
            index.unreadable += 1
            break
        index.flow_count += 1
        if not isinstance(flow, dict):
            continue
        exchange = to_exchange(flow)
        if exchange is None:
            index.responseless += 1
            continue
        index.add(exchange)
    return index
