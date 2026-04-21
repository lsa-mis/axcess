"""Sitemap discovery and XML parsing.

Handles both ``urlset`` and ``sitemapindex`` documents. ``discover_sitemaps``
unions robots-declared sitemaps with conventional ``/sitemap.xml`` and
``/sitemap_index.xml`` locations. Parsing uses ``defusedxml`` to block XXE and
billion-laughs attacks.
"""

from __future__ import annotations

from urllib.parse import urljoin, urlsplit
from xml.etree.ElementTree import Element

import httpx
from defusedxml import ElementTree as defused_et  # noqa: N813

from audit.logging import get_logger

log = get_logger(__name__)

SITEMAP_NS = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
_MAX_DEPTH = 3


async def urls_from_sitemap(
    client: httpx.AsyncClient,
    sitemap_url: str,
    *,
    depth: int = 0,
) -> list[str]:
    """Fetch ``sitemap_url`` and return all ``<loc>`` URLs, recursing into indexes.

    Returns an empty list on fetch failure or malformed XML. Recursion stops at
    ``_MAX_DEPTH`` to bound work on pathological sitemap graphs.
    """
    if depth > _MAX_DEPTH:
        return []
    try:
        resp = await client.get(sitemap_url, follow_redirects=True)
    except httpx.HTTPError as exc:
        log.warning("sitemap.fetch_failed", url=sitemap_url, error=str(exc))
        return []
    if resp.status_code != 200 or not resp.content:
        return []
    try:
        root = defused_et.fromstring(resp.content)
    except (defused_et.ParseError, ValueError) as exc:
        log.warning("sitemap.parse_failed", url=sitemap_url, error=str(exc))
        return []

    tag = _localname(root.tag)
    if tag == "sitemapindex":
        urls: list[str] = []
        for child in root.findall(f"{SITEMAP_NS}sitemap"):
            loc = _loc_text(child)
            if loc:
                urls.extend(await urls_from_sitemap(client, loc, depth=depth + 1))
        return urls
    if tag == "urlset":
        return [loc for child in root.findall(f"{SITEMAP_NS}url") if (loc := _loc_text(child))]
    return []


def _localname(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _loc_text(elem: Element) -> str | None:
    node = elem.find(f"{SITEMAP_NS}loc")
    if node is None or node.text is None:
        return None
    text = node.text.strip()
    return text or None


def discover_sitemaps(seed_url: str, robots_declared: list[str]) -> list[str]:
    """Union of robots-declared sitemaps with conventional locations, deduped."""
    parts = urlsplit(seed_url)
    base = f"{parts.scheme}://{parts.netloc}/"
    candidates = list(robots_declared)
    for name in ("sitemap.xml", "sitemap_index.xml"):
        candidates.append(urljoin(base, name))
    seen: set[str] = set()
    out: list[str] = []
    for url in candidates:
        if url not in seen:
            seen.add(url)
            out.append(url)
    return out
