"""The WCAG version a scan is audited against, and how stored scans read it.

New scans choose between WCAG 2.1 and 2.2 and default to 2.1, the current
U-M standard. The choice is stored in ``scans.config_json`` next to
``axe_level``. A scan stored before the setting existed has no such key and
ran every engine with the WCAG 2.2 rule set, so it must keep reading as
"2.2": the report of an old scan describes what actually ran, and a resumed
old scan keeps running the rules it started with.

That "missing means 2.2" rule lives here and nowhere else. Every reader of
``config_json`` (resume, the methods-used row, exports, the issue projection,
report comparison, the protected companion) goes through
:func:`stored_wcag_version`.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, Literal, TypeGuard

WcagVersion = Literal["2.1", "2.2"]

WCAG_VERSIONS: tuple[WcagVersion, ...] = ("2.1", "2.2")
# What a new scan runs when nobody chose: the current U-M standard.
DEFAULT_WCAG_VERSION: WcagVersion = "2.1"
# What a stored scan without the key actually ran with.
LEGACY_WCAG_VERSION: WcagVersion = "2.2"


def is_wcag_version(value: object) -> TypeGuard[WcagVersion]:
    """True for exactly "2.1" or "2.2"."""
    return isinstance(value, str) and value in WCAG_VERSIONS


def stored_wcag_version(config: Mapping[str, Any] | str | bytes | None) -> WcagVersion:
    """The version a stored scan config says it ran with.

    Accepts the parsed config mapping or the raw ``config_json`` text. A
    config without the key, one that cannot be parsed, or one holding an
    unexpected value reads as WCAG 2.2, because every scan written before
    this setting existed ran the 2.2 rule set.
    """
    if isinstance(config, (str, bytes)):
        try:
            config = json.loads(config or "{}")
        except (TypeError, ValueError):
            return LEGACY_WCAG_VERSION
    if not isinstance(config, Mapping):
        return LEGACY_WCAG_VERSION
    value = config.get("wcag_version")
    return value if is_wcag_version(value) else LEGACY_WCAG_VERSION
