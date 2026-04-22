"""Top-level crawl orchestration.

Seed URL → queue → workers → fetch → record page → enqueue in-scope links.
Resumability comes from the SQLite-backed queue: an interrupted crawl leaves
pending jobs behind, and a re-run under the same seed URL reuses the scan row
and drains what's left.

Phase 1 only records pages; image extraction arrives in Phase 2.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import sqlite3
from dataclasses import dataclass, field
from urllib.parse import urljoin

import httpx
from selectolax.parser import HTMLParser

from audit.analyzer.ocr.pool import OcrPool
from audit.analyzer.vlm.base import VlmProvider
from audit.analyzer.vlm.ollama import OllamaProvider
from audit.blob_store import BlobStore
from audit.config import get_settings
from audit.crawler import url_policy
from audit.crawler.fetcher import FetchError, FetchResult, StaticFetcher
from audit.crawler.js_fetcher import JsFetcher
from audit.crawler.rate_limit import HostLimiter
from audit.crawler.render_detect import is_js_only
from audit.crawler.robots import RobotsChecker
from audit.crawler.url_policy import HostScope
from audit.db import queue, repo
from audit.extractor.downloader import ImageDownloader
from audit.extractor.pipeline import OcrConfig, VlmConfig, process_page
from audit.logging import get_logger
from audit.synthesizer.findings import synthesize_findings

log = get_logger(__name__)

JOB_KIND = "fetch"


@dataclass(frozen=True)
class CrawlConfig:
    seed_url: str
    max_pages: int = 500
    max_depth: int = 10
    allow_subdomains: bool = False
    rps: float = 2.0
    ignore_robots: bool = False
    concurrency_per_host: int = 2
    workers: int = 4
    user_agent: str = "imagetextscanner/0.1 (+local accessibility audit)"
    request_timeout_s: float = 30.0
    # OCR — disable with ``ocr_enabled=False`` or by passing ``--skip-ocr`` on the CLI.
    ocr_enabled: bool = True
    ocr_language: str = "eng"
    ocr_max_workers: int = 2
    ocr_min_confidence: float = 60.0
    ocr_min_word_count: int = 3
    # VLM — disabled unless Ollama is reachable and the model is loaded.
    vlm_enabled: bool = True
    vlm_model: str = "qwen2-vl:2b"
    vlm_base_url: str = "http://localhost:11434"
    vlm_prompt_name: str = "classify_v1.txt"
    vlm_concurrency: int = 1
    # Synthesis — toggle off with ``--skip-synthesize`` if the caller wants
    # to run ``audit synthesize`` manually against the same scan later.
    synthesize_enabled: bool = True


@dataclass
class CrawlSummary:
    scan_id: int
    seed_url: str
    pages_fetched: int = 0
    pages_skipped_robots: int = 0
    errors: int = 0
    images_persisted: int = 0
    svg_text_hits: int = 0
    image_errors: int = 0
    ocr_analyzed: int = 0
    ocr_text_candidates: int = 0
    vlm_classified: int = 0
    vlm_errors: int = 0
    findings_written: int = 0
    findings_by_severity: dict[str, int] = field(
        default_factory=lambda: {"critical": 0, "major": 0, "minor": 0, "info": 0}
    )
    status: str = "running"
    # Human-readable status reasons collected during the crawl.
    notes: list[str] = field(default_factory=list)


async def run_crawl(
    conn: sqlite3.Connection,
    config: CrawlConfig,
    *,
    http_client: httpx.AsyncClient | None = None,
    js_fetcher: JsFetcher | None = None,
    vlm_provider: VlmProvider | None = None,
) -> CrawlSummary:
    """Execute (or resume) a crawl for ``config.seed_url``."""
    normalized_seed = url_policy.normalize(config.seed_url)
    scope = url_policy.build_scope(normalized_seed)

    scan_id = _ensure_scan(conn, normalized_seed, config)
    queue.reclaim_expired(conn)
    _seed_queue(conn, scan_id, normalized_seed)

    summary = CrawlSummary(scan_id=scan_id, seed_url=normalized_seed)
    limiter = HostLimiter(rps=config.rps, concurrency_per_host=config.concurrency_per_host)

    owned_client = http_client is None
    client = http_client or _default_client(config)
    robots = RobotsChecker(client, user_agent=config.user_agent)
    fetcher = StaticFetcher(client)
    blob_store = BlobStore(get_settings().blob_dir)
    downloader = ImageDownloader(client, blob_store)
    ocr_pool: OcrPool | None = None
    ocr_config: OcrConfig | None = None
    if config.ocr_enabled:
        ocr_pool = OcrPool(lang=config.ocr_language, max_workers=config.ocr_max_workers)
        ocr_config = OcrConfig(
            pool=ocr_pool,
            blob_store=blob_store,
            min_confidence=config.ocr_min_confidence,
            min_word_count=config.ocr_min_word_count,
        )
    vlm_config = await _build_vlm(config, client, vlm_provider)
    ctx = _WorkerContext(
        conn=conn,
        config=config,
        scope=scope,
        scan_id=scan_id,
        limiter=limiter,
        robots=robots,
        static=fetcher,
        js=js_fetcher,
        downloader=downloader,
        ocr=ocr_config,
        vlm=vlm_config,
        in_flight=0,
        summary=summary,
    )

    interrupted = False
    try:
        try:
            async with asyncio.TaskGroup() as tg:
                for _ in range(config.workers):
                    tg.create_task(_worker(ctx))
        except* asyncio.CancelledError:
            interrupted = True
    except asyncio.CancelledError:
        interrupted = True
        raise
    finally:
        if interrupted:
            summary.status = "interrupted"
            summary.notes.append("crawl interrupted")
        elif summary.status == "running":
            summary.status = "completed"
        if (
            summary.status == "completed"
            and config.synthesize_enabled
            and summary.pages_fetched > 0
        ):
            try:
                synth = synthesize_findings(conn, scan_id=scan_id)
                summary.findings_written = synth.findings_written
                summary.findings_by_severity = synth.by_severity
            except Exception as exc:
                log.warning("synthesize.failed", scan_id=scan_id, error=str(exc))
        _finalize_scan(conn, scan_id, summary)
        if ocr_pool is not None:
            ocr_pool.shutdown()
        if owned_client:
            with contextlib.suppress(Exception):
                await client.aclose()

    return summary


def _default_client(config: CrawlConfig) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=config.request_timeout_s,
        headers={"User-Agent": config.user_agent},
        http2=True,
        max_redirects=10,
    )


def _ensure_scan(conn: sqlite3.Connection, seed_url: str, config: CrawlConfig) -> int:
    """Create (or resume) a scan row for ``seed_url``. Returns its id."""
    row = conn.execute(
        """
        SELECT id FROM scans
         WHERE seed_url = ? AND status IN ('running', 'interrupted')
         ORDER BY id DESC
         LIMIT 1
        """,
        (seed_url,),
    ).fetchone()
    if row is not None:
        scan_id = int(row["id"])
        conn.execute(
            "UPDATE scans SET status = 'running' WHERE id = ?",
            (scan_id,),
        )
        return scan_id

    cur = conn.execute(
        """
        INSERT INTO scans (seed_url, status, config_json)
        VALUES (?, 'running', ?)
        """,
        (seed_url, _config_json(config)),
    )
    return int(cur.lastrowid or 0)


def _config_json(config: CrawlConfig) -> str:
    return json.dumps(
        {
            "max_pages": config.max_pages,
            "max_depth": config.max_depth,
            "allow_subdomains": config.allow_subdomains,
            "rps": config.rps,
            "ignore_robots": config.ignore_robots,
            "concurrency_per_host": config.concurrency_per_host,
            "user_agent": config.user_agent,
        },
        sort_keys=True,
    )


def _seed_queue(conn: sqlite3.Connection, scan_id: int, seed_url: str) -> None:
    queue.enqueue(
        conn,
        JOB_KIND,
        {"url": seed_url, "depth": 0, "scan_id": scan_id},
        dedupe_key=_dedupe_key(scan_id, seed_url),
    )


def _dedupe_key(scan_id: int, url: str) -> str:
    return f"{JOB_KIND}:{scan_id}:{url}"


@dataclass
class _WorkerContext:
    conn: sqlite3.Connection
    config: CrawlConfig
    scope: HostScope
    scan_id: int
    limiter: HostLimiter
    robots: RobotsChecker
    static: StaticFetcher
    js: JsFetcher | None
    downloader: ImageDownloader
    ocr: OcrConfig | None
    vlm: VlmConfig | None
    in_flight: int
    summary: CrawlSummary


async def _build_vlm(
    config: CrawlConfig,
    client: httpx.AsyncClient,
    provider: VlmProvider | None,
) -> VlmConfig | None:
    """Resolve a :class:`VlmConfig` or log a reason for skipping."""
    if not config.vlm_enabled:
        return None
    if provider is not None:
        return VlmConfig(provider=provider)
    ollama = OllamaProvider(
        client,
        model=config.vlm_model,
        base_url=config.vlm_base_url,
        prompt_name=config.vlm_prompt_name,
        concurrency=config.vlm_concurrency,
    )
    if not await ollama.healthy():
        log.warning(
            "vlm.unavailable",
            model=config.vlm_model,
            base_url=config.vlm_base_url,
            hint="Ollama daemon not running or model not pulled; continuing without VLM.",
        )
        return None
    return VlmConfig(provider=ollama)


async def _worker(ctx: _WorkerContext) -> None:
    """Lease and process jobs until both queue and peers are idle."""
    while True:
        if _page_limit_reached(ctx):
            return
        job = queue.lease(ctx.conn, JOB_KIND, lease_secs=120)
        if job is None:
            if ctx.in_flight == 0 and queue.pending_count(ctx.conn, JOB_KIND) == 0:
                return
            await asyncio.sleep(0.05)
            continue
        ctx.in_flight += 1
        try:
            await _process_job(ctx, job)
            queue.complete(ctx.conn, job.id)
        except Exception as exc:  # record and move on
            log.warning("crawl.job_failed", id=job.id, error=str(exc))
            queue.fail(ctx.conn, job.id, str(exc))
            ctx.summary.errors += 1
        finally:
            ctx.in_flight -= 1


def _page_limit_reached(ctx: _WorkerContext) -> bool:
    return ctx.summary.pages_fetched >= ctx.config.max_pages


async def _process_job(ctx: _WorkerContext, job: queue.Job) -> None:
    url: str = job.payload["url"]
    depth: int = int(job.payload["depth"])

    if not ctx.config.ignore_robots and not await ctx.robots.allowed(url):
        ctx.summary.pages_skipped_robots += 1
        return

    async with ctx.limiter.throttle(url):
        try:
            result = await ctx.static.fetch(url)
        except FetchError as exc:
            log.warning("crawl.fetch_failed", url=url, error=str(exc))
            ctx.summary.errors += 1
            _record_page(ctx, url, status_code=None, result=None, render_mode="static")
            return

    render_mode = "static"
    if result.is_html and result.is_ok and ctx.js is not None and is_js_only(result.body):
        try:
            result = await ctx.js.fetch(url)
            render_mode = "js"
        except FetchError as exc:
            log.warning("crawl.js_fetch_failed", url=url, error=str(exc))

    page_id = _record_page(
        ctx, url, status_code=result.status_code, result=result, render_mode=render_mode
    )
    ctx.summary.pages_fetched += 1

    if result.is_html and result.is_ok and page_id is not None:
        extraction = await process_page(
            ctx.conn,
            page_id=page_id,
            scan_id=ctx.scan_id,
            page_url=result.url,
            body=result.body,
            downloader=ctx.downloader,
            ocr=ctx.ocr,
            vlm=ctx.vlm,
        )
        ctx.summary.images_persisted += extraction.images_persisted
        ctx.summary.svg_text_hits += extraction.svg_text_hits
        ctx.summary.image_errors += extraction.errors
        ctx.summary.ocr_analyzed += extraction.ocr_analyzed
        ctx.summary.ocr_text_candidates += extraction.ocr_text_candidates
        ctx.summary.vlm_classified += extraction.vlm_classified
        ctx.summary.vlm_errors += extraction.vlm_errors

    if not result.is_html or not result.is_ok:
        return
    if depth >= ctx.config.max_depth:
        return
    if _page_limit_reached(ctx):
        return
    _enqueue_children(ctx, base_url=result.url, body=result.body, depth=depth + 1)


def _record_page(
    ctx: _WorkerContext,
    url: str,
    *,
    status_code: int | None,
    result: FetchResult | None,
    render_mode: str,
) -> int | None:
    title = _extract_title(result.body) if result and result.is_html else None
    html_hash = hashlib.sha256(result.body).hexdigest() if result and result.body else None
    return repo.upsert_page(
        ctx.conn,
        scan_id=ctx.scan_id,
        url_normalized=url,
        status_code=status_code,
        title=title,
        render_mode=render_mode,
        html_hash=html_hash,
    )


def _extract_title(body: bytes) -> str | None:
    try:
        tree = HTMLParser(body)
    except Exception:  # selectolax can raise on exotic inputs
        return None
    node = tree.css_first("title")
    if node is None:
        return None
    text = (node.text() or "").strip()
    return text or None


def _enqueue_children(
    ctx: _WorkerContext,
    *,
    base_url: str,
    body: bytes,
    depth: int,
) -> None:
    try:
        tree = HTMLParser(body)
    except Exception:
        return
    seen: set[str] = set()
    for anchor in tree.css("a[href]"):
        href = anchor.attributes.get("href")
        if not href:
            continue
        try:
            absolute = urljoin(base_url, href)
        except ValueError:
            continue
        normalized = url_policy.normalize(absolute)
        if normalized in seen:
            continue
        seen.add(normalized)
        if not url_policy.is_in_scope(
            normalized, ctx.scope, allow_subdomains=ctx.config.allow_subdomains
        ):
            continue
        queue.enqueue(
            ctx.conn,
            JOB_KIND,
            {"url": normalized, "depth": depth, "scan_id": ctx.scan_id},
            dedupe_key=_dedupe_key(ctx.scan_id, normalized),
        )


def _finalize_scan(conn: sqlite3.Connection, scan_id: int, summary: CrawlSummary) -> None:
    page_count = conn.execute(
        "SELECT COUNT(*) AS n FROM pages WHERE scan_id = ?",
        (scan_id,),
    ).fetchone()["n"]
    conn.execute(
        """
        UPDATE scans
           SET status = ?,
               finished_at = CURRENT_TIMESTAMP,
               page_count = ?,
               error_count = ?
         WHERE id = ?
        """,
        (summary.status, int(page_count), summary.errors, scan_id),
    )
