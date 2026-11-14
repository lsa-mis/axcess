"""Record a crawl's linked files as it runs, and check each PDF as it is found.

One :class:`LinkedFileTracker` per crawl. The orchestrator calls it at three
points, and nothing else in the crawl changes:

``record_page``
    For every HTML page that loaded: each link, frame, object and embed in
    its saved HTML, plus the links the interaction probe saw appear after a
    click. An address that names a file by itself (``formats.classify_url``)
    is recorded with the page as a reference.
``record_response``
    For every address the crawler itself fetched: if the server answered
    with a file's Content-Type, the address is a linked file even though
    nothing in it said so. The pages that linked to it earlier were held in
    memory (``_candidates``) and become its references now. If it is a PDF
    the crawler fetched without a browser, the PDF is checked from that same
    response, so the site is not asked for it twice.
``check_page``
    Right after ``record_page``, as part of the same page: every PDF that
    page reaches and the crawl will not fetch itself is downloaded once and
    checked: a PDF on another host (Google Drive, Box, a partner's site),
    which the crawl never visits, and one shown in a frame, object or embed,
    which the crawl does not follow. A PDF linked from many pages is
    downloaded with the first of them; the others find it checked. A PDF in
    the crawl's scope that some page links to by an ordinary link is left
    to the crawl, which fetches it as it fetches a page and checks it from
    that response (``record_response``): checking it here too would ask the
    site for it twice. (If a page found later links by an ordinary link to
    a PDF already checked from a frame, the crawl still fetches it: one
    extra request, in that case only.) One file per address, robots.txt and the crawl's rate limit
    honoured, links from the file never followed.
``check_pending``
    After the last page: anything still waiting, such as a PDF in scope
    past the page or depth limit, which the crawl never reached.

PDFs on other hosts are checked with the page, not at the end, since
2026-11-14 (the developer's choice): a scan stopped part way then keeps
their results for the pages it reached, as it already kept the results of
the in-scope PDFs it had fetched. The same files are downloaded either way,
each once, under the same limits.

The held references are in memory only. A crawl stopped and resumed keeps
every file and reference already written, but loses the not-yet-matched
references of pages fetched before the stop, so a file found by
Content-Type after a resume can list fewer pages than link to it.
"""

from __future__ import annotations

import asyncio
import functools
import hashlib
import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

import httpx

from audit.crawler import url_policy
from audit.db import linked_files as store
from audit.db.schema import write_batch
from audit.linked_files import formats
from audit.linked_files.discovery import FoundLink, find_links, resolve
from audit.linked_files.fetch import MAX_FILE_BYTES, FetchedFile, fetch_file
from audit.linked_files.pdf_check import PdfCheck, check_pdf, looks_like_pdf
from audit.logging import get_logger

if TYPE_CHECKING:
    from audit.analyzer.interaction.base import RevealedLink
    from audit.crawler.rate_limit import HostLimiter
    from audit.crawler.robots import RobotsChecker
    from audit.crawler.url_policy import HostScope

log = get_logger(__name__)


@dataclass(frozen=True)
class _Downloads:
    """How the tracker downloads a PDF: the crawl's client, limits and rules."""

    client: httpx.AsyncClient
    limiter: HostLimiter
    robots: RobotsChecker
    ignore_robots: bool
    blocked_url_patterns: tuple[str, ...]
    excluded_scopes: tuple[str, ...]

#: PDFs downloaded by ``check_pending`` per scan. The ones the crawler
#: fetched itself are checked from its response and do not count.
MAX_DOWNLOADS = 200
#: Downloads at once. Each host is still limited by the crawl's own limiter.
DOWNLOAD_CONCURRENCY = 4
#: Longest the checks may take on one PDF. pypdf is pure Python, so a hostile
#: file can be slow; past this the file is "timed out" and the crawl moves on.
CHECK_TIMEOUT_S = 20.0
#: References held in memory while waiting to learn whether an address is a
#: file (see the module docstring), across the whole crawl.
MAX_HELD_REFS = 100_000


