"""Unit tests for url_policy.normalize / build_scope / is_in_scope."""

from __future__ import annotations

from audit.crawler.url_policy import HostScope, build_scope, is_in_scope, normalize


def test_normalize_drops_fragment() -> None:
    assert normalize("https://example.com/page#section") == "https://example.com/page"


def test_normalize_sorts_query() -> None:
    assert normalize("https://example.com/p?b=2&a=1&c=3") == "https://example.com/p?a=1&b=2&c=3"


def test_normalize_keeps_blank_query_values() -> None:
    assert normalize("https://example.com/?flag=&x=1") == "https://example.com/?flag=&x=1"


def test_normalize_lowercases_host_and_scheme() -> None:
    assert normalize("HTTPS://Example.COM/Path") == "https://example.com/Path"


def test_normalize_strips_default_http_port() -> None:
    assert normalize("http://example.com:80/a") == "http://example.com/a"


def test_normalize_strips_default_https_port() -> None:
    assert normalize("https://example.com:443/a") == "https://example.com/a"


def test_normalize_keeps_nondefault_port() -> None:
    assert normalize("http://example.com:8080/a") == "http://example.com:8080/a"


def test_normalize_empty_path_becomes_slash() -> None:
    assert normalize("https://example.com") == "https://example.com/"


def test_normalize_is_idempotent() -> None:
    once = normalize("HTTPS://Example.com:443/x?b=2&a=1#frag")
    twice = normalize(once)
    assert once == twice == "https://example.com/x?a=1&b=2"


def test_build_scope_from_www_seed() -> None:
    scope = build_scope("https://www.example.com/")
    assert scope == HostScope(registrable_domain="example.com", seed_host="www.example.com")


def test_build_scope_from_apex_seed() -> None:
    scope = build_scope("https://example.com/")
    assert scope.registrable_domain == "example.com"
    assert scope.seed_host == "example.com"


def test_is_in_scope_exact_match() -> None:
    scope = build_scope("https://example.com/")
    assert is_in_scope("https://example.com/about", scope)


def test_is_in_scope_www_variant_matches_apex() -> None:
    scope = build_scope("https://example.com/")
    assert is_in_scope("https://www.example.com/x", scope)


def test_is_in_scope_rejects_subdomain_by_default() -> None:
    scope = build_scope("https://example.com/")
    assert not is_in_scope("https://blog.example.com/post", scope)


def test_is_in_scope_allows_subdomain_when_flag_set() -> None:
    scope = build_scope("https://example.com/")
    assert is_in_scope("https://blog.example.com/post", scope, allow_subdomains=True)


def test_is_in_scope_rejects_different_registrable() -> None:
    scope = build_scope("https://example.com/")
    assert not is_in_scope("https://example.org/", scope, allow_subdomains=True)


def test_is_in_scope_rejects_non_http_scheme() -> None:
    scope = build_scope("https://example.com/")
    assert not is_in_scope("mailto:hi@example.com", scope)
    assert not is_in_scope("javascript:void(0)", scope)


def test_is_in_scope_rejects_malformed_url() -> None:
    scope = build_scope("https://example.com/")
    assert not is_in_scope("not a url", scope)
