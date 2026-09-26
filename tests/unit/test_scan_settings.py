"""A stored scan's settings, read back for New scan (``audit.web.scan_settings``).

The snapshot is how a failed or stopped scan is started again without
re-entering every setting. These tests pin the two things that matter: every
form setting survives the trip through ``config_json``, and nothing that is
not a form setting (credentials, session state, the post-sign-in landing URL,
the user agent) can come back out.
"""

from __future__ import annotations

import json
import math
from typing import Any

import pytest

from audit.config import Settings
from audit.crawler.orchestrator import CrawlConfig, config_json_for_scan
from audit.web import server
from audit.web.scan_settings import (
    MAX_DEPTH,
    PUBLIC_MAX_PAGES,
    ScanFormSettings,
    limit_refusal,
    snapshot_from_config,
    strip_userinfo,
)

# Every field set away from its default, so a dropped or inverted mapping
# cannot pass by landing on the default.
_CUSTOM_FORM: dict[str, Any] = {
    "url": "https://example.test/section/",
    "search": None,
    "max_pages": 300,
    "max_depth": 3,
    "rps": 1.5,
    "workers": 4,
    "include_subdomain": True,
    "whole_host": True,
    "ignore_robots": True,
    "skip_ocr": False,
    "skip_vlm": False,
    "static_only": False,
    "show_browser": True,
    "scan_engine": "both",
    "skip_interaction": True,
    "skip_keyboard": True,
    "skip_responsive": True,
    "skip_semantic": False,
    "skip_focus": True,
    "skip_visual": False,
    "skip_rendered_storage": True,
    "axe_level": "AAA",
    "wcag_version": "2.2",
}


def _round_trip(form: dict[str, Any]) -> dict[str, Any]:
    config = server._build_crawl_config(form, Settings())
    snapshot = snapshot_from_config(
        scan_id=7, seed_url=form["url"], config_json=config_json_for_scan(config)
    )
    assert snapshot.scan_id == 7
    assert snapshot.mode == "public"
    return snapshot.settings.model_dump(mode="json")


def test_every_public_form_setting_round_trips() -> None:
    assert _round_trip(_CUSTOM_FORM) == _CUSTOM_FORM


def test_the_form_defaults_round_trip() -> None:
    # PUBLIC_DEFAULTS in scanPolicy.ts.
    defaults = {
        **_CUSTOM_FORM,
        "max_pages": 2500,
        "max_depth": 10,
        "rps": 2.0,
        "workers": 8,
        "include_subdomain": False,
        "whole_host": False,
        "ignore_robots": False,
        "skip_ocr": False,
        "skip_vlm": True,
        "show_browser": False,
        "scan_engine": "axe",
        "skip_interaction": False,
        "skip_keyboard": False,
        "skip_responsive": False,
        "skip_semantic": True,
        "skip_focus": False,
        "skip_visual": True,
        "skip_rendered_storage": False,
        "axe_level": "AA",
        "wcag_version": "2.1",
    }
    assert _round_trip(defaults) == defaults


def test_fast_crawl_with_alfa_round_trips() -> None:
    form = {**_CUSTOM_FORM, "static_only": True, "scan_engine": "alfa", "skip_interaction": True}
    assert _round_trip(form) == form


def test_snapshot_fields_are_exactly_the_form_fields() -> None:
    # The TypeScript NewScanPayload; a field added there without a mapping
    # here (or the other way round) fails.
    assert set(ScanFormSettings.model_fields) == set(_CUSTOM_FORM)


