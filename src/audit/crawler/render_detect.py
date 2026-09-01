"""Cheap heuristics for deciding whether a page needs Playwright rendering.

Two detectors, both run off the static HTTP response:

:func:`is_js_only` escalates when the page looks like a single-page app that
needs to execute JavaScript to render real content (sparse DOM, noscript
meta-refresh, known SPA bootstrap hints with empty mount points).

:func:`is_challenge_response` escalates when the upstream server returned a
bot-check interstitial (Cloudflare "Just a moment...", generic "Checking
your browser" pages, AWS WAF, etc) instead of the real resource. These come
back with a 403/503/429 status code and specific body markers, so we can
spot them without false-positiving on real error pages.
"""

from __future__ import annotations

import re
from urllib.parse import urlsplit

from selectolax.parser import HTMLParser

MIN_BODY_NODE_COUNT = 15

_SPA_SIGNALS = (
    b"__NEXT_DATA__",
    b"__NUXT__",
    b"window.__INITIAL_STATE__",
    b"ng-version=",
)
_SPA_MOUNT_IDS = ("root", "app", "__next", "__nuxt")


def is_js_only(body: bytes) -> bool:
    """Return True if the static body is unlikely to carry final content."""
    if not body:
        return False
    tree = HTMLParser(body)
    body_node = tree.body
    if body_node is None:
        return False

    node_count = sum(1 for _ in body_node.traverse(include_text=False))
    if node_count < MIN_BODY_NODE_COUNT:
        return True

    if _has_noscript_meta_refresh(tree):
        return True

    has_signal = any(sig in body for sig in _SPA_SIGNALS)
    return bool(has_signal and _mount_is_empty(tree))


def _has_noscript_meta_refresh(tree: HTMLParser) -> bool:
    for ns in tree.css("noscript"):
        for meta in ns.css("meta"):
            if (meta.attributes.get("http-equiv") or "").lower() == "refresh":
                return True
    return False


def _mount_is_empty(tree: HTMLParser) -> bool:
    for mount_id in _SPA_MOUNT_IDS:
        node = tree.css_first(f"#{mount_id}")
        if node is None:
            continue
        children = [c for c in node.iter() if c.tag != "-text"]
        if not children:
            return True
    return False


# Status codes where a bot-challenge interstitial is plausible. Genuine 404s
# or 401s are excluded deliberately — we don't want to retry those in a
# real browser.
_CHALLENGE_STATUSES = frozenset({403, 429, 503})

_CHALLENGE_MARKERS = (
    b"Just a moment...",  # Cloudflare interstitial title
    b"cf-browser-verification",
    b"cf_chl_",
    b"__cf_chl_",
    b"Checking your browser",  # Cloudflare + others
    b"Attention Required! | Cloudflare",
    b"/cdn-cgi/challenge-platform",
    b"awswaf.com/token",  # AWS WAF captcha / JS challenge
    b"captcha-delivery.com",  # DataDome
)


def is_challenge_response(status_code: int, body: bytes) -> bool:
    """Return True if the response looks like a bot-check interstitial.

    Match requires BOTH a plausible status code and at least one known marker
    in the body, so a static ``403 Forbidden`` page with no JS challenge
    stays treated as a real 403.
    """
    if status_code not in _CHALLENGE_STATUSES or not body:
        return False
    # The markers are short and the bodies are small (< 50KB for most
    # challenge pages). Linear byte search is fine.
    return any(marker in body for marker in _CHALLENGE_MARKERS)


# Password / OTP / WebAuthn form controls. A session that has lapsed usually
# lands on a same-origin login page returning HTTP 200, so status and host
# checks alone cannot tell an application page from a sign-in wall.
_AUTH_INPUT_MARKER = re.compile(
    rb"<input\b[^>]*(?:"
    rb"type\s*=\s*['\"]?password|"
    rb"autocomplete\s*=\s*['\"]?(?:current-password|one-time-code|webauthn)|"
    rb"name\s*=\s*['\"]?(?:otp|mfa|verification(?:_|-)?code)"
    rb")",
    re.IGNORECASE,
)

_AUTH_PATH_SEGMENTS = ("/login", "/sign-in", "/signin", "/sso", "/mfa", "/verify")


def looks_like_authentication_page(url: str, body: bytes) -> bool:
    """Recognize a login / re-verification page without retaining any of it.

    Deliberately conservative: a path segment that names authentication, or
    the presence of a password, one-time-code, or WebAuthn control. It reads
    no names, values, labels, or text as evidence.

    Shared by the companion, which uses it to detect a lapsed session
    mid-crawl, and by the local login handoff, which uses it to refuse to
    call a scan of a sign-in form a completed audit.
    """
    try:
        path = urlsplit(url).path.lower()
    except ValueError:
        path = ""
    if any(segment in path for segment in _AUTH_PATH_SEGMENTS):
        return True
    return _AUTH_INPUT_MARKER.search(body[:512_000]) is not None
