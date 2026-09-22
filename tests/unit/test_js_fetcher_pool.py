"""Authenticated JsFetcher tab-pool behavior."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

import pytest

from audit.crawler.js_fetcher import JsFetcher


@dataclass
class _Response:
    url: str
    status: int = 200
    headers: dict[str, str] = field(default_factory=lambda: {"content-type": "text/html"})


@dataclass
class _Page:
    goto_calls: list[str] = field(default_factory=list)
    closed: bool = False
    url: str = "about:blank"
    same_document: bool = False
    reload_status: int = 200
    reload_calls: int = 0

    async def goto(self, url: str, *, timeout: int, wait_until: str) -> _Response | None:
        assert timeout == 30_000
        assert wait_until == "load"
        self.goto_calls.append(url)
        self.url = url
        await asyncio.sleep(0)
        return None if self.same_document else _Response(url)

    async def reload(self, *, timeout: int, wait_until: str) -> _Response:
        assert timeout == 30_000
        assert wait_until == "load"
        self.reload_calls += 1
        return _Response(self.url, status=self.reload_status)

    async def wait_for_load_state(self, state: str, *, timeout: int) -> None:
        assert state == "networkidle"
        assert timeout == 10_000

    async def content(self) -> str:
        return "<html><head><title>pooled</title></head><body></body></html>"

    async def close(self) -> None:
        self.closed = True


@dataclass
class _Context:
    new_page_calls: int = 0

    async def new_page(self) -> _Page:
        self.new_page_calls += 1
        return _Page()


@pytest.mark.asyncio
async def test_shared_page_pool_reuses_prepared_tabs_without_opening_new_windows() -> None:
    context = _Context()
    pages = (_Page(), _Page())
    fetcher = JsFetcher(
        user_agent="test",
        shared_context=context,  # type: ignore[arg-type]
        shared_pages=pages,  # type: ignore[arg-type]
        private_context=True,
    )

    first, second = await asyncio.gather(
        fetcher.fetch("https://app.example.test/one"),
        fetcher.fetch("https://app.example.test/two"),
    )
    third = await fetcher.fetch("https://app.example.test/three")

    assert {first.url, second.url, third.url} == {
        "https://app.example.test/one",
        "https://app.example.test/two",
        "https://app.example.test/three",
    }
    assert context.new_page_calls == 0
    assert sum(len(page.goto_calls) for page in pages) == 3
    assert all(not page.closed for page in pages)
    assert not any(result.interaction_evaluated for result in (first, second, third))


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [200, 401, 404, 503])
async def test_same_document_route_uses_real_reload_status(status: int) -> None:
    page = _Page(same_document=True, reload_status=status)
    fetcher = JsFetcher(
        user_agent="test",
        shared_context=_Context(),  # type: ignore[arg-type]
        shared_pages=(page,),  # type: ignore[arg-type]
    )
    result = await fetcher.fetch("https://app.example.test/#/projects")
    assert result.status_code == status
    assert result.url.endswith("#/projects")
    assert page.reload_calls == 1
    assert not page.closed
