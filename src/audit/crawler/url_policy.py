"""URL normalization and scope rules.

Normalization is aggressive and deterministic so that two cosmetic variants of
the same URL dedupe against the same row.

Scope is anchored on the seed URL's host AND path. A seed like
``https://lsa.umich.edu/bicentennial/`` produces a scope whose
``path_prefix`` is ``/bicentennial/``; the crawler then follows links
whose path starts with that prefix. If the user enters the same URL
without the trailing slash (``…/bicentennial``), we auto-add the slash so
long as the last path segment doesn't look like a filename (no dot in
the last segment). Seeds with an extension (``/docs/intro.html``) fall
back to the directory of the seed (``/docs/``) so links to sibling pages
still get crawled. A bare-host seed (``/``) gives a whole-host scope.

Subdomains are still opt-in via ``allow_subdomains``.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import tldextract

_DEFAULT_PORTS = {"http": "80", "https": "443"}

_extract = tldextract.TLDExtract(suffix_list_urls=())
"""Offline-only PSL extractor — uses the snapshot bundled with tldextract."""


# Ported from a11y-crawler (lib/crawler/config.ts). A crawl that follows a
# "Sign out" link destroys the session it was given and then reports every
# remaining page as the login screen — the scan looks like it completed,
# having tested nothing. The defaults are path fragments rather than whole
# paths because applications spell the same action many ways
# (``/logout``, ``/account/logout``, ``/auth/sign-out``).
DEFAULT_BLOCKED_URL_PATTERNS: tuple[str, ...] = (
    "/logout",
    "/delete",
    "/remove",
    "/signout",
    "/sign-out",
    "/log-out",
)


def is_blocked(url: str, patterns: Iterable[str]) -> bool:
    """True if ``url`` contains any pattern, case-insensitively.

    Substring rather than path-segment matching, matching a11y-crawler's
    ``isBlocked``. It is deliberately broad: over-blocking costs a page of
    coverage, while under-blocking costs the whole authenticated scan.
    """
    lowered = url.lower()
    return any(pattern and pattern.lower() in lowered for pattern in patterns)


def is_excluded(url: str, scopes: Iterable[str]) -> bool:
    """True if ``url`` is, or sits under, one of ``scopes``.

    Mirrors a11y-crawler's ``isExcluded``: an entry matches the URL exactly,
    or as a path prefix, or as a prefix followed by a query string. The
    trailing slash on an entry is ignored so both spellings behave alike.
    This is the operator's "never visit these" list, distinct from the
    pattern blocklist above.
    """
    for scope in scopes:
        if not scope:
            continue
        clean = scope.rstrip("/")
        if url == clean or url.startswith(clean + "/") or url.startswith(clean + "?"):
            return True
    return False


def normalize(url: str) -> str:
    """Return a canonical form of ``url`` suitable for equality/dedupe.

    Rules:
      * lowercase scheme and host
      * strip default ports (``:80`` for http, ``:443`` for https)
      * sort query parameters alphabetically, preserving blank values
      * drop ordinary in-page fragments
      * preserve hash-router paths (``#/route`` and ``#!/route``), because
        they identify distinct rendered pages in single-page applications
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

    fragment = _spa_route_fragment(parts.fragment)

    return urlunsplit((scheme, netloc, path, query, fragment))


def _spa_route_fragment(fragment: str) -> str:
    """Return a fragment only when it has the shape of a client-side route.

    Ordinary fragments point within one document and must continue to dedupe
    (``#main-content`` is not another page). Hash routers use a leading slash,
    optionally behind the historical ``!`` marker, to represent a distinct
    application route whose DOM must be rendered and audited separately.
    """
    if fragment.startswith("/") or fragment.startswith("!/"):
        return fragment
    return ""


@dataclass(frozen=True)
class HostScope:
    """Crawl scope anchored on a seed URL's host AND path prefix."""

    registrable_domain: str
    seed_host: str
    path_prefix: str = "/"
    """URL path prefix (always ends in ``/``). ``/`` means whole-host."""


def _registrable_domain(host: str) -> str:
    parts = _extract(host)
    if not parts.domain or not parts.suffix:
        return host
    return f"{parts.domain}.{parts.suffix}"


def _looks_like_filename(segment: str) -> bool:
    """True if the last path segment looks like a file (has a dot + extension)."""
    return "." in segment and not segment.startswith(".")


def _path_prefix_for(path: str) -> str:
    """Pick a path-scope prefix from a seed URL path.

    Rules (see module docstring for rationale):

      * ``/`` → ``/`` (whole-host)
      * ends in ``/`` → returned as-is
      * last segment has an extension (``/docs/intro.html``) → the
        directory of that file (``/docs/``)
      * otherwise → auto-add a trailing slash (``/bicentennial`` →
        ``/bicentennial/``)
    """
    if not path or path == "/":
        return "/"
    if path.endswith("/"):
        return path
    last_slash = path.rfind("/")
    last_segment = path[last_slash + 1 :]
    if _looks_like_filename(last_segment):
        # Include everything up to and including the last '/'.
        return path[: last_slash + 1]
    return path + "/"


def normalize_seed_url(seed_url: str) -> str:
    """Return ``seed_url`` with a trailing slash added when the last path
    segment looks like a directory (no extension).

    Canonicalizes the input a user likely typed into a form. Does not alter
    seeds that look like files or already end with ``/``.
    """
    parts = urlsplit(seed_url.strip())
    path = parts.path or "/"
    if path == "/" or path.endswith("/"):
        return urlunsplit(parts)
    last_segment = path[path.rfind("/") + 1 :]
    if _looks_like_filename(last_segment):
        return urlunsplit(parts)
    return urlunsplit(parts._replace(path=path + "/"))


def build_scope(seed_url: str, *, whole_host: bool = False) -> HostScope:
    """Derive a ``HostScope`` from a seed URL.

    Set ``whole_host=True`` to keep the old behavior (ignore path; follow
    every in-host link). By default the scope is path-constrained, so
    ``/bicentennial/`` crawls only ``/bicentennial/*`` — not the whole site.
    """
    parts = urlsplit(seed_url)
    host = (parts.hostname or "").lower()
    prefix = "/" if whole_host else _path_prefix_for(parts.path or "/")
    return HostScope(
        registrable_domain=_registrable_domain(host),
        seed_host=host,
        path_prefix=prefix,
    )


def _strip_www(host: str) -> str:
    return host[4:] if host.startswith("www.") else host


_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1", "0.0.0.0"})  # noqa: S104  (string constant for URL host matching, not a bind address)
_CANONICAL_LOOPBACK = "127.0.0.1"

_INLINE_SVG_SCHEME = "inline-svg://"


def compare_key(url: str) -> str:
    """Canonicalize ``url`` for cross-scan matching.

    Two rules beyond :func:`normalize`:

      * On loopback hosts (``127.0.0.1``/``localhost``/``::1``/``0.0.0.0``)
        the port is dropped and the host name is canonicalized to
        ``127.0.0.1``. This way a rescan run against a different dev-server
        port doesn't register every finding as "new + resolved".
      * Inline-SVG pseudo-URLs (``inline-svg://<page_url>#<position>``) have
        the embedded page URL normalized the same way.

    For any other host, the input is returned unchanged — a port change on
    a real host is semantically significant and should not be papered over.
    """
    if url.startswith(_INLINE_SVG_SCHEME):
        inner = url[len(_INLINE_SVG_SCHEME) :]
        frag = ""
        if "#" in inner:
            # The embedded page URL may itself be a hash-router URL. The last
            # fragment is the inline SVG position; everything before it is
            # the page identity.
            inner, frag = inner.rsplit("#", 1)
        return f"{_INLINE_SVG_SCHEME}{compare_key(inner)}" + (f"#{frag}" if frag else "")

    try:
        parts = urlsplit(url)
    except ValueError:
        return url
    host = (parts.hostname or "").lower()
    if host not in _LOOPBACK_HOSTS:
        return url

    scheme = parts.scheme.lower()
    path = parts.path or "/"
    query_pairs = parse_qsl(parts.query, keep_blank_values=True)
    query = urlencode(sorted(query_pairs))
    fragment = _spa_route_fragment(parts.fragment)
    return urlunsplit((scheme, _CANONICAL_LOOPBACK, path, query, fragment))


def is_in_scope(url: str, scope: HostScope, *, allow_subdomains: bool = False) -> bool:
    """Return True if ``url`` should be crawled under ``scope``.

    Checks, in order:
      * ``http``/``https`` scheme only
      * host matches the seed (or falls under the registrable domain when
        ``allow_subdomains`` is set)
      * path starts with ``scope.path_prefix`` (``/`` matches everything)

    The ``www.`` vs apex host variance is normalized so ``example.com`` and
    ``www.example.com`` are treated as the same site.
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
        host_ok = _registrable_domain(host) == scope.registrable_domain
    else:
        host_ok = _strip_www(host) == _strip_www(scope.seed_host)
    if not host_ok:
        return False

    if scope.path_prefix == "/":
        return True
    path = parts.path or "/"
    # Match against the prefix itself OR the prefix with its trailing '/'
    # dropped — so a link to ``/bicentennial`` resolves as in-scope for a
    # ``/bicentennial/`` prefix, letting the server's redirect settle it.
    bare = scope.path_prefix.rstrip("/")
    return path == bare or path.startswith(scope.path_prefix)
