"""The browser name (user agent) a public scan sends to the site.

By default a scan names itself: ``Settings.user_agent``, "axcess/0.1 ...".
New scan also lets a person send a browser's name instead, from a list of
current browsers or typed by hand. Some sites serve a different page, or
refuse the request, depending on that name, and an audit should be able to
see the page a real visitor's browser gets.

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

import re
from collections.abc import Mapping
from typing import Any

#: The choice that sends Axcess's own name, ``Settings.user_agent``.
DEFAULT_CHOICE = "axcess"
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


def chosen_user_agent(config: Mapping[str, Any]) -> str | None:
    """The browser name a stored scan chose in the form, or None.

    None means the scan sent Axcess's own name (or predates the choice), so
    a caller keeps its own default.
    """
    choice = config.get("user_agent_choice")
    if not is_choice(choice) or choice == DEFAULT_CHOICE:
        return None
    value = config.get("user_agent")
    if user_agent_problem(value) is not None:
        return None
    return str(value).strip()
