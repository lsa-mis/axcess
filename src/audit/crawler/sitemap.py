"""Sitemap discovery and XML parsing.

Handles both ``urlset`` and ``sitemapindex`` documents. ``discover_sitemaps``
unions robots-declared sitemaps with conventional ``/sitemap.xml`` and
``/sitemap_index.xml`` locations, plus ``sitemap.xml`` inside the scan's
folder when the scan is limited to one. Parsing uses ``defusedxml`` to block
XXE and billion-laughs attacks.

``read_site_sitemaps`` is what a crawl calls: it reads only sitemaps on the
scanned host (a robots.txt may name one anywhere, and the crawler must not
fetch arbitrary addresses on a site's say-so), and it stops at a fixed number
of files and addresses so a huge or looping sitemap cannot stall a scan.
Gzipped sitemap files (``.xml.gz``) are not read.
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
# Bounds for one crawl. 50,000 is the sitemap protocol's own per-file limit,
# far above the default page limit, so no real site is cut short by it.
MAX_SITEMAP_URLS = 50_000
MAX_SITEMAP_FILES = 50


async def urls_from_sitemap(
    client: httpx.AsyncClient,
    sitemap_url: str,
    *,
    depth: int = 0,
    same_host_only: bool = False,
    _files: list[str] | None = None,
) -> list[str]:
    """Fetch ``sitemap_url`` and return all ``<loc>`` URLs, recursing into indexes.

    Returns an empty list on fetch failure or malformed XML. Recursion stops at
    ``_MAX_DEPTH`` to bound work on pathological sitemap graphs, and after
    ``MAX_SITEMAP_FILES`` files. With ``same_host_only`` an index's children on
    another host are skipped.
    """
    files = _files if _files is not None else []
    if depth > _MAX_DEPTH or len(files) >= MAX_SITEMAP_FILES:
        return []
    files.append(sitemap_url)
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
            if not loc:
                continue
            if same_host_only and not _same_host(loc, sitemap_url):
                log.info("sitemap.child_other_host", url=loc)
                continue
            urls.extend(
                await urls_from_sitemap(
                    client,
                    loc,
                    depth=depth + 1,
                    same_host_only=same_host_only,
                    _files=files,
                )
            )
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


def _same_host(url: str, other: str) -> bool:
    a, b = urlsplit(url), urlsplit(other)
    return (
        a.scheme in ("http", "https") and (a.hostname or "").lower() == (b.hostname or "").lower()
    )


def discover_sitemaps(
    seed_url: str, robots_declared: list[str], *, path_prefix: str = "/"
) -> list[str]:
    """Union of robots-declared sitemaps with conventional locations, deduped.

    ``path_prefix`` is the scan's folder (``/docs/``). When it is not the
    whole host, ``/docs/sitemap.xml`` is tried too: a section of a large site
    often publishes its own.
    """
    parts = urlsplit(seed_url)
    base = f"{parts.scheme}://{parts.netloc}/"
    candidates = list(robots_declared)
    for name in ("sitemap.xml", "sitemap_index.xml"):
        candidates.append(urljoin(base, name))
    if path_prefix not in ("", "/"):
        candidates.append(urljoin(base, path_prefix.lstrip("/") + "sitemap.xml"))
    seen: set[str] = set()
    out: list[str] = []
    for url in candidates:
        if url not in seen:
            seen.add(url)
            out.append(url)
    return out


async def read_site_sitemaps(
    client: httpx.AsyncClient,
    seed_url: str,
    robots_declared: list[str],
    *,
    path_prefix: str = "/",
    max_urls: int = MAX_SITEMAP_URLS,
) -> list[str]:
    """Every address the site's sitemaps list, in the order they list them.

    Reads robots-declared and conventional sitemaps on the seed's host only,
    deduplicated, and stops after ``max_urls`` addresses. The caller scopes,
    normalizes and filters what comes back.
    """
    files: list[str] = []
    seen: set[str] = set()
    out: list[str] = []
    for sitemap_url in discover_sitemaps(seed_url, robots_declared, path_prefix=path_prefix):
        if not _same_host(sitemap_url, seed_url):
            log.info("sitemap.other_host_skipped", url=sitemap_url)
            continue
        if sitemap_url in files:
            continue
        for url in await urls_from_sitemap(client, sitemap_url, same_host_only=True, _files=files):
            if url in seen:
                continue
            seen.add(url)
            out.append(url)
            if len(out) >= max_urls:
                log.warning("sitemap.url_cap_reached", cap=max_urls)
                return out
    return out