def test_login_scan_reads_as_login_and_drops_session_details() -> None:
    config = CrawlConfig(
        seed_url="https://app.example.test/courses/",
        # Where sign-in landed: single-use codes can ride in it.
        start_url="https://app.example.test/courses/?code=one-time-sso-code",
        user_agent="AxcessTestAgent/1.0",
        browser_only=True,
        js_eager=True,
        resumable=False,
        ignore_robots=True,
        semantic_enabled=False,
        visual_checks_enabled=False,
        workers=2,
        rps=1.0,
    )
    snapshot = snapshot_from_config(
        scan_id=3, seed_url=config.seed_url, config_json=config_json_for_scan(config)
    )
    assert snapshot.mode == "login"
    assert snapshot.settings.url == "https://app.example.test/courses/"
    assert snapshot.settings.workers == 2
    dumped = snapshot.model_dump_json()
    assert "one-time-sso-code" not in dumped
    assert "AxcessTestAgent" not in dumped
    assert "start_url" not in dumped


def test_unknown_config_keys_never_reach_the_snapshot() -> None:
    secrets = {
        "password": "hunter2-password",
        "cookies": [{"name": "session", "value": "cookie-secret-value"}],
        "storage_state": {"origins": [{"localStorage": "storage-secret-value"}]},
        "authorization": "Bearer token-secret-value",
        "session_token": "session-secret-value",
    }
    config_json = json.dumps({"max_pages": 40, **secrets})
    snapshot = snapshot_from_config(
        scan_id=1, seed_url="https://example.test/", config_json=config_json
    )
    dumped = snapshot.model_dump_json()
    for needle in (
        "hunter2-password",
        "cookie-secret-value",
        "storage-secret-value",
        "token-secret-value",
        "session-secret-value",
    ):
        assert needle not in dumped
    assert snapshot.settings.max_pages == 40


def test_credentials_in_the_address_are_removed() -> None:
    snapshot = snapshot_from_config(
        scan_id=1,
        seed_url="https://alice:hunter2@example.test/a/?page=2",
        config_json="{}",
    )
    assert snapshot.settings.url == "https://example.test/a/?page=2"
    assert "hunter2" not in snapshot.model_dump_json()


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("https://example.test/", "https://example.test/"),
        ("https://user@example.test:8443/x", "https://example.test:8443/x"),
        ("https://u:p@ss@example.test/", "https://example.test/"),
    ],
)
def test_strip_userinfo(raw: str, expected: str) -> None:
    assert strip_userinfo(raw) == expected


@pytest.mark.parametrize("config_json", ["{}", None, "not json", "[1, 2]", '{"max_pages": "lots"}'])
def test_an_old_or_unreadable_config_falls_back_to_form_defaults(
    config_json: str | None,
) -> None:
    snapshot = snapshot_from_config(
        scan_id=1, seed_url="https://example.test/", config_json=config_json
    )
    settings = snapshot.settings
    assert snapshot.mode == "public"
    assert (settings.max_pages, settings.max_depth, settings.rps, settings.workers) == (
        2500,
        10,
        2.0,
        8,
    )
    assert settings.scan_engine == "axe"
    assert settings.whole_host is False
    # A stored scan without a version ran 2.2; the snapshot says what ran.
    assert settings.wcag_version == "2.2"


@pytest.mark.parametrize(
    ("body", "field"),
    [
        ({}, None),
        ({"max_pages": None, "max_depth": None}, None),
        ({"max_pages": 1, "max_depth": 1}, None),
        ({"max_pages": PUBLIC_MAX_PAGES, "max_depth": MAX_DEPTH}, None),
        ({"max_pages": 300.0}, None),
        ({"max_pages": 0}, "max_pages"),
        ({"max_pages": -5}, "max_pages"),
        ({"max_pages": PUBLIC_MAX_PAGES + 1}, "max_pages"),
        ({"max_pages": 2.5}, "max_pages"),
        ({"max_pages": "300"}, "max_pages"),
        ({"max_pages": True}, "max_pages"),
        ({"max_pages": math.nan}, "max_pages"),
        ({"max_pages": math.inf}, "max_pages"),
        ({"max_depth": 0}, "max_depth"),
        ({"max_depth": MAX_DEPTH + 1}, "max_depth"),
    ],
)
def test_limit_refusal(body: dict[str, Any], field: str | None) -> None:
    refusal = limit_refusal(body)
    assert (refusal[0] if refusal else None) == field
