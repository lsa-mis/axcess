"""Blocklist predicates, ported from a11y-crawler's urlUtils.ts.

Semantics are deliberately identical: ``is_blocked`` is a case-insensitive
substring test against the whole URL, ``is_excluded`` is an exact / path-prefix
/ prefix-plus-query test against operator-supplied entries.
"""

from __future__ import annotations

import pytest

from audit.crawler.url_policy import (
    DEFAULT_BLOCKED_URL_PATTERNS,
    is_blocked,
    is_excluded,
)


@pytest.mark.parametrize(
    "url",
    [
        "https://app.example.edu/logout",
        "https://app.example.edu/account/logout",
        "https://app.example.edu/auth/sign-out",
        "https://app.example.edu/users/7/delete",
        "https://app.example.edu/LOGOUT",  # case-insensitive
        "https://app.example.edu/x?next=/logout",  # substring, anywhere
    ],
)
def test_session_ending_urls_are_blocked_by_default(url: str) -> None:
    assert is_blocked(url, DEFAULT_BLOCKED_URL_PATTERNS)


@pytest.mark.parametrize(
    "url",
    [
        "https://app.example.edu/",
        "https://app.example.edu/course/abc/dashboard/",
        "https://app.example.edu/login/forgot_password",
    ],
)
def test_ordinary_urls_are_not_blocked(url: str) -> None:
    assert not is_blocked(url, DEFAULT_BLOCKED_URL_PATTERNS)


@pytest.mark.parametrize(
    "url",
    [
        "https://app.example.edu/deleted-items",
        "https://app.example.edu/removed-users",
        "https://app.example.edu/logout-help",
    ],
)
def test_substring_matching_over_blocks_and_that_is_the_trade(url: str) -> None:
    """Matching is substring, not path-segment — inherited from a11y-crawler.

    ``/deleted-items`` contains ``/delete`` and is therefore skipped, even
    though it is a listing page. That is the intended side of the trade:
    over-blocking costs one page of coverage, under-blocking costs the whole
    authenticated scan when the crawler signs itself out. Recorded here so a
    future tightening to path-segment matching is a deliberate decision
    rather than an accident.
    """
    assert is_blocked(url, DEFAULT_BLOCKED_URL_PATTERNS)


def test_empty_patterns_never_block() -> None:
    assert not is_blocked("https://app.example.edu/logout", ())
    # An empty string must not match everything.
    assert not is_blocked("https://app.example.edu/logout", ("",))


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://a.example/admin", True),  # exact
        ("https://a.example/admin/", True),  # prefix + "/"
        ("https://a.example/admin/users", True),  # deeper prefix
        ("https://a.example/admin?tab=1", True),  # prefix + query
        ("https://a.example/administration", False),  # not a path boundary
        ("https://a.example/other", False),
    ],
)
def test_excluded_scope_matching(url: str, expected: bool) -> None:
    assert is_excluded(url, ["https://a.example/admin"]) is expected


def test_excluded_ignores_a_trailing_slash_on_the_entry() -> None:
    """Both spellings of an entry must behave identically."""
    for entry in ("https://a.example/admin", "https://a.example/admin/"):
        assert is_excluded("https://a.example/admin/users", [entry])