class LinkedFileTracker:
    def __init__(
        self,
        conn: sqlite3.Connection,
        *,
        scan_id: int,
        scope: HostScope,
        allow_subdomains: bool,
    ) -> None:
        self._conn = conn
        self._scan_id = scan_id
        self._scope = scope
        self._site = replace(scope, path_prefix="/")
        self._allow_subdomains = allow_subdomains
        self._by_content_type = store.content_type_files(conn, scan_id)
        self._candidates: dict[str, list[tuple[int, FoundLink]]] = {}
        self._held = 0
        self.full = False
        self._downloads: _Downloads | None = None
        # Shared by check_page and check_pending: the download cap counts
        # across the whole scan, and a file being checked for one page is
        # awaited, not downloaded again, by another.
        self._started = 0
        self._semaphore = asyncio.Semaphore(DOWNLOAD_CONCURRENCY)
        self._in_flight: dict[int, asyncio.Task[None]] = {}

    def attach_downloads(
        self,
        *,
        client: httpx.AsyncClient,
        limiter: HostLimiter,
        robots: RobotsChecker,
        ignore_robots: bool,
        blocked_url_patterns: Sequence[str],
        excluded_scopes: Sequence[str],
    ) -> None:
        """What ``check_page`` downloads with: the crawl's own client and limits."""
        self._downloads = _Downloads(
            client=client,
            limiter=limiter,
            robots=robots,
            ignore_robots=ignore_robots,
            blocked_url_patterns=tuple(blocked_url_patterns),
            excluded_scopes=tuple(excluded_scopes),
        )

    # -- while the crawl runs ---------------------------------------------

    def record_page(
        self,
        *,
        page_id: int,
        base_url: str,
        body: bytes,
        revealed: Sequence[RevealedLink] = (),
    ) -> None:
        """Record every file this page reaches. Never raises into the crawl."""
        try:
            found = find_links(body, base_url)
            in_html = {link.url for link in found}
            for item in revealed:
                url = resolve(base_url, item.url)
                # A link already in the saved page is an ordinary link; the
                # click only showed something that was there all along.
                if url is None or url in in_html:
                    continue
                found.append(
                    FoundLink(
                        url=url, how="revealed_link", text=item.name, revealed_by=item.revealed_by
                    )
                )
            with write_batch(self._conn):
                for link in found:
                    self._record_link(page_id, link)
        except (sqlite3.Error, ValueError) as exc:
            log.warning("linked_files.page_failed", page_id=page_id, error_type=type(exc).__name__)

    def _record_link(self, page_id: int, link: FoundLink) -> None:
        file_type = formats.classify_url(link.url)
        if file_type is not None:
            file_id = self._upsert(link.url, file_type, formats.found_by_for_url(link.url))
        else:
            file_id = self._by_content_type.get(link.url)
            if file_id is None:
                self._hold(page_id, link)
                return
        if file_id is not None:
            self._add_ref(file_id, page_id, link)

    def _hold(self, page_id: int, link: FoundLink) -> None:
        # Only addresses the crawler may fetch can turn out to be files by
        # Content-Type; anything else would wait here for nothing.
        if not url_policy.is_in_scope(
            link.url, self._scope, allow_subdomains=self._allow_subdomains
        ):
            return
        if self._held >= MAX_HELD_REFS:
            return
        self._candidates.setdefault(link.url, []).append((page_id, link))
        self._held += 1

    def _upsert(
        self, url: str, file_type: formats.FileType, found_by: formats.FoundBy
    ) -> int | None:
        off_site = not url_policy.is_in_scope(
            url, self._site, allow_subdomains=self._allow_subdomains
        )
        file_id = store.upsert_file(
            self._conn,
            scan_id=self._scan_id,
            url=url,
            file_type=file_type,
            found_by=found_by,
            off_site=off_site,
        )
        if file_id is None and not self.full:
            self.full = True
            log.warning("linked_files.limit_reached", limit=store.MAX_FILES_PER_SCAN)
        return file_id

    def _add_ref(self, file_id: int, page_id: int, link: FoundLink) -> None:
        store.add_ref(
            self._conn,
            scan_id=self._scan_id,
            file_id=file_id,
            page_id=page_id,
            how=link.how,
            link_text=link.text,
            revealed_by=link.revealed_by,
        )

    async def record_response(
        self,
        *,
        url: str,
        status_code: int,
        content_type: str,
        body: bytes,
        complete: bool,
    ) -> None:
        """The crawler fetched ``url`` itself; record it if it is a file.

        ``complete`` says ``body`` is the server's own bytes, whole: a
        response fetched without a browser and not cut at the crawler's body
        limit. Only then is a PDF checked from it; otherwise it waits for
        ``check_pending`` to download it.
        """
        try:
            by_url = formats.classify_url(url)
            by_type = formats.classify_content_type(content_type)
            file_type = by_url or by_type
            if file_type is None:
                return
            found_by = formats.found_by_for_url(url) if by_url else "content_type"
            with write_batch(self._conn):
                file_id = self._upsert(url, file_type, found_by)
                if file_id is None:
                    return
                if found_by == "content_type":
                    self._by_content_type[url] = file_id
                    for page_id, link in self._candidates.pop(url, []):
                        self._held -= 1
                        self._add_ref(file_id, page_id, link)
            if store.file_status(self._conn, scan_id=self._scan_id, file_id=file_id) != "pending":
                return
            if status_code >= 400:
                self._store(
                    file_id,
                    store.CheckResult(
                        "could_not_check",
                        "http_error",
                        http_status=status_code,
                        content_type=content_type,
                    ),
                )
                return
            if not complete:
                return
            # The crawler's fetcher cuts a body at the same limit, so a body
            # that reached it was cut: the file is too large to check.
            if len(body) >= MAX_FILE_BYTES:
                fetched = FetchedFile("too_large", status_code, content_type)
            else:
                fetched = FetchedFile("ok", status_code, content_type, body)
            await self._check_fetched(file_id, fetched)
        except (sqlite3.Error, ValueError) as exc:
            log.warning("linked_files.response_failed", error_type=type(exc).__name__)

    # -- after the last page ----------------------------------------------

    async def check_page(self, page_id: int) -> None:
        """Download and check the PDFs on other hosts ``page_id`` links to, not checked yet.

        Part of the page: the progress page's "Document check" is done when
        this returns. A PDF inside the crawl's scope is left to the crawl
        (see the module docstring). Bounded and never raises; does nothing
        before ``attach_downloads``.
        """
        if self._downloads is None:
            return
        try:
            pending = [
                (file_id, url)
                for file_id, url, linked in store.pending_files_for_page(
                    self._conn, self._scan_id, page_id
                )
                if not (
                    linked
                    and url_policy.is_in_scope(
                        url, self._scope, allow_subdomains=self._allow_subdomains
                    )
                )
            ]
        except sqlite3.Error as exc:
            log.warning("linked_files.page_check_failed", error_type=type(exc).__name__)
            return
        await self._check_all(pending, self._downloads)

    async def check_pending(
        self,
        *,
        client: httpx.AsyncClient,
        limiter: HostLimiter,
        robots: RobotsChecker,
        ignore_robots: bool,
        blocked_url_patterns: Sequence[str],
        excluded_scopes: Sequence[str],
    ) -> None:
        """Download and check every PDF still waiting. Bounded; never raises."""
        downloads = self._downloads or _Downloads(
            client=client,
            limiter=limiter,
            robots=robots,
            ignore_robots=ignore_robots,
            blocked_url_patterns=tuple(blocked_url_patterns),
            excluded_scopes=tuple(excluded_scopes),
        )
        pending = store.pending_files(self._conn, self._scan_id)
        if pending:
            log.info("linked_files.checking", files=len(pending))
        try:
            await self._check_all(pending, downloads)
        finally:
            # A stop or a fault leaves nothing silently pending: the report
            # says the scan stopped before the file was checked.
            store.mark_unchecked(self._conn, self._scan_id)

    async def _check_all(self, pending: Sequence[tuple[int, str]], downloads: _Downloads) -> None:
        tasks: list[asyncio.Task[None]] = []
        for file_id, url in pending:
            task = self._in_flight.get(file_id)
            if task is None:
                task = asyncio.ensure_future(self._check_one(file_id, url, downloads))
                self._in_flight[file_id] = task
                task.add_done_callback(functools.partial(self._done, file_id))
            tasks.append(task)
        if not tasks:
            return
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for result in results:
            if isinstance(result, asyncio.CancelledError):
                raise result
            if isinstance(result, (sqlite3.Error, ValueError)):
                log.warning("linked_files.check_failed", error_type=type(result).__name__)

    def _done(self, file_id: int, _task: asyncio.Task[None]) -> None:
        self._in_flight.pop(file_id, None)

    async def _check_one(self, file_id: int, url: str, downloads: _Downloads) -> None:
        if self._started >= MAX_DOWNLOADS:
            self._store(file_id, store.CheckResult("could_not_check", "limit"))
            return
        if url_policy.is_blocked(url, downloads.blocked_url_patterns) or url_policy.is_excluded(
            url, downloads.excluded_scopes
        ):
            self._store(file_id, store.CheckResult("could_not_check", "blocked"))
            return
        self._started += 1
        async with self._semaphore:
            if not downloads.ignore_robots and not await downloads.robots.allowed(url):
                self._store(file_id, store.CheckResult("could_not_check", "robots"))
                return
            async with downloads.limiter.throttle(url):
                fetched = await fetch_file(downloads.client, url)
            await self._check_fetched(file_id, fetched)

    # -- shared -----------------------------------------------------------

    async def _check_fetched(self, file_id: int, fetched: FetchedFile) -> None:
        if fetched.outcome != "ok":
            self._store(
                file_id,
                store.CheckResult(
                    "could_not_check",
                    _FETCH_REASON[fetched.outcome],
                    http_status=fetched.http_status,
                    content_type=fetched.content_type,
                ),
            )
            return
        body = fetched.body
        downloaded = store.CheckResult(
            "could_not_check",
            "not_a_pdf",
            http_status=fetched.http_status,
            content_type=fetched.content_type,
            byte_size=len(body),
            sha256=hashlib.sha256(body).hexdigest(),
        )
        if not looks_like_pdf(body):
            self._store(file_id, downloaded)
            return
        try:
            result: PdfCheck = await asyncio.wait_for(
                asyncio.to_thread(check_pdf, body), timeout=CHECK_TIMEOUT_S
            )
        except TimeoutError:
            self._store(file_id, replace(downloaded, reason="timed_out"))
            return
        if result.outcome == "checked":
            self._store(
                file_id,
                replace(
                    downloaded,
                    status="mostly_sure" if result.failed else "not_sure",
                    reason=None,
                    failed_checks=result.failed,
                    is_form=result.is_form,
                    page_count=result.page_count,
                ),
            )
            return
        self._store(file_id, replace(downloaded, reason=_CHECK_REASON[result.outcome]))

    def _store(self, file_id: int, result: store.CheckResult) -> None:
        store.set_result(self._conn, scan_id=self._scan_id, file_id=file_id, result=result)


_FETCH_REASON: dict[str, formats.Reason] = {
    "http_error": "http_error",
    "broken_link": "broken_link",
    "too_large": "too_large",
    "timed_out": "timed_out",
}
_CHECK_REASON: dict[str, formats.Reason] = {
    "password": "password",
    "not_a_pdf": "not_a_pdf",
    "damaged": "damaged",
}
