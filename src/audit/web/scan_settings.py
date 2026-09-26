"""A stored scan's settings, in the New scan form's own shape.

When a scan fails or is stopped, the person starting it again should not
have to re-enter every choice they made. ``scans.config_json`` already holds
those choices (it is how a report says which methods ran), so this module
reads them back into the fields the form posts.

It is an allow-list, not a copy. Only the form's own settings are read, one
named key at a time, and nothing else in ``config_json`` can reach the
response: not the user agent, not the post-sign-in landing URL
(``start_url``, which can carry single-use sign-in codes), and not anything a
later change might add. The address has any ``user:password@`` removed.
Login scans never store a password, cookie or session in the first place;
the authorization and image-storage confirmations are not settings and are
never returned, so the person gives them again for the new run.

The limits the public create endpoint enforces live here too, next to the
form fields they bound, so the form and the server agree on one range.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from typing import Any, Literal
from urllib.parse import urlsplit, urlunsplit

from pydantic import BaseModel, ConfigDict, ValidationError

from audit.crawler.search import SearchConfig
from audit.wcag_version import WcagVersion, stored_wcag_version

# Inclusive bounds for a public scan's two limits. The login endpoint's
# request model carries its own (lower) page cap.
MIN_LIMIT = 1
PUBLIC_MAX_PAGES = 10_000
MAX_DEPTH = 20

ScanMode = Literal["public", "login"]


class ScanFormSettings(BaseModel):
    """The New scan form's fields (``NewScanPayload`` in the SPA)."""

    model_config = ConfigDict(extra="forbid")

    url: str
    search: SearchConfig | None = None
    max_pages: int
    max_depth: int
    rps: float
    workers: int
    include_subdomain: bool
    whole_host: bool
    ignore_robots: bool
    skip_ocr: bool
    skip_vlm: bool
    static_only: bool
    show_browser: bool
    scan_engine: Literal["axe", "alfa", "both"]
    skip_interaction: bool
    skip_keyboard: bool
    skip_responsive: bool
    skip_semantic: bool
    skip_focus: bool
    skip_visual: bool
    skip_rendered_storage: bool
    axe_level: Literal["A", "AA", "AAA"]
    wcag_version: WcagVersion


class ScanSettingsSnapshot(BaseModel):
    """``GET /api/scans/{scan_id}/settings``."""

    model_config = ConfigDict(extra="forbid")

    scan_id: int
    mode: ScanMode
    settings: ScanFormSettings


def strip_userinfo(url: str) -> str:
    """``url`` without any ``user:password@`` in its authority."""
    try:
        parts = urlsplit(url)
    except ValueError:
        return url
    if "@" not in parts.netloc:
        return url
    return urlunsplit(parts._replace(netloc=parts.netloc.rsplit("@", 1)[1]))


def _parse(config_json: str | bytes | None) -> Mapping[str, Any]:
    try:
        parsed = json.loads(config_json or "{}")
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, Mapping) else {}


def _flag(config: Mapping[str, Any], key: str, default: bool) -> bool:
    value = config.get(key, default)
    return value if isinstance(value, bool) else default


def _number(config: Mapping[str, Any], key: str, default: float) -> float:
    value = config.get(key, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return default
    return float(value)


def _mode(config: Mapping[str, Any]) -> ScanMode:
    # A local login scan is the only writer that renders every page in the
    # signed-in browser *and* marks its row unresumable (the session dies
    # with the process). Nothing else sets both.
    browser_only = _flag(config, "browser_only", default=False)
    resumable = _flag(config, "resumable", default=True)
    return "login" if browser_only and not resumable else "public"


def _search(config: Mapping[str, Any]) -> SearchConfig | None:
    raw = config.get("search")
    if not raw:
        return None
    try:
        return SearchConfig.model_validate(raw)
    except ValidationError:
        # A search setup this version cannot read is dropped rather than
        # failing the whole snapshot; the form shows search as off.
        return None


def snapshot_from_config(
    *, scan_id: int, seed_url: str, config_json: str | bytes | None
) -> ScanSettingsSnapshot:
    """Read one scan's form settings back from its stored config.

    A key an older row does not have falls back to the form's own default
    for that field.
    """
    config = _parse(config_json)
    axe = _flag(config, "axe_enabled", default=True)
    alfa = _flag(config, "alfa_enabled", default=False)
    engine: Literal["axe", "alfa", "both"] = "both" if axe and alfa else "alfa" if alfa else "axe"
    level = config.get("axe_level")
    axe_level: Literal["A", "AA", "AAA"] = level if level in ("A", "AA", "AAA") else "AA"
    settings = ScanFormSettings(
        url=strip_userinfo(seed_url),
        search=_search(config),
        max_pages=int(_number(config, "max_pages", 2500)),
        max_depth=int(_number(config, "max_depth", 10)),
        rps=_number(config, "rps", 2.0),
        workers=int(_number(config, "workers", 8)),
        include_subdomain=_flag(config, "allow_subdomains", default=False),
        whole_host=_flag(config, "whole_host", default=False),
        ignore_robots=_flag(config, "ignore_robots", default=False),
        skip_ocr=not _flag(config, "ocr_enabled", default=True),
        skip_vlm=not _flag(config, "vlm_enabled", default=False),
        static_only=not _flag(config, "js_eager", default=True),
        show_browser=not _flag(config, "browser_headless", default=True),
        scan_engine=engine,
        skip_interaction=not _flag(config, "interaction_checks_enabled", default=True),
        skip_keyboard=not _flag(config, "keyboard_probe_enabled", default=True),
        skip_responsive=not _flag(config, "responsive_checks_enabled", default=True),
        skip_semantic=not _flag(config, "semantic_enabled", default=False),
        skip_focus=not _flag(config, "focus_checks_enabled", default=True),
        skip_visual=not _flag(config, "visual_checks_enabled", default=False),
        skip_rendered_storage=not _flag(config, "store_rendered_html", default=True),
        axe_level=axe_level,
        wcag_version=stored_wcag_version(config),
    )
    return ScanSettingsSnapshot(scan_id=scan_id, mode=_mode(config), settings=settings)


def limit_refusal(body: Mapping[str, Any]) -> tuple[str, str] | None:
    """``(field, message)`` for a public scan limit out of range, else None.

    A missing or null limit keeps the endpoint's default. A value that is
    present but not a whole number in range is refused by name: it used to
    be coerced, so 0 silently became 2,500 pages and 50,000 was accepted.
    """
    bounds = {
        "max_pages": ("Max pages", PUBLIC_MAX_PAGES),
        "max_depth": ("Max link depth", MAX_DEPTH),
    }
    for field, (label, maximum) in bounds.items():
        value = body.get(field)
        if value is None:
            continue
        # Python's JSON parser accepts NaN and Infinity; neither is a limit.
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or value != int(value)
        ):
            return field, f"{label} must be a whole number."
        if not MIN_LIMIT <= value <= maximum:
            return field, f"{label} must be from {MIN_LIMIT} to {maximum:,}."
    return None
