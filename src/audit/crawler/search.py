"""Explicit, bounded search journeys on a live (possibly signed-in) page."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Sequence
from contextlib import suppress
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal
from urllib.parse import urljoin, urlsplit

from playwright.async_api import TimeoutError as BrowserTimeout
from pydantic import BaseModel, ConfigDict, Field

from audit.analyzer.axe import AxeAnalyzer, AxeViolation, Level
from audit.analyzer.interaction import DEFAULT_BLOCKED_LABELS, RevealedViolation
from audit.crawler import url_policy

if TYPE_CHECKING:
    from playwright.async_api import Locator, Page, Route


class SearchTarget(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)
    by: Literal["label", "selector"] = "label"
    target: str = Field(min_length=1, max_length=300)


class SearchField(SearchTarget):
    value: str = Field(max_length=200)
    kind: Literal["text", "select"] = "text"


class SearchConfig(BaseModel):
    """No implicit form submission: the auditor supplies the journey and consent."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)
    confirmed: Literal[True]
    page_url: str = Field(default="", max_length=2048)
    fields: tuple[SearchField, ...] = Field(min_length=1, max_length=6)
    submit: SearchTarget | None = None
    results_selector: str = Field(default="a[href], [role=option]", min_length=1, max_length=300)
    next_button: SearchTarget | None = None
    max_result_pages: int = Field(default=3, ge=1, le=5)
    max_results: int = Field(default=20, ge=1, le=50)
    timeout_ms: int = Field(default=5000, ge=500, le=15000)


class SearchOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    status: Literal["completed", "limited", "no_results", "failed"] = "completed"
    states: int = Field(default=0, ge=0)
    discovered: int = Field(default=0, ge=0)
    detail: str = Field(default="", max_length=120)


@dataclass(frozen=True)
class SearchResult:
    outcome: SearchOutcome
    urls: tuple[str, ...] = ()
    findings: tuple[RevealedViolation, ...] = ()


async def rendered_links(page: Page, limit: int = 1000) -> tuple[str, ...]:
    """Read resolved hrefs, bounded before transfer out of the browser."""
    values = await page.locator("a[href]").evaluate_all(
        "(nodes, limit) => nodes.slice(0, limit).map(n => n.href).filter(u => u.length <= 2048)",
        limit,
    )
    return tuple(value for value in values if isinstance(value, str))


def search_target(target: SearchTarget, page: Page, *, button: bool = False) -> Locator:
    if target.by == "selector":
        return page.locator(target.target)
    if button:
        return page.get_by_role("button", name=target.target, exact=True)
    if isinstance(target, SearchField) and target.kind == "select":
        # A wrapping label's raw text contains its option labels. Resolve
        # the control's accessible name instead of matching that raw text.
        return page.get_by_role("combobox", name=target.target, exact=True)
    return page.get_by_label(target.target, exact=True)


def search_url_allowed(config: SearchConfig, seed_url: str, *, whole_host: bool) -> bool:
    """Validate configured entry before allocating a scan or opening a browser."""
    try:
        parts = urlsplit(config.page_url or seed_url)
        if parts.username or parts.password:
            return False
        return url_policy.is_in_scope(
            url_policy.normalize(config.page_url or seed_url),
            url_policy.build_scope(seed_url, whole_host=whole_host),
        ) and not url_policy.is_blocked(
            config.page_url or seed_url, url_policy.DEFAULT_BLOCKED_URL_PATTERNS
        )
    except ValueError:
        return False


