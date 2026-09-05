"""Compare an image's alt text against its visible text content.

Returns an :class:`AltAdequacy` bucket based on:
  * missing, no alt attribute was present on the ``<img>``,
  * inadequate, alt present but the text dissimilar,
  * partial, some overlap with the visible text,
  * adequate, alt captures the visible text (or there was no visible text).

An empty ``alt=""`` is treated as ``inadequate`` here because its suitability
depends on the VLM classification: decorative images with ``alt=""`` get a
low-priority finding, while essential/informational ones are a real failure.
The priority formula in :mod:`audit.synthesizer.priority` handles that
weighting, this module stays a pure string-similarity check.
"""

from __future__ import annotations

import re
from enum import StrEnum

from rapidfuzz import fuzz


class AltAdequacy(StrEnum):
    MISSING = "missing"
    INADEQUATE = "inadequate"
    PARTIAL = "partial"
    ADEQUATE = "adequate"


_PUNCT_RE = re.compile(r"[^\w\s]+")

_ADEQUATE_RATIO = 85
_PARTIAL_RATIO = 55


def normalize(text: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace."""
    cleaned = _PUNCT_RE.sub(" ", text.lower())
    return " ".join(cleaned.split())


def compare(alt: str | None, visible_text: str) -> AltAdequacy:
    """Return the adequacy bucket for ``alt`` vs ``visible_text``."""
    if alt is None:
        return AltAdequacy.MISSING

    norm_alt = normalize(alt)
    norm_text = normalize(visible_text)

    if not norm_text:
        # No visible text to compare against. Any alt is adequate; empty alt
        # is also adequate because there's nothing being hidden from AT users.
        return AltAdequacy.ADEQUATE

    if not norm_alt:
        # alt="" on an image that DOES contain visible text, author declared
        # it decorative. Downstream, the priority weight plus the VLM
        # classification will determine severity.
        return AltAdequacy.INADEQUATE

    if norm_alt == norm_text or norm_alt in norm_text or norm_text in norm_alt:
        return AltAdequacy.ADEQUATE

    ratio = fuzz.token_set_ratio(norm_alt, norm_text)
    if ratio >= _ADEQUATE_RATIO:
        return AltAdequacy.ADEQUATE
    if ratio >= _PARTIAL_RATIO:
        return AltAdequacy.PARTIAL
    return AltAdequacy.INADEQUATE


def worst(buckets: list[AltAdequacy]) -> AltAdequacy:
    """Aggregate adequacy across multiple occurrences of the same image."""
    order = {
        AltAdequacy.ADEQUATE: 0,
        AltAdequacy.PARTIAL: 1,
        AltAdequacy.INADEQUATE: 2,
        AltAdequacy.MISSING: 3,
    }
    if not buckets:
        return AltAdequacy.MISSING
    return max(buckets, key=lambda b: order[b])
