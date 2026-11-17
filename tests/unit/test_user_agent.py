"""The browser name (user agent) a public scan sends, and robots.txt matching."""

from __future__ import annotations

from typing import Any

import pytest

from audit.config import Settings
from audit.crawler.user_agent import (
    MAX_USER_AGENT_LENGTH,
    chosen_user_agent,
    chromium_user_agent,
    user_agent_problem,
)

SAFARI = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/27.2 Safari/605.1.15"
)


@pytest.mark.parametrize(
    "value",
    [None, "", "   ", 5, "a\nb", "a\rb", "tab\there", "café", "A" * (MAX_USER_AGENT_LENGTH + 1)],
)
def test_names_that_cannot_be_sent_are_refused(value: object) -> None:
    assert user_agent_problem(value) is not None


@pytest.mark.parametrize("value", [SAFARI, "x", "A" * MAX_USER_AGENT_LENGTH, "  padded/1  "])
def test_printable_names_are_accepted(value: str) -> None:
    assert user_agent_problem(value) is None


@pytest.mark.parametrize(
    ("config", "expected"),
    [
        ({}, None),
        ({"user_agent": SAFARI}, None),  # an older scan: the server's own name
        ({"user_agent_choice": "axcess", "user_agent": SAFARI}, None),
        ({"user_agent_choice": "safari_mac", "user_agent": SAFARI}, SAFARI),
        ({"user_agent_choice": "custom", "user_agent": " Bot/1 "}, "Bot/1"),
        ({"user_agent_choice": "custom", "user_agent": "Bot/1\r\nX: y"}, None),
        ({"user_agent_choice": "Not A Slug", "user_agent": SAFARI}, None),
    ],
)
def test_chosen_user_agent(config: dict[str, Any], expected: str | None) -> None:
    assert chosen_user_agent(config) == expected


def _form(**overrides: Any) -> dict[str, Any]:
    return {
        "url": "https://example.test/",
        "max_pages": 10,
        "max_depth": 2,
        "rps": 1.0,
        "workers": 1,
        "include_subdomain": False,
        "ignore_robots": False,
        "skip_ocr": True,
        "skip_vlm": True,
        **overrides,
    }


def test_a_chosen_name_is_sent_but_robots_txt_is_read_for_axcess() -> None:
    from audit.web.server import _build_crawl_config

    settings = Settings(user_agent="axcess/0.1 (+local accessibility audit)")
    config = _build_crawl_config(_form(user_agent_choice="safari_mac", user_agent=SAFARI), settings)
    assert config.user_agent == SAFARI
    assert config.robots_user_agent == settings.user_agent
    assert config.user_agent_choice == "safari_mac"

    # A stored scan with no choice (from before 2026-11-16) sent Axcess's
    # own name, and running it again keeps that.
    default = _build_crawl_config(_form(), settings)
    assert default.user_agent == settings.user_agent
    assert default.robots_user_agent is None
    assert default.user_agent_choice is None

    # "Chrome on this computer", the default since 2026-11-16: the server
    # builds the name; robots.txt is still read for Axcess.
    chrome = _build_crawl_config(_form(user_agent_choice="chrome", user_agent=""), settings)
    assert chrome.user_agent == chromium_user_agent()
    assert chrome.robots_user_agent == settings.user_agent
    assert chrome.user_agent_choice == "chrome"


@pytest.mark.parametrize(
    ("system", "platform"),
    [
        ("win32", "(Windows NT 10.0; Win64; x64)"),
        ("darwin", "(Macintosh; Intel Mac OS X 10_15_7)"),
        ("linux", "(X11; Linux x86_64)"),
    ],
)
def test_chrome_on_this_computer_is_the_engines_version_and_this_system(
    system: str, platform: str
) -> None:
    """The engine's own major version, as Chrome reduces it, never a fixed
    newer one: Chromium's Client Hints report the real version."""
    import json
    from pathlib import Path

    import playwright

    record = Path(playwright.__file__).parent / "driver" / "package" / "browsers.json"
    chromium = next(
        b for b in json.loads(record.read_text())["browsers"] if b["name"] == "chromium"
    )
    major = chromium["browserVersion"].split(".")[0]
    name = chromium_user_agent(system)
    assert name == (
        f"Mozilla/5.0 {platform} AppleWebKit/537.36 (KHTML, like Gecko) "
        f"Chrome/{major}.0.0.0 Safari/537.36"
    )
    assert user_agent_problem(name) is None
    assert chosen_user_agent({"user_agent_choice": "chrome"}) == chromium_user_agent()


async def test_robots_rules_for_axcess_apply_under_a_browser_name() -> None:
    """The checker the crawl builds matches robots.txt against Axcess's name."""
    import httpx
    import respx

    from audit.crawler.robots import RobotsChecker

    robots = "User-agent: axcess\nDisallow: /private/\n\nUser-agent: *\nAllow: /\n"
    with respx.mock:
        respx.get("https://example.test/robots.txt").mock(
            return_value=httpx.Response(200, text=robots)
        )
        async with httpx.AsyncClient(headers={"User-Agent": SAFARI}) as client:
            as_axcess = RobotsChecker(client, user_agent="axcess/0.1 (+local accessibility audit)")
            as_safari = RobotsChecker(client, user_agent=SAFARI)
            assert not await as_axcess.allowed("https://example.test/private/page")
            # What the crawl would wrongly do if it matched the sent name.
            assert await as_safari.allowed("https://example.test/private/page")
