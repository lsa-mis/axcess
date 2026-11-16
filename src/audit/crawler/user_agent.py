"""The browser name (user agent) a public scan sends to the site.

By default a scan sends Chrome's name, built from the Chromium Axcess runs
(``CHROME_CHOICE``, ``chromium_user_agent``): the developer's decision,
2026-11-16. Bot filters block or challenge a scanner's own name, and some
sites serve it a cut-down page, so the scan audited a page no visitor
gets. The version is the engine's own, never a fixed newer one: Chromium
reports its real version in its Client Hints, and a name that disagrees
with them is itself a sign of a bot.

New scan also lets a person send Axcess's own name (``DEFAULT_CHOICE``,
``Settings.user_agent``, "axcess/0.1 ..."), so a site owner can tell the
scanner apart in their logs, or another browser's name from a list, or one
typed by hand. A scan from before 2026-11-16 that recorded no choice sent
Axcess's own name, and running it again keeps that.

Only the name changes. Pages are still drawn by Playwright's Chromium, and
Chromium still describes itself in its Client Hints (``Sec-CH-UA``,
``navigator.userAgentData``) and in ``navigator.platform``; verified
2026-11-13 against a local server. The form says so.

What is stored in ``scans.config_json``:

``user_agent``
    The exact string sent, as before.
``user_agent_choice``
    Which entry of the form's list was chosen (a slug, such as
    ``chrome_windows``, or ``custom``). Absent from older scans and from
    scans that kept Axcess's own name.

robots.txt rules are always matched against Axcess's own name
(``CrawlConfig.robots_user_agent``), never against the browser name sent:
choosing "Chrome" must not quietly change which robots.txt rules apply.
"""

from __future__ import annotations

import json
import re
import sys
from collections.abc import Mapping
from functools import lru_cache
from pathlib import Path
from typing import Any

#: The choice that sends Axcess's own name, ``Settings.user_agent``. It was
#: the default until 2026-11-16, and is what a stored scan with no choice
#: sent (``chosen_user_agent``).
DEFAULT_CHOICE = "axcess"
#: Chrome's name, as the Chromium Axcess runs on this computer: what a new
#: scan sends unless the person chooses otherwise.
CHROME_CHOICE = "chrome"
#: The Chromium major version when Playwright's own record cannot be read.
#: Keep it at the version the pinned Playwright ships (browsers.json).
_FALLBACK_CHROMIUM_MAJOR = "145"
#: The choice whose string the person typed.
CUSTOM_CHOICE = "custom"
#: Real browser strings are 70-200 characters. The cap bounds what is stored
#: and sent on every request.
MAX_USER_AGENT_LENGTH = 512

_CHOICE = re.compile(r"^[a-z0-9_]{1,40}$")
# Visible ASCII and the space. A header value may not hold CR or LF (header
# injection), and non-ASCII text in a header is read differently by
# different servers.
_PRINTABLE_ASCII = re.compile(r"^[\x20-\x7e]+$")


def is_choice(value: object) -> bool:
    """True for a choice slug in the shape the form sends."""
    return isinstance(value, str) and bool(_CHOICE.fullmatch(value))


def user_agent_problem(value: object) -> str | None:
    """A plain message saying why ``value`` cannot be sent, or None."""
    if not isinstance(value, str) or not value.strip():
        return "Type the browser name (user agent) to send, or choose one from the list."
    text = value.strip()
    if len(text) > MAX_USER_AGENT_LENGTH:
        return f"The browser name (user agent) can be at most {MAX_USER_AGENT_LENGTH} characters."
    if not _PRINTABLE_ASCII.fullmatch(text):
        return (
            "The browser name (user agent) can use only English letters, numbers, "
            "spaces and keyboard symbols, on one line."
        )
    return None


@lru_cache(maxsize=1)
def chromium_major() -> str:
    """The major version of the Chromium Playwright runs, such as "145"."""
    try:
        import playwright

        record = Path(playwright.__file__).parent / "driver" / "package" / "browsers.json"
        for browser in json.loads(record.read_text(encoding="utf-8"))["browsers"]:
            if browser.get("name") == "chromium":
                major = str(browser["browserVersion"]).split(".", 1)[0]
                if major.isdigit():
                    return major
    except (OSError, ValueError, KeyError, TypeError, ImportError):
        pass
    return _FALLBACK_CHROMIUM_MAJOR


def chromium_user_agent(system: str | None = None) -> str:
    """Chrome's name as the Chromium Axcess runs on this computer would send it.

    The platform part is this computer's, as Chromium's other signals
    (``navigator.platform``, Client Hints) report it, in the frozen form
    Chrome sends since User-Agent Reduction ("Windows NT 10.0", "Intel Mac
    OS X 10_15_7", "X11; Linux x86_64"), and the version is the major only
    ("145.0.0.0"), as Chrome sends it.
    """
    system = system or sys.platform
    if system.startswith("win"):
        platform = "Windows NT 10.0; Win64; x64"
    elif system == "darwin":
        platform = "Macintosh; Intel Mac OS X 10_15_7"
    else:
        platform = "X11; Linux x86_64"
    return (
        f"Mozilla/5.0 ({platform}) AppleWebKit/537.36 (KHTML, like Gecko) "
        f"Chrome/{chromium_major()}.0.0.0 Safari/537.36"
    )


def chosen_user_agent(config: Mapping[str, Any]) -> str | None:
    """The browser name a stored scan chose in the form, or None.

    None means the scan sent Axcess's own name (or predates the choice), so
    a caller keeps its own default. "chrome" is worked out here, from the
    Chromium this computer runs.
    """
    choice = config.get("user_agent_choice")
    if not is_choice(choice) or choice == DEFAULT_CHOICE:
        return None
    if choice == CHROME_CHOICE:
        return chromium_user_agent()
    value = config.get("user_agent")
    if user_agent_problem(value) is not None:
        return None
    return str(value).strip()
