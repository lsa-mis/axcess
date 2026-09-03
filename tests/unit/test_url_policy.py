"""Unit tests for url_policy.normalize / build_scope / is_in_scope."""

from __future__ import annotations

from audit.crawler.url_policy import (
    HostScope,
    build_scope,
    compare_key,
    is_in_scope,
    normalize,
    normalize_seed_url,
)


def test_normalize_drops_fragment() -> None:
    assert normalize("https://example.com/page#section") == "https://example.com/page"


def test_normalize_preserves_hash_router_path() -> None:
    assert normalize("https://example.com/#/about") == "https://example.com/#/about"
    assert normalize("https://example.com/#!/projects") == "https://example.com/#!/projects"


def test_normalize_keeps_hash_routes_distinct_from_in_page_anchors() -> None:
    assert normalize("https://example.com/#main-content") == "https://example.com/"
    assert normalize("https://example.com/#/projects/42?tab=summary") == (
        "https://example.com/#/projects/42?tab=summary"
    )


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


# ---------- path scope + auto-slash -----------------------------------------


def test_normalize_seed_url_adds_trailing_slash_on_dir_like_path() -> None:
    assert (
        normalize_seed_url("https://example.com/bicentennial")
        == "https://example.com/bicentennial/"
    )


def test_normalize_seed_url_preserves_existing_slash() -> None:
    assert normalize_seed_url("https://example.com/docs/") == "https://example.com/docs/"


def test_normalize_seed_url_leaves_file_seeds_alone() -> None:
    # Ends in an extension → treated as a file, no slash added.
    for seed in (
        "https://example.com/index.html",
        "https://example.com/docs/intro.html",
        "https://example.com/path/sitemap.xml",
    ):
        assert normalize_seed_url(seed) == seed


def test_normalize_seed_url_treats_root_as_root() -> None:
    assert normalize_seed_url("https://example.com") == "https://example.com"
    assert normalize_seed_url("https://example.com/") == "https://example.com/"


def test_build_scope_path_prefix_for_bicentennial() -> None:
    scope = build_scope("https://lsa.umich.edu/bicentennial/")
    assert scope.path_prefix == "/bicentennial/"


def test_build_scope_path_prefix_for_file_seed_is_its_directory() -> None:
    scope = build_scope("https://example.com/docs/intro.html")
    assert scope.path_prefix == "/docs/"


def test_build_scope_whole_host_override_ignores_path() -> None:
    scope = build_scope("https://example.com/section/", whole_host=True)
    assert scope.path_prefix == "/"


def test_build_scope_bare_host_is_whole_host() -> None:
    scope = build_scope("https://example.com/")
    assert scope.path_prefix == "/"


def test_is_in_scope_honors_path_prefix() -> None:
    scope = build_scope("https://lsa.umich.edu/bicentennial/")
    # Under the prefix: in scope.
    assert is_in_scope("https://lsa.umich.edu/bicentennial/about", scope)
    assert is_in_scope("https://lsa.umich.edu/bicentennial/", scope)
    # The bare prefix (no trailing slash) should still be in-scope so the
    # server can redirect us to the canonical form.
    assert is_in_scope("https://lsa.umich.edu/bicentennial", scope)
    # Siblings with the same prefix string but different segment: out.
    assert not is_in_scope("https://lsa.umich.edu/bicentennial-news", scope)
    # Other sections: out.
    assert not is_in_scope("https://lsa.umich.edu/admissions/", scope)


def test_is_in_scope_whole_host_matches_everything() -> None:
    scope = build_scope("https://example.com/section/", whole_host=True)
    assert is_in_scope("https://example.com/anywhere/else", scope)
    assert is_in_scope("https://example.com/", scope)


def test_is_in_scope_path_prefix_combines_with_host_check() -> None:
    scope = build_scope("https://example.com/docs/")
    # Correct path prefix but wrong host → still out.
    assert not is_in_scope("https://other.example/docs/intro", scope)


def test_is_in_scope_path_prefix_with_subdomains_flag() -> None:
    scope = build_scope("https://www.example.com/docs/")
    # Subdomain off: other subdomain rejected even when the path matches.
    assert not is_in_scope("https://api.example.com/docs/intro", scope)
    # Subdomain on: accept any subdomain under the registrable domain.
    assert is_in_scope("https://api.example.com/docs/intro", scope, allow_subdomains=True)


def test_compare_key_strips_loopback_port() -> None:
    a = compare_key("http://127.0.0.1:18800/gallery.html")
    b = compare_key("http://127.0.0.1:18801/gallery.html")
    assert a == b == "http://127.0.0.1/gallery.html"


def test_compare_key_canonicalizes_loopback_aliases() -> None:
    k = compare_key("http://127.0.0.1/x")
    for variant in (
        "http://localhost/x",
        "http://127.0.0.1:8080/x",
        "http://localhost:9090/x",
        "http://0.0.0.0:3000/x",
    ):
        assert compare_key(variant) == k, variant


def test_compare_key_preserves_loopback_hash_router_path() -> None:
    a = compare_key("http://localhost:8000/#/projects")
    b = compare_key("http://127.0.0.1:9000/#/projects")
    assert a == b == "http://127.0.0.1/#/projects"


def test_compare_key_preserves_real_host_port() -> None:
    # Ports on real hosts are semantically significant — do not strip.
    assert compare_key("https://example.com:8443/x") == "https://example.com:8443/x"
    assert compare_key("https://example.com:8443/x") != compare_key("https://example.com:9443/x")


def test_compare_key_preserves_real_host() -> None:
    assert compare_key("https://example.com/x") == "https://example.com/x"


def test_compare_key_handles_inline_svg_embedded_url() -> None:
    a = compare_key("inline-svg://http://127.0.0.1:18800/page.html#0")
    b = compare_key("inline-svg://http://127.0.0.1:18801/page.html#0")
    assert a == b
    assert a.endswith("#0")
    assert "127.0.0.1/page.html" in a


def test_compare_key_handles_inline_svg_on_hash_router_page() -> None:
    value = compare_key("inline-svg://http://localhost:8000/#/about#3")
    assert value == "inline-svg://http://127.0.0.1/#/about#3"


def test_compare_key_is_idempotent() -> None:
    for url in (
        "http://localhost:8000/a?b=2&a=1",
        "https://example.com/path",
        "inline-svg://http://localhost:8000/p.html#3",
    ):
        assert compare_key(compare_key(url)) == compare_key(url)


def test_compare_key_sorts_query_for_loopback() -> None:
    a = compare_key("http://localhost:8000/x?b=2&a=1")
    b = compare_key("http://127.0.0.1:9000/x?a=1&b=2")
    assert a == b


def test_compare_key_invalid_url_returned_unchanged() -> None:
    assert compare_key("not a url") == "not a url"
