"""Every way a page's saved HTML reaches another address.

Links come from :func:`audit.analyzer.semantic.extractor.extract_links`, the
reader the link-purpose check (SC 2.4.4) already uses, so a link's text here
is the same accessible name that check reports. Frames, objects and embeds
are read here, named by their ``title`` or ``aria-label`` as a screen reader
would name them.

Links revealed by a click are not in the saved HTML: the interaction probe
reports them (``FetchResult.revealed_links``) and the tracker merges them.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit

from selectolax.parser import HTMLParser

from audit.analyzer.semantic.extractor import extract_links
from audit.crawler import url_policy
from audit.linked_files.formats import RefKind

#: Addresses read per page, links and embeds together.
MAX_PER_PAGE = 2000
_MAX_URL = 2048

_EMBEDS: tuple[tuple[str, str, RefKind], ...] = (
    ("iframe[src]", "src", "iframe"),
    ("object[data]", "data", "object"),
    ("embed[src]", "src", "embed"),
)


@dataclass(frozen=True)
class FoundLink:
    """One place on a page that reaches ``url``."""

    url: str
    how: RefKind
    #: Accessible name of the link, or the frame's or embed's title.
    text: str
    #: Accessible name of the control whose click revealed the link.
    revealed_by: str | None = None


def resolve(base_url: str, href: str) -> str | None:
    """The normalized absolute address ``href`` names, or None.

    Only http and https, never an address with a user name or password in
    it (it would be stored and shown), and never one longer than browsers
    accept.
    """
    try:
        absolute = urljoin(base_url, href.strip())
        parts = urlsplit(absolute)
        if parts.scheme not in {"http", "https"} or not parts.hostname:
            return None
        if parts.username is not None or parts.password is not None:
            return None
        if len(absolute) > _MAX_URL:
            return None
        return url_policy.normalize(absolute)
    except ValueError:
        return None


def _collapse(text: str | None) -> str:
    return " ".join((text or "").split())


def find_links(body: bytes, base_url: str) -> list[FoundLink]:
    """Every link and embed in ``body``, in document order, bounded."""
    out: list[FoundLink] = []
    for link in extract_links(body):
        url = resolve(base_url, link.href)
        if url is not None:
            out.append(FoundLink(url=url, how="link", text=link.accessible_name))
        if len(out) >= MAX_PER_PAGE:
            return out
    try:
        tree = HTMLParser(body)
    except Exception:
        return out
    for selector, attribute, how in _EMBEDS:
        for node in tree.css(selector):
            url = resolve(base_url, node.attributes.get(attribute) or "")
            if url is None:
                continue
            name = _collapse(node.attributes.get("aria-label")) or _collapse(
                node.attributes.get("title")
            )
            if not name and how == "object":
                # An object's content is its fallback, which is what a
                # screen reader reads when the object has no name.
                name = _collapse(node.text())
            out.append(FoundLink(url=url, how=how, text=name))
            if len(out) >= MAX_PER_PAGE:
                return out
    return out
