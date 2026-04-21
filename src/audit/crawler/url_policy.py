"""URL normalization and scope rules.

Normalization is aggressive and deterministic so that two cosmetic variants of the
same URL dedupe against the same row. Scope is based on the registrable domain
(eTLD+1) of the seed URL; subdomains are opt-in via ``allow_subdomains``.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import tldextract

_DEFAULT_PORTS = {"http": "80", "https": "443"}

_extract = tldextract.TLDExtract(suffix_list_urls=())
"""Offline-only PSL extractor — uses the snapshot bundled with tldextract."""


def normalize(url: str) -> str:
    """Return a canonical form of ``url`` suitable for equality/dedupe.

    Rules:
      * lowercase scheme and host
      * strip default ports (``:80`` for http, ``:443`` for https)
      * sort query parameters alphabetically, preserving blank values
      * drop URL fragment
      * empty path becomes ``/``
    """
    parts = urlsplit(url.strip())
    scheme = parts.scheme.lower()
    host = (parts.hostname or "").lower()
    port = parts.port
    if port is not None and _DEFAULT_PORTS.get(scheme) == str(port):
        port = None
    netloc = host if port is None else f"{host}:{port}"
    if parts.username or parts.password:
        userinfo = parts.username or ""
        if parts.password:
            userinfo = f"{userinfo}:{parts.password}"
        netloc = f"{userinfo}@{netloc}"

    path = parts.path or "/"

    query_pairs = parse_qsl(parts.query, keep_blank_values=True)
    query = urlencode(sorted(query_pairs))

    return urlunsplit((scheme, netloc, path, query, ""))


@dataclass(frozen=True)
class HostScope:
    """Crawl scope anchored on a seed URL's registrable domain."""

    registrable_domain: str
    seed_host: str


def _registrable_domain(host: str) -> str:
    parts = _extract(host)
    if not parts.domain or not parts.suffix:
        return host
    return f"{parts.domain}.{parts.suffix}"


def build_scope(seed_url: str) -> HostScope:
    """Derive a ``HostScope`` from a seed URL."""
    host = (urlsplit(seed_url).hostname or "").lower()
    return HostScope(registrable_domain=_registrable_domain(host), seed_host=host)


def _strip_www(host: str) -> str:
    return host[4:] if host.startswith("www.") else host


def is_in_scope(url: str, scope: HostScope, *, allow_subdomains: bool = False) -> bool:
    """Return True if ``url`` should be crawled under ``scope``.

    Only ``http`` and ``https`` URLs are considered in scope.
    With ``allow_subdomains=True``, any host under the registrable domain matches.
    Without it, only the seed host matches, with ``www.`` normalized out for the
    convenience of matching ``example.com`` and ``www.example.com`` as the same site.
    """
    try:
        parts = urlsplit(url)
    except ValueError:
        return False
    if parts.scheme not in ("http", "https"):
        return False
    host = (parts.hostname or "").lower()
    if not host:
        return False
    if allow_subdomains:
        return _registrable_domain(host) == scope.registrable_domain
    return _strip_www(host) == _strip_www(scope.seed_host)