class SearchExplorer:
    def __init__(
        self,
        config: SearchConfig,
        *,
        entry_url: str,
        can_visit: Callable[[str], bool],
        axe: AxeAnalyzer,
        level: Level = "AA",
    ) -> None:
        self.config = config
        self.entry_url = url_policy.normalize(config.page_url or entry_url)
        self.can_visit = can_visit
        self.axe = axe
        self.level = level

    async def run(self, page: Page, *, baseline: Sequence[AxeViolation]) -> SearchResult:
        urls: set[str] = set()
        findings: list[RevealedViolation] = []
        hashes = {finding.target_hash for finding in baseline}
        states = 0
        clicked = 0
        status: Literal["completed", "limited", "no_results", "failed"] = "completed"
        detail = ""

        async def guard(route: Route) -> None:
            request = route.request
            if (
                request.is_navigation_request()
                and request.frame == page.main_frame
                and not self.can_visit(request.url)
            ):
                await route.abort("blockedbyclient")
                return
            await route.fallback()

        def remember(url: str) -> None:
            nonlocal status, detail
            if len(urls) >= self.config.max_results:
                status, detail = "limited", "Configured search result limit reached."
            elif len(url) <= 2048 and self.can_visit(url):
                urls.add(url_policy.normalize(url))

        async def collect(*, links: bool = False) -> None:
            nonlocal states
            if not self.can_visit(page.url):
                raise ValueError("out_of_scope")
            states += 1
            if links:
                for url in await rendered_links(page):
                    remember(url)
            for finding in await self.axe.run(page, self.level):
                if finding.target_hash not in hashes:
                    hashes.add(finding.target_hash)
                    findings.append(RevealedViolation(finding, "Configured search"))

        await page.route("**/*", guard)
        try:
            async with asyncio.timeout(120):
                for result_page in range(self.config.max_result_pages):
                    await self._open_results(page, result_page, reset=True)
                    results = page.locator(self.config.results_selector)
                    try:
                        await results.first.wait_for(
                            state="visible", timeout=self.config.timeout_ms
                        )
                    except BrowserTimeout:
                        status, detail = (
                            "no_results",
                            "No results appeared before the search timeout.",
                        )
                        break
                    await collect()
                    # A live result list can be replaced by Vue after every
                    # navigation. Re-run the same query/pagination to reach
                    # each configured non-link result without exporting auth.
                    count = min(await results.count(), self.config.max_results - clicked)
                    for index in range(count):
                        result = page.locator(self.config.results_selector).nth(index)
                        href = await result.get_attribute("href", timeout=self.config.timeout_ms)
                        if href:
                            candidate = urljoin(page.url, href)
                            remember(candidate)
                            clicked += 1
                            continue
                        if not await self._can_click(result):
                            status, detail = (
                                "limited",
                                "Some configured result controls were skipped.",
                            )
                            continue
                        previous_url = url_policy.normalize(page.url)
                        await self._click_and_wait(page, result)
                        clicked += 1
                        if url_policy.normalize(page.url) != previous_url:
                            remember(page.url)
                        else:
                            await collect(links=True)
                        # Also replay DOM-only results: a detail panel may
                        # replace or reorder the remaining result controls.
                        await self._open_results(page, result_page, reset=True)
                        await page.locator(self.config.results_selector).first.wait_for(
                            state="visible", timeout=self.config.timeout_ms
                        )
                    if clicked >= self.config.max_results:
                        status, detail = "limited", "Configured search result limit reached."
                        break
                    if self.config.next_button is None:
                        break
                    next_button = search_target(self.config.next_button, page, button=True)
                    if await next_button.count() != 1 or not await next_button.is_enabled():
                        break
                    if result_page + 1 == self.config.max_result_pages:
                        status, detail = "limited", "Configured search pagination limit reached."
        except TimeoutError:
            status, detail = "limited", "Search time limit reached; retained discovered results."
        except Exception:
            # Browser exceptions can contain entered values or private URLs.
            status, detail = (
                "failed",
                "Search controls could not be used; check labels or selectors.",
            )
        finally:
            with suppress(Exception):
                await page.unroute("**/*", guard)
        return SearchResult(
            SearchOutcome(status=status, states=states, discovered=len(urls), detail=detail),
            tuple(sorted(urls)),
            tuple(findings),
        )

    async def _open_results(self, page: Page, result_page: int, *, reset: bool = False) -> None:
        if reset or url_policy.normalize(page.url) != self.entry_url:
            response = await page.goto(
                self.entry_url, wait_until="load", timeout=self.config.timeout_ms
            )
            if response is None:
                await page.reload(wait_until="load", timeout=self.config.timeout_ms)
        if not self.can_visit(page.url):
            raise ValueError("out_of_scope")
        for field in self.config.fields:
            locator = search_target(field, page)
            await locator.first.wait_for(state="visible", timeout=self.config.timeout_ms)
            if await locator.count() != 1:
                raise ValueError("ambiguous_field")
            kind = await locator.get_attribute("type")
            if (kind or "").lower() in {"password", "file", "hidden", "submit", "button"}:
                raise ValueError("unsafe_field")
            if field.kind == "select":
                await locator.select_option(label=field.value, timeout=self.config.timeout_ms)
            else:
                await locator.fill(field.value, timeout=self.config.timeout_ms)
        if self.config.submit:
            submit = search_target(self.config.submit, page, button=True)
            if await submit.count() != 1 or not await self._can_click(submit):
                raise ValueError("unsafe_submit")
            await submit.click(timeout=self.config.timeout_ms)
        for _ in range(result_page):
            await page.locator(self.config.results_selector).first.wait_for(
                state="visible", timeout=self.config.timeout_ms
            )
            if not self.config.next_button:
                break
            next_button = search_target(self.config.next_button, page, button=True)
            if not await self._can_click(next_button):
                raise ValueError("unsafe_pagination")
            await self._click_and_wait(page, next_button)

    async def _click_and_wait(self, page: Page, locator: Locator) -> None:
        before = await page.evaluate(_STATE_JS)
        await locator.click(timeout=self.config.timeout_ms)
        await page.wait_for_function(
            f"previous => ({_STATE_JS})() !== previous",
            arg=before,
            timeout=self.config.timeout_ms,
        )
        # Let deferred rendering/data requests finish after the first DOM or
        # URL change. Persistent connections must not stall the whole search.
        with suppress(BrowserTimeout):
            await page.wait_for_load_state("networkidle", timeout=self.config.timeout_ms)

    @staticmethod
    async def _can_click(locator: Locator) -> bool:
        label = (await locator.get_attribute("aria-label") or await locator.inner_text()).lower()
        return bool(label.strip()) and not any(word in label for word in DEFAULT_BLOCKED_LABELS)


_STATE_JS = """() => {
    const text = (document.body?.innerHTML || '').slice(0, 200000);
    let hash = 0;
    for (let i = 0; i < text.length; i++) hash = ((hash << 5) - hash + text.charCodeAt(i)) | 0;
    return location.href + ':' + hash;
}"""
