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
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol
from urllib.parse import urljoin

import httpx
from selectolax.parser import HTMLParser

from audit.analyzer.alfa import (
    AlfaAnalyzer,
    AlfaError,
    AlfaFinding,
    AlfaResult,
    chromium_executable_path,
)
from audit.analyzer.alfa import availability as alfa_availability
from audit.analyzer.axe import AxeAnalyzer, AxeViolation
from audit.analyzer.axe import Level as AxeLevel
from audit.analyzer.focus import FocusFinding, FocusProbe
from audit.analyzer.interaction import InteractionProbe, RevealedViolation
from audit.analyzer.keyboard import KeyboardProbe, KeyboardTrap
from audit.analyzer.ocr.pool import OcrPool
from audit.analyzer.responsive import ResponsiveFinding, ResponsiveProbe
from audit.analyzer.visual import VisualFinding, VisualProbe
from audit.analyzer.vlm.base import VlmProvider
from audit.analyzer.vlm.ollama import OllamaProvider
from audit.analyzer.vlm.vision import OllamaVisionProvider
from audit.blob_store import BlobStore
from audit.config import get_settings
from audit.crawler import url_policy
from audit.crawler.fetcher import FetchError, FetchResult, StaticFetcher
from audit.crawler.js_fetcher import JsFetcher
from audit.crawler.rate_limit import HostLimiter
from audit.crawler.render_detect import is_challenge_response, is_js_only
from audit.crawler.robots import RobotsChecker
from audit.crawler.url_policy import HostScope
from audit.db import queue, repo
from audit.extractor.downloader import ImageDownloader, ImageDownloaderProtocol
from audit.extractor.pipeline import OcrConfig, VlmConfig, process_page
from audit.logging import get_logger
from audit.synthesizer.findings import synthesize_findings

log = get_logger(__name__)

JOB_KIND = "fetch"


class AlfaPageAnalyzer(Protocol):
    """Narrow per-page Alfa contract, including authenticated adapters."""

    async def run(self, url: str, *, level: str) -> AlfaResult: ...


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
    user_agent: str = "axcess/0.1 (+local accessibility audit)"
    request_timeout_s: float = 30.0
    # OCR — disable with ``ocr_enabled=False`` or by passing ``--skip-ocr`` on the CLI.
    ocr_enabled: bool = True
    ocr_language: str = "eng"
    ocr_max_workers: int = 2
    ocr_min_confidence: float = 60.0
    ocr_min_word_count: int = 3
    # VLM — disabled unless Ollama is reachable and the model is loaded.
    vlm_enabled: bool = True
    vlm_model: str = "qwen3-vl:2b-instruct"
    vlm_base_url: str = "http://localhost:11434"
    vlm_prompt_name: str = "classify_v1.txt"
    vlm_concurrency: int = 1
    # Synthesis — toggle off with ``--skip-synthesize`` if the caller wants
    # to run ``audit synthesize`` manually against the same scan later.
    synthesize_enabled: bool = True
    # Explicit override for the diff's ``compare_to`` scan id. ``None`` means
    # auto-discover the most-recent completed scan of the same logical site
    # (matched via :func:`audit.crawler.url_policy.compare_key`).
    compare_to: int | None = None
    # JS rendering. ``js_enabled`` lets the orchestrator start Playwright on
    # demand (when the static fetcher sees a JS-only page or a bot-challenge
    # interstitial). ``js_eager`` renders EVERY page in a real browser and
    # defaults to True: this is an accessibility auditor, and three of the
    # four detection pipelines (axe, keyboard probe, responsive probe) can
    # only see a rendered DOM. The pre-flip default (False) silently
    # produced near-zero axe coverage on static sites — an audit tool must
    # not have a fast path that quietly guts its own audit. Set
    # ``js_eager=False`` (CLI ``--static-only``) for a fast link-inventory
    # crawl when rendered-DOM checks aren't needed.
    js_enabled: bool = True
    js_eager: bool = True
    # Run Axcess' public Playwright browser in the background by default.
    # Local operators can opt into a headed window to watch page navigation.
    browser_headless: bool = True
    # Authenticated scans must not make an anonymous HTTP request before the
    # shared browser fetch. When true, every document is retrieved directly
    # through the injected Playwright context.
    browser_only: bool = False
    # Protected direct-login mode can omit image extraction entirely unless
    # the auditor explicitly enables local OCR/image analysis.
    image_extraction_enabled: bool = True
    # Scope: by default, the crawler stays under the seed URL's path prefix
    # (so ``https://example.com/docs/`` only follows ``/docs/*`` links).
    # Set ``whole_host`` to follow every link on the seed host.
    whole_host: bool = False
    # WCAG 2.x AA scan via axe-core. Runs against the rendered DOM, so it
    # requires Playwright — pages fetched statically are skipped (only
    # relevant under ``--static-only``). ``axe_level`` is the WCAG level
    # the rule set is filtered to: "A" (Level A only), "AA" (default — A+AA),
    # or "AAA" (all). Best-practice rules are always included.
    axe_enabled: bool = True
    axe_level: str = "AA"
    # Independent Siteimprove Alfa ACT-rule engine. It is opt-in because it
    # runs a second local-browser capture per page. It can run alongside axe
    # or alone; Axcess still owns scope, page inventory, and evidence storage.
    alfa_enabled: bool = False
    alfa_timeout_s: float = 75.0
    alfa_concurrency: int = 1
    # Per-criterion semantic analyzers (Phase 9+). Each enabled SC runs
    # one LLM call per page; the criteria list is the SCs to evaluate.
    # Default is the Phase 9 wave-1 set (the 10 SCs picked for first
    # build-out). At 10k pages x 10 SCs = ~100k local Ollama calls,
    # roughly 3h on M-series with the 7B model. ``--skip-semantic``
    # disables the whole pass; ``--semantic-criteria 2.4.4,1.3.1``
    # narrows to a subset.
    semantic_enabled: bool = True
    semantic_criteria: tuple[str, ...] = (
        "2.4.4",  # Link Purpose (In Context)
        "2.4.9",  # Link Purpose (Link Only)
        "2.4.6",  # Headings and Labels descriptiveness
        "2.4.10",  # Section Headings
        "2.5.3",  # Label in Name
        "3.3.2",  # Labels or Instructions
        "1.3.5",  # Identify Input Purpose
        "1.3.1",  # Info and Relationships
        "4.1.2",  # Name, Role, Value (semantic)
        "1.1.1",  # Non-text Content descriptiveness
        "1.2.1",  # Audio-only (prerecorded) transcript presence
    )
    semantic_concurrency: int = 1
    # SC 2.1.2 keyboard-exit probe. Default ON, but intentionally partial:
    # only repeated bidirectional exit failure on the same observable element
    # becomes a review lead. Cost is bounded (≤ max_focusable*2+4 forward
    # presses plus a small reverse confirmation), and the page is already open
    # in Playwright for axe. Disable with ``--skip-keyboard`` when crawl speed
    # matters more than this evidence.
    keyboard_probe_enabled: bool = True
    keyboard_probe_max_focusable: int = 50
    # Responsive/zoom/text-spacing probe (Phase 10). Three dynamic checks
    # on the live page: 320px reflow (SC 1.4.10), ~200% zoom text
    # clipping (SC 1.4.4), and the WCAG text-spacing override
    # (SC 1.4.12). The zoom-lock viewport-meta check is deliberately NOT
    # here — axe's `meta-viewport` rule already covers it. ~1-2s per
    # page; disable with ``--skip-responsive``.
    responsive_checks_enabled: bool = True
    # SC 2.4.11 Focus Not Obscured — live-page focus probe. Deterministic
    # (focuses each element, checks for a sticky/fixed overlay over its
    # centre); no model. Default on; disable with ``--skip-focus``.
    focus_checks_enabled: bool = True
    # SC 1.3.2 Meaningful Sequence — visual (VLM) probe. Screenshots the page
    # and asks a local vision model whether the visual reading order matches
    # the DOM order. Needs Ollama + a vision model; no-ops cleanly without
    # one. One VLM call per page, so it respects the same vlm_enabled gate.
    # Default on; disable with ``--skip-visual``.
    visual_checks_enabled: bool = True
    # Interaction probe. Clicks the page's controls and re-runs axe on
    # each state a click reveals, so defects inside closed menus,
    # unopened dialogs, and unswitched tabs become visible. Findings
    # persist as ordinary axe rows carrying ``revealed_by``, so the
    # existing (page_id, rule_id, target_hash) uniqueness already stops
    # an unchanged header being reported once per click.
    #
    # OFF by default, unlike every other probe here: it is the only pass
    # that mutates the page, and it costs one axe run per revealed state
    # rather than one per page. Enable with ``--interaction``.
    interaction_checks_enabled: bool = False
    interaction_max_clicks: int = 40
    interaction_max_repeated: int = 3
    interaction_max_depth: int = 2
    # Per-finding element screenshots. When on (default), the JS fetcher
    # captures a circled screenshot of each live-page finding's element
    # at scan time; the orchestrator stores it in the blob store and threads
    # the hash onto the row, so the Excel report can embed the exact spot of
    # each issue. Bounded per page (see ``js_fetcher.MAX_SHOTS_PER_PAGE``);
    # disable with ``--skip-screenshots`` when crawl speed matters more.
    capture_screenshots: bool = True


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
    pages_skipped_scope: int = 0
    ocr_analyzed: int = 0
    ocr_text_candidates: int = 0
    vlm_classified: int = 0
    vlm_errors: int = 0
    semantic_pages_analyzed: int = 0
    semantic_findings_total: int = 0
    axe_pages_scanned: int = 0
    axe_violations_total: int = 0
    alfa_pages_scanned: int = 0
    alfa_failed_total: int = 0
    alfa_cant_tell_total: int = 0
    keyboard_pages_probed: int = 0
    keyboard_traps_total: int = 0
    responsive_pages_probed: int = 0
    responsive_findings_total: int = 0
    focus_pages_probed: int = 0
    focus_findings_total: int = 0
    visual_pages_probed: int = 0
    visual_findings_total: int = 0
    interaction_pages_probed: int = 0
    interaction_clicked_total: int = 0
    interaction_findings_total: int = 0
    findings_written: int = 0
    findings_by_severity: dict[str, int] = field(
        default_factory=lambda: {"critical": 0, "major": 0, "minor": 0, "info": 0}
    )
    compare_to_scan_id: int | None = None
    first_seen: int = 0
    resolved: int = 0
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
    image_downloader: ImageDownloaderProtocol | None = None,
    alfa_analyzer: AlfaPageAnalyzer | None = None,
) -> CrawlSummary:
    """Execute (or resume) a crawl for ``config.seed_url``."""
    # Path-auto-slash first (``/bicentennial`` → ``/bicentennial/``), then
    # the canonical normalize pass. Scope then reads the normalized path.
    seed_with_slash = url_policy.normalize_seed_url(config.seed_url)
    normalized_seed = url_policy.normalize(seed_with_slash)
    scope = url_policy.build_scope(normalized_seed, whole_host=config.whole_host)

    scan_id = _ensure_scan(conn, normalized_seed, config)
    queue.reclaim_expired(conn)
    # If we're reusing a scan whose queue was built under different scope
    # rules (e.g. path-scope was added after the scan started, or the user
    # re-submitted the seed with a tighter prefix), drop pending jobs that
    # fall outside the current scope. Without this, a resume would spend
    # time leasing + rejecting them at process time.
    _purge_out_of_scope_jobs(
        conn,
        scan_id=scan_id,
        scope=scope,
        allow_subdomains=config.allow_subdomains,
    )
    _seed_queue(conn, scan_id, normalized_seed)

    summary = CrawlSummary(scan_id=scan_id, seed_url=normalized_seed)
    limiter = HostLimiter(rps=config.rps, concurrency_per_host=config.concurrency_per_host)

    owned_client = http_client is None
    client = http_client or _default_client(config)
    robots = RobotsChecker(client, user_agent=config.user_agent)
    fetcher = StaticFetcher(client)
    blob_store = BlobStore(get_settings().blob_dir)
    downloader = image_downloader or ImageDownloader(client, blob_store)
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
    # Build the axe analyzer once for the whole crawl. Reads the bundled
    # axe.min.js off disk; reuses the same JS source across every page so
    # we pay the 553 KB I/O cost once. A missing bundle is loud, not
    # silent — the crawl fails fast rather than silently producing
    # zero axe findings.
    axe_analyzer: AxeAnalyzer | None = None
    axe_level: AxeLevel = "AA"
    if config.axe_enabled:
        try:
            axe_analyzer = AxeAnalyzer.from_bundled()
            if config.axe_level in ("A", "AA", "AAA"):
                axe_level = config.axe_level  # type: ignore[assignment]
            else:
                log.warning(
                    "crawl.axe_level_invalid",
                    requested=config.axe_level,
                    used="AA",
                )
        except FileNotFoundError as exc:
            log.warning("crawl.axe_disabled_missing_bundle", error=str(exc))
            summary.notes.append("Axe scan disabled: bundle missing.")
            axe_analyzer = None
    if config.alfa_enabled:
        state = alfa_availability()
        if not state.available:
            # A selected engine must never quietly become a clean result.
            raise RuntimeError(state.reason or "Siteimprove Alfa is unavailable.")
        if alfa_analyzer is None:
            alfa_analyzer = AlfaAnalyzer(
                user_agent=config.user_agent,
                timeout_s=config.alfa_timeout_s,
                concurrency=config.alfa_concurrency,
                chromium_path=await chromium_executable_path(),
            )
    else:
        alfa_analyzer = None
    # SC 2.1.2 keyboard probe — default on. Constructed once per crawl
    # and reused across all pages; cheap to allocate, no state.
    keyboard_probe: KeyboardProbe | None = None
    if config.keyboard_probe_enabled:
        keyboard_probe = KeyboardProbe(
            max_focusable=config.keyboard_probe_max_focusable,
        )
    # Responsive/zoom/text-spacing probe (SC 1.4.4/1.4.10/1.4.12) —
    # default on. Stateless like the keyboard probe.
    responsive_probe: ResponsiveProbe | None = None
    if config.responsive_checks_enabled:
        responsive_probe = ResponsiveProbe()
    # SC 2.4.11 focus-obscured probe — default on. Deterministic, stateless.
    focus_probe: FocusProbe | None = None
    if config.focus_checks_enabled:
        focus_probe = FocusProbe()
    # Visual pipeline probe. SC 2.2.2 (motion) is deterministic and always
    # runs; SC 1.3.2 (meaningful sequence) needs a vision model, so we attach
    # the provider only when one is reachable (else that check no-ops).
    visual_probe: VisualProbe | None = None
    if config.visual_checks_enabled:
        vision_provider = None
        if config.vlm_enabled:
            vision_provider = await _build_vision_provider(config, client)
        visual_probe = VisualProbe(provider=vision_provider)
    # Interaction probe — opt-in. Shares the crawl's single AxeAnalyzer so
    # axe is injected once per page whether or not this probe runs.
    interaction_probe: InteractionProbe | None = None
    if config.interaction_checks_enabled and axe_analyzer is not None:
        interaction_probe = InteractionProbe(
            axe=axe_analyzer,
            level=axe_level,
            max_clicks=config.interaction_max_clicks,
            max_repeated=config.interaction_max_repeated,
            max_depth=config.interaction_max_depth,
        )
    js_holder: _LazyJs | None = None
    if js_fetcher is not None or config.js_enabled:
        js_holder = _LazyJs(
            user_agent=config.user_agent,
            injected=js_fetcher,
            axe_analyzer=axe_analyzer,
            axe_level=axe_level,
            keyboard_probe=keyboard_probe,
            responsive_probe=responsive_probe,
            focus_probe=focus_probe,
            visual_probe=visual_probe,
            interaction_probe=interaction_probe,
            capture_screenshots=config.capture_screenshots,
            headless=config.browser_headless,
        )
    # Phase 9+: build the semantic analyzer list once per crawl. The
    # provider holds the shared Ollama semaphore so per-page analyzers
    # don't multiply load on the daemon.
    _semantic_provider, semantic_analyzers = await _build_semantic_analyzers(config, client)
    if semantic_analyzers:
        log.info(
            "semantic.enabled",
            count=len(semantic_analyzers),
            criteria=[a.criterion_sc for a in semantic_analyzers],
        )
    ctx = _WorkerContext(
        conn=conn,
        config=config,
        scope=scope,
        scan_id=scan_id,
        limiter=limiter,
        robots=robots,
        static=fetcher,
        js=js_holder,
        downloader=downloader,
        blob_store=blob_store,
        ocr=ocr_config,
        vlm=vlm_config,
        alfa=alfa_analyzer,
        in_flight=0,
        summary=summary,
        semantic_analyzers=semantic_analyzers,
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
                prior = config.compare_to
                if prior is None:
                    prior = _previous_completed_scan(conn, normalized_seed, scan_id)
                synth = synthesize_findings(conn, scan_id=scan_id, compare_to=prior)
                summary.findings_written = synth.findings_written
                summary.findings_by_severity = synth.by_severity
                summary.compare_to_scan_id = prior
                summary.first_seen = synth.first_seen
                summary.resolved = synth.resolved
            except Exception as exc:
                log.warning("synthesize.failed", scan_id=scan_id, error=str(exc))
        _finalize_scan(conn, scan_id, summary)
        if ocr_pool is not None:
            ocr_pool.shutdown()
        if js_holder is not None:
            with contextlib.suppress(Exception):
                await js_holder.shutdown()
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
           AND NOT EXISTS (
               SELECT 1 FROM protected_scans p WHERE p.scan_id = scans.id
           )
         ORDER BY id DESC
         LIMIT 1
        """,
        (seed_url,),
    ).fetchone()
    if row is not None:
        scan_id = int(row["id"])
        conn.execute(
            "UPDATE scans SET status = 'running', finished_at = NULL, failure_reason = NULL, "
            "config_json = ? WHERE id = ?",
            (config_json_for_scan(config), scan_id),
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


def config_json_for_scan(config: CrawlConfig) -> str:
    """Serialize the scan-relevant config for the ``scans.config_json`` column.

    Single source of truth — the web layer's ``_prepare_scan_row`` uses
    this too, so both writers produce the same shape. The pipeline flags
    matter beyond reproducibility: the UI's "methods used on this scan"
    row derives from them, so an operator can tell a full audit from a
    ``--static-only`` link inventory at a glance.
    """
    return json.dumps(
        {
            "max_pages": config.max_pages,
            "max_depth": config.max_depth,
            "allow_subdomains": config.allow_subdomains,
            "rps": config.rps,
            "workers": config.workers,
            "ignore_robots": config.ignore_robots,
            "concurrency_per_host": config.concurrency_per_host,
            "user_agent": config.user_agent,
            # Pipeline switches — drives the "methods used" UI row.
            "js_eager": config.js_eager,
            "browser_headless": config.browser_headless,
            "browser_only": config.browser_only,
            "image_extraction_enabled": config.image_extraction_enabled,
            "ocr_enabled": config.ocr_enabled,
            "vlm_enabled": config.vlm_enabled,
            "axe_enabled": config.axe_enabled,
            "axe_level": config.axe_level,
            "alfa_enabled": config.alfa_enabled,
            "alfa_timeout_s": config.alfa_timeout_s,
            "alfa_concurrency": config.alfa_concurrency,
            "semantic_enabled": config.semantic_enabled,
            "keyboard_probe_enabled": config.keyboard_probe_enabled,
            "responsive_checks_enabled": config.responsive_checks_enabled,
            "focus_checks_enabled": config.focus_checks_enabled,
            "visual_checks_enabled": config.visual_checks_enabled,
            "interaction_checks_enabled": config.interaction_checks_enabled,
            # Version 1 means completed-page counters for semantic, keyboard,
            # and responsive checks are persisted on the scan row. Older
            # reports omit this key and must be labeled "coverage not recorded"
            # rather than inferred from configuration or finding counts.
            "method_coverage_version": 1,
        },
        sort_keys=True,
    )


# Backwards-compatible private alias (existing call sites/tests).
_config_json = config_json_for_scan


def _purge_out_of_scope_jobs(
    conn: sqlite3.Connection,
    *,
    scan_id: int,
    scope: HostScope,
    allow_subdomains: bool,
) -> int:
    """Delete pending ``fetch`` jobs for ``scan_id`` whose URL is out of scope.

    Returns the number of rows dropped. Safe to call on scans that don't
    have any stale jobs — no-op if every pending job still matches scope.
    """
    rows = conn.execute(
        "SELECT id, payload_json FROM jobs "
        "WHERE kind = ? AND state = 'pending' "
        "AND json_extract(payload_json, '$.scan_id') = ?",
        (JOB_KIND, scan_id),
    ).fetchall()
    stale: list[int] = []
    for row in rows:
        try:
            payload = json.loads(row["payload_json"])
        except (TypeError, ValueError):
            stale.append(int(row["id"]))
            continue
        url = str(payload.get("url") or "")
        if not url_policy.is_in_scope(url, scope, allow_subdomains=allow_subdomains):
            stale.append(int(row["id"]))
    if stale:
        placeholders = ",".join("?" * len(stale))
        conn.execute(
            f"DELETE FROM jobs WHERE id IN ({placeholders})",  # noqa: S608 — ids only
            stale,
        )
        log.info("crawl.purge_out_of_scope", scan_id=scan_id, dropped=len(stale))
    return len(stale)


def _seed_queue(conn: sqlite3.Connection, scan_id: int, seed_url: str) -> None:
    queue.enqueue(
        conn,
        JOB_KIND,
        {"url": seed_url, "depth": 0, "scan_id": scan_id},
        dedupe_key=_dedupe_key(scan_id, seed_url),
    )


def _dedupe_key(scan_id: int, url: str) -> str:
    return f"{JOB_KIND}:{scan_id}:{url}"


class _LazyJs:
    """Start the Playwright JsFetcher on first use, keep it alive for the crawl.

    Chromium startup costs ~1-2 seconds, so we don't pay it unless a page
    actually needs JS rendering (SPA bootstrap or a WAF challenge). If a
    caller injects a ready-made JsFetcher, we use it directly and don't
    manage its lifecycle.
    """

    def __init__(
        self,
        *,
        user_agent: str,
        injected: JsFetcher | None = None,
        axe_analyzer: AxeAnalyzer | None = None,
        axe_level: AxeLevel = "AA",
        keyboard_probe: KeyboardProbe | None = None,
        responsive_probe: ResponsiveProbe | None = None,
        focus_probe: FocusProbe | None = None,
        visual_probe: VisualProbe | None = None,
        interaction_probe: InteractionProbe | None = None,
        capture_screenshots: bool = False,
        headless: bool = True,
    ) -> None:
        self._user_agent = user_agent
        self._fetcher: JsFetcher | None = injected
        self._owned = injected is None
        self._axe_analyzer = axe_analyzer
        self._axe_level: AxeLevel = axe_level
        self._keyboard_probe = keyboard_probe
        self._responsive_probe = responsive_probe
        self._focus_probe = focus_probe
        self._visual_probe = visual_probe
        self._interaction_probe = interaction_probe
        self._capture_screenshots = capture_screenshots
        self._headless = headless

    async def get(self) -> JsFetcher:
        if self._fetcher is None:
            fetcher = JsFetcher(
                user_agent=self._user_agent,
                axe_analyzer=self._axe_analyzer,
                axe_level=self._axe_level,
                keyboard_probe=self._keyboard_probe,
                responsive_probe=self._responsive_probe,
                focus_probe=self._focus_probe,
                visual_probe=self._visual_probe,
                interaction_probe=self._interaction_probe,
                capture_screenshots=self._capture_screenshots,
                headless=self._headless,
            )
            await fetcher.__aenter__()
            self._fetcher = fetcher
        return self._fetcher

    async def shutdown(self) -> None:
        if self._owned and self._fetcher is not None:
            await self._fetcher.__aexit__(None, None, None)
            self._fetcher = None


@dataclass
class _WorkerContext:
    conn: sqlite3.Connection
    config: CrawlConfig
    scope: HostScope
    scan_id: int
    limiter: HostLimiter
    robots: RobotsChecker
    static: StaticFetcher
    js: _LazyJs | None
    downloader: ImageDownloaderProtocol
    # Shared content-addressed store. Used to persist per-finding element
    # screenshots captured at scan time (the hash lands on the finding row).
    blob_store: BlobStore
    ocr: OcrConfig | None
    vlm: VlmConfig | None
    alfa: AlfaPageAnalyzer | None
    in_flight: int
    summary: CrawlSummary
    # Phase 9+: list of per-criterion semantic analyzers to run per
    # page. Empty when ``config.semantic_enabled`` is False, the
    # provider can't reach Ollama, or no SC is registered.
    semantic_analyzers: list[Any] = field(default_factory=list)


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


async def _build_vision_provider(
    config: CrawlConfig,
    client: httpx.AsyncClient,
) -> OllamaVisionProvider | None:
    """Build the SC 1.3.2 vision provider, or None if no model is reachable.

    Reuses the configured ``vlm_model`` (a vision model) + base URL. The
    health probe avoids hammering a dead daemon once per page.
    """
    provider = OllamaVisionProvider(
        client,
        model=config.vlm_model,
        base_url=config.vlm_base_url,
        concurrency=config.vlm_concurrency,
    )
    if not await provider.healthy():
        log.warning(
            "visual.unavailable",
            model=config.vlm_model,
            hint="No reachable vision model; skipping the SC 1.3.2 visual probe.",
        )
        return None
    return provider


async def _build_semantic_analyzers(
    config: CrawlConfig,
    client: httpx.AsyncClient,
) -> tuple[Any, list[Any]]:
    """Build the per-criterion semantic analyzer list for this crawl.

    Returns ``(provider, analyzers)``. ``provider`` is the shared
    :class:`OllamaTextProvider` (or ``None`` if disabled / unhealthy);
    ``analyzers`` is the registered analyzers for
    ``config.semantic_criteria`` (or ``[]``).

    The semantic pass is opt-out: if Ollama isn't reachable, or no
    requested criterion has a registered analyzer yet, we log and
    return an empty list. The crawl continues without semantic
    findings — same graceful-skip semantics as the VLM and axe
    pipelines.
    """
    if not config.semantic_enabled:
        return None, []
    if not config.semantic_criteria:
        return None, []

    # Imports inside the function so the orchestrator module doesn't
    # depend on the semantic package at import time — the analyzer
    # is a Phase 9+ addition; importing eagerly would couple existing
    # crawl flow to a brand-new module.
    # Default model: pick from the model registry's text-default. The
    # per-criterion analyzer may override via its own pick when the
    # registry assigns a specialty model (e.g. SC 2.5.3 → 14B).
    from audit.analyzer.model_registry import get_pick
    from audit.analyzer.semantic.ollama_text import OllamaTextProvider
    from audit.analyzer.semantic.registry import build_analyzers

    default_pick = get_pick(None, kind="text")
    provider = OllamaTextProvider(
        client,
        model=default_pick.primary,
        base_url=config.vlm_base_url,
        concurrency=config.semantic_concurrency,
    )
    if not await provider.healthy():
        log.warning(
            "semantic.unavailable",
            model=default_pick.primary,
            base_url=config.vlm_base_url,
            hint=(
                "Ollama daemon not running or model not pulled; "
                "continuing without semantic analyzers."
            ),
        )
        return None, []

    analyzers = build_analyzers(config.semantic_criteria, provider)
    if not analyzers:
        log.warning(
            "semantic.no_registered_analyzers",
            requested=list(config.semantic_criteria),
            hint="None of the requested criteria are registered yet.",
        )
        return None, []
    return provider, analyzers


async def _worker(ctx: _WorkerContext) -> None:
    """Lease and process jobs until both queue and peers are idle."""
    while True:
        if _page_limit_reached(ctx):
            return
        job = queue.lease(ctx.conn, JOB_KIND, lease_secs=120, scan_id=ctx.scan_id)
        if job is None:
            if (
                ctx.in_flight == 0
                and queue.pending_count(ctx.conn, JOB_KIND, scan_id=ctx.scan_id) == 0
            ):
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

    # Defensive re-check: jobs enqueued under a previous scope (e.g. before
    # the user added a path prefix, or before a server upgrade that tightened
    # scope rules) shouldn't be fetched. Cheaper than the robots call below.
    if not url_policy.is_in_scope(url, ctx.scope, allow_subdomains=ctx.config.allow_subdomains):
        ctx.summary.pages_skipped_scope += 1
        return

    if not ctx.config.ignore_robots and not await ctx.robots.allowed(url):
        ctx.summary.pages_skipped_robots += 1
        return

    async with ctx.limiter.throttle(url):
        if ctx.config.browser_only:
            if ctx.js is None:
                raise RuntimeError("Browser-only crawling requires an injected browser fetcher.")
            try:
                result = await (await ctx.js.get()).fetch(url)
                render_mode = "js"
            except FetchError:
                log.warning("crawl.js_fetch_failed", protected_context=True)
                ctx.summary.errors += 1
                _record_page(ctx, url, status_code=None, result=None, render_mode="js")
                return
        else:
            try:
                result = await ctx.static.fetch(url)
            except FetchError as exc:
                log.warning("crawl.fetch_failed", url=url, error=str(exc))
                ctx.summary.errors += 1
                _record_page(ctx, url, status_code=None, result=None, render_mode="static")
                return
            render_mode = "static"

    if not ctx.config.browser_only and ctx.js is not None and _should_escalate_to_js(ctx, result):
        try:
            js_fetcher = await ctx.js.get()
            result = await js_fetcher.fetch(url)
            render_mode = "js"
        except FetchError as exc:
            log.warning("crawl.js_fetch_failed", url=url, error=str(exc))

    page_id = _record_page(
        ctx, url, status_code=result.status_code, result=result, render_mode=render_mode
    )
    ctx.summary.pages_fetched += 1

    if (
        ctx.config.image_extraction_enabled
        and result.is_html
        and result.is_ok
        and page_id is not None
    ):
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

    # Browser and semantic evidence is independent of image extraction.
    # Login scans intentionally disable protected-image persistence by
    # default, but axe, keyboard, responsive, focus, Alfa, and semantic work
    # must still be retained for every successfully rendered HTML page.
    if result.is_html and result.is_ok and page_id is not None:
        # Persist axe-core violations attached by JsFetcher. Static fetches
        # never carry violations (axe needs a browser); we count an axe-page
        # only when violations is a real attached tuple, even an empty one
        # — that distinguishes "we scanned and found nothing" from "we
        # never scanned this page." JsFetcher always returns a tuple after
        # a successful axe run, so the proxy here is `render_mode == "js"`
        # AND axe was on.
        if render_mode == "js" and ctx.config.axe_enabled:
            _persist_axe(
                ctx,
                page_id=page_id,
                violations=result.axe_violations,
                screenshots=result.screenshots,
            )

        # Alfa is a distinct ACT-rule engine, not an axe wrapper. It makes
        # its own local browser capture of this already in-scope URL; capture
        # details and outcome type are retained on each row so the report can
        # never suggest both engines observed one identical DOM snapshot.
        if ctx.alfa is not None:
            try:
                alfa_result = await ctx.alfa.run(result.url, level=ctx.config.axe_level)
                _persist_alfa(
                    ctx,
                    page_id=page_id,
                    findings=alfa_result.findings,
                    failed_total=alfa_result.failed_total,
                    cant_tell_total=alfa_result.cant_tell_total,
                )
                if alfa_result.truncated:
                    _add_note_once(
                        ctx.summary,
                        "Alfa capped page-level evidence at 200 actionable outcomes; "
                        "see source rule links for follow-up.",
                    )
            except AlfaError as exc:
                log.warning("alfa.page_failed", url=result.url, error=str(exc))
                _add_note_once(
                    ctx.summary,
                    "Alfa could not evaluate one or more pages; its coverage counts "
                    "show only completed Alfa captures.",
                )

        # SC 2.1.2 keyboard-trap probe. Only runs when the page was
        # JS-rendered (the probe needs a live page; static fetches
        # have no FetchResult.keyboard_traps populated). On by default;
        # ``--skip-keyboard`` disables. Persist via the dedicated
        # keyboard helper so the row is tagged ``pipeline='keyboard'``.
        if render_mode == "js" and ctx.config.keyboard_probe_enabled:
            _persist_keyboard(
                ctx,
                page_id=page_id,
                traps=result.keyboard_traps,
                screenshots=result.screenshots,
            )

        # Responsive/zoom/text-spacing probe (SC 1.4.4/1.4.10/1.4.12).
        # Same gating shape as the keyboard probe; rows are tagged
        # ``pipeline='responsive'``.
        if render_mode == "js" and ctx.config.responsive_checks_enabled:
            _persist_responsive(
                ctx,
                page_id=page_id,
                findings=result.responsive_findings,
                screenshots=result.screenshots,
            )

        # SC 2.4.11 focus-obscured probe. Same gating; rows tagged
        # ``pipeline='focus'``.
        if render_mode == "js" and ctx.config.focus_checks_enabled:
            _persist_focus(
                ctx,
                page_id=page_id,
                findings=result.focus_findings,
                screenshots=result.screenshots,
            )

        # SC 1.3.2 visual probe. Rows tagged ``pipeline='visual'``.
        if render_mode == "js" and ctx.config.visual_checks_enabled:
            _persist_visual(
                ctx,
                page_id=page_id,
                findings=result.visual_findings,
                screenshots=result.screenshots,
            )

        # Interaction probe. Unlike the probes above these are NOT tagged
        # with their own pipeline: what the probe found is an axe
        # violation, so it goes down the ordinary axe path and inherits
        # its (page_id, rule_id, target_hash) dedupe. All that is added is
        # ``revealed_by``.
        if render_mode == "js" and ctx.config.interaction_checks_enabled:
            _persist_interaction(
                ctx,
                page_id=page_id,
                findings=result.interaction_findings,
                screenshots=result.screenshots,
            )

        # Phase 9+: per-criterion semantic analyzers. Works on both
        # static and JS-rendered fetches because the first wave is
        # selectolax-based (the HTML body is enough). Later phases
        # adding contrast / focus-visible analyzers will check
        # ``render_mode == 'js'`` themselves before running.
        if ctx.semantic_analyzers:
            await _run_semantic(ctx, page_id=page_id, result=result)

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


def _should_escalate_to_js(ctx: _WorkerContext, result: FetchResult) -> bool:
    """Decide whether a static fetch result warrants a re-fetch via Playwright.

    Three triggers, any of which is enough:
      * ``js_eager`` is on — the caller asked for JS on every page.
      * the static HTML clearly needs client rendering (SPA bootstrap).
      * the response looks like a WAF / bot-check interstitial.

    The static body still needs to be present so we aren't re-fetching
    binary responses or images.
    """
    if ctx.config.js_eager and result.is_html:
        return True
    body = result.body or b""
    if result.is_html and result.is_ok and is_js_only(body):
        return True
    return is_challenge_response(result.status_code, body)


def _store_screenshot(
    ctx: _WorkerContext, target_hash: str, screenshots: Mapping[str, bytes]
) -> str | None:
    """Persist a finding's element screenshot to the blob store.

    Returns its content hash, or ``None`` when there's no screenshot for
    this finding or the store write fails.
    """
    png = screenshots.get(target_hash)
    if not png:
        return None
    try:
        content_hash, _rel = ctx.blob_store.store(png, "image/png")
        return content_hash
    except Exception as exc:  # pragma: no cover - defensive
        log.warning("screenshot.persist_failed", target_hash=target_hash, error=str(exc))
        return None


def _persist_axe(
    ctx: _WorkerContext,
    *,
    page_id: int,
    violations: tuple[AxeViolation, ...],
    screenshots: Mapping[str, bytes],
) -> None:
    """Write the page's axe violations to the DB + bump the scan counters.

    One DB statement per violation row keeps the code simple at the
    expense of N writes per page. SQLite handles this trivially at our
    scale (10k pages x ~10 violations = 100k inserts, all under one
    transaction held open by the worker context).
    """
    for v in violations:
        try:
            repo.upsert_axe_violation(
                ctx.conn,
                page_id=page_id,
                scan_id=ctx.scan_id,
                rule_id=v.rule_id,
                wcag_sc=v.wcag_sc,
                wcag_scs=v.wcag_scs,
                wcag_level=v.wcag_level,
                impact=v.impact,
                help=v.help,
                help_url=v.help_url,
                target_selector=v.target_selector,
                failure_summary=v.failure_summary,
                html_snippet=v.html_snippet,
                target_hash=v.target_hash,
                screenshot_hash=_store_screenshot(ctx, v.target_hash, screenshots),
            )
        except sqlite3.Error as exc:
            # One bad row must not kill the rest of the page's findings.
            log.warning(
                "axe.persist_failed",
                rule_id=v.rule_id,
                page_id=page_id,
                error=str(exc),
            )
    repo.increment_scan_axe_counters(
        ctx.conn,
        scan_id=ctx.scan_id,
        pages_delta=1,
        violations_delta=len(violations),
    )
    ctx.summary.axe_pages_scanned += 1
    ctx.summary.axe_violations_total += len(violations)


def _persist_interaction(
    ctx: _WorkerContext,
    *,
    page_id: int,
    findings: tuple[RevealedViolation, ...],
    screenshots: Mapping[str, bytes],
) -> None:
    """Write violations that only exist after a control was operated.

    Deliberately the same ``upsert_axe_violation`` the load-state pass
    uses, against the same ``page_id``. That is the entire dedupe story:
    a violation already recorded at load has the same target_hash here,
    hits ``ON CONFLICT``, and updates instead of inserting a second row.
    The probe filters those out before they ever reach this function, so
    the constraint is a backstop rather than the primary mechanism.
    """
    for revealed in findings:
        v = revealed.violation
        try:
            repo.upsert_axe_violation(
                ctx.conn,
                page_id=page_id,
                scan_id=ctx.scan_id,
                rule_id=v.rule_id,
                wcag_sc=v.wcag_sc,
                wcag_scs=v.wcag_scs,
                wcag_level=v.wcag_level,
                impact=v.impact,
                help=v.help,
                help_url=v.help_url,
                target_selector=v.target_selector,
                failure_summary=v.failure_summary,
                html_snippet=v.html_snippet,
                target_hash=v.target_hash,
                screenshot_hash=_store_screenshot(ctx, v.target_hash, screenshots),
                revealed_by=revealed.revealed_by,
            )
        except sqlite3.Error as exc:
            log.warning(
                "interaction.persist_failed",
                rule_id=v.rule_id,
                page_id=page_id,
                error=str(exc),
            )
    # These ARE axe violations, so they belong in the scan's axe total —
    # otherwise page_a11y_findings would hold more axe rows than the
    # counter claims. pages_delta stays 0: the page was already counted as
    # axe-scanned by the load-state pass, and counting it twice would make
    # "pages scanned" exceed the number of pages.
    repo.increment_scan_axe_counters(
        ctx.conn,
        scan_id=ctx.scan_id,
        pages_delta=0,
        violations_delta=len(findings),
    )
    # Mirrored into the in-memory summary so the CLI table and the DB
    # cannot disagree, with the interaction-specific counters kept
    # alongside so the report can still say how much clicking bought.
    ctx.summary.axe_violations_total += len(findings)
    ctx.summary.interaction_pages_probed += 1
    ctx.summary.interaction_findings_total += len(findings)


def _persist_alfa(
    ctx: _WorkerContext,
    *,
    page_id: int,
    findings: tuple[AlfaFinding, ...],
    failed_total: int,
    cant_tell_total: int,
) -> None:
    """Write retained Alfa evidence and record the engine's true outcome totals.

    The runner caps stored per-page evidence to keep SQLite bounded. Coverage
    counters must still retain the complete Alfa result so the report cannot
    mislabel a truncated evidence set as the engine's full finding total.
    """
    for finding in findings:
        try:
            repo.upsert_alfa_finding(
                ctx.conn,
                page_id=page_id,
                scan_id=ctx.scan_id,
                rule_id=finding.rule_id,
                wcag_sc=finding.wcag_sc,
                wcag_scs=finding.wcag_scs,
                wcag_level=finding.wcag_level,
                help=finding.help,
                help_url=finding.rule_uri,
                target_selector=finding.target_hint,
                failure_summary=finding.failure_summary,
                html_snippet=finding.target_hint,
                target_hash=finding.target_hash,
                engine_outcome=finding.outcome,
                engine_evidence_json=finding.evidence_json,
            )
        except sqlite3.Error as exc:
            log.warning(
                "alfa.persist_failed",
                rule_id=finding.rule_id,
                page_id=page_id,
                error=str(exc),
            )
    repo.increment_scan_alfa_counters(
        ctx.conn,
        scan_id=ctx.scan_id,
        pages_delta=1,
        failed_delta=failed_total,
        cant_tell_delta=cant_tell_total,
    )
    ctx.summary.alfa_pages_scanned += 1
    ctx.summary.alfa_failed_total += failed_total
    ctx.summary.alfa_cant_tell_total += cant_tell_total


def _add_note_once(summary: CrawlSummary, note: str) -> None:
    """Keep repeated per-page engine limitations readable in the summary."""
    if note not in summary.notes:
        summary.notes.append(note)


def _persist_keyboard(
    ctx: _WorkerContext,
    *,
    page_id: int,
    traps: tuple[KeyboardTrap, ...],
    screenshots: Mapping[str, bytes],
) -> None:
    """Write keyboard-trap findings + bump the keyboard counters.

    Mirrors :func:`_persist_axe`'s row-by-row insert pattern. Counts
    every probed page (even ones that returned zero findings), because
    the operator cares about coverage — "we probed 47 of 50 pages and
    found 2 traps" is more useful than "we found 2 traps somewhere."
    """
    for t in traps:
        try:
            repo.upsert_keyboard_finding(
                ctx.conn,
                page_id=page_id,
                scan_id=ctx.scan_id,
                screenshot_hash=_store_screenshot(ctx, t.target_hash, screenshots),
                **t.to_repo_kwargs(),
            )
        except sqlite3.Error as exc:
            log.warning(
                "keyboard.persist_failed",
                rule_id=t.rule_id,
                page_id=page_id,
                error=str(exc),
            )
    repo.increment_scan_method_coverage(
        ctx.conn,
        scan_id=ctx.scan_id,
        method="keyboard",
    )
    ctx.summary.keyboard_pages_probed += 1
    ctx.summary.keyboard_traps_total += len(traps)


def _persist_responsive(
    ctx: _WorkerContext,
    *,
    page_id: int,
    findings: tuple[ResponsiveFinding, ...],
    screenshots: Mapping[str, bytes],
) -> None:
    """Write responsive-probe findings + bump the responsive counters.

    Mirrors :func:`_persist_keyboard` — pages are counted even when the
    probe found nothing, because the coverage signal ("we probed 47 of
    50 pages") matters as much as the findings.
    """
    for f in findings:
        try:
            repo.upsert_responsive_finding(
                ctx.conn,
                page_id=page_id,
                scan_id=ctx.scan_id,
                screenshot_hash=_store_screenshot(ctx, f.target_hash, screenshots),
                **f.to_repo_kwargs(),
            )
        except sqlite3.Error as exc:
            log.warning(
                "responsive.persist_failed",
                rule_id=f.rule_id,
                page_id=page_id,
                error=str(exc),
            )
    repo.increment_scan_method_coverage(
        ctx.conn,
        scan_id=ctx.scan_id,
        method="responsive",
    )
    ctx.summary.responsive_pages_probed += 1
    ctx.summary.responsive_findings_total += len(findings)


def _persist_focus(
    ctx: _WorkerContext,
    *,
    page_id: int,
    findings: tuple[FocusFinding, ...],
    screenshots: Mapping[str, bytes],
) -> None:
    """Write focus-probe findings (SC 2.4.11) + bump the focus counters."""
    for f in findings:
        try:
            repo.upsert_focus_finding(
                ctx.conn,
                page_id=page_id,
                scan_id=ctx.scan_id,
                screenshot_hash=_store_screenshot(ctx, f.target_hash, screenshots),
                **f.to_repo_kwargs(),
            )
        except sqlite3.Error as exc:
            log.warning(
                "focus.persist_failed",
                rule_id=f.rule_id,
                page_id=page_id,
                error=str(exc),
            )
    ctx.summary.focus_pages_probed += 1
    ctx.summary.focus_findings_total += len(findings)


def _persist_visual(
    ctx: _WorkerContext,
    *,
    page_id: int,
    findings: tuple[VisualFinding, ...],
    screenshots: Mapping[str, bytes],
) -> None:
    """Write visual (VLM) probe findings (SC 1.3.2) + bump the counters."""
    for f in findings:
        try:
            repo.upsert_visual_finding(
                ctx.conn,
                page_id=page_id,
                scan_id=ctx.scan_id,
                screenshot_hash=_store_screenshot(ctx, f.target_hash, screenshots),
                **f.to_repo_kwargs(),
            )
        except sqlite3.Error as exc:
            log.warning(
                "visual.persist_failed",
                rule_id=f.rule_id,
                page_id=page_id,
                error=str(exc),
            )
    ctx.summary.visual_pages_probed += 1
    ctx.summary.visual_findings_total += len(findings)


async def _run_semantic(
    ctx: _WorkerContext,
    *,
    page_id: int,
    result: FetchResult,
) -> None:
    """Run the registered semantic analyzers against this page + persist.

    Mirrors :func:`_persist_axe`'s contract: every per-analyzer failure
    is logged and dropped (the runner does the gather + log internally);
    persistence errors don't take down siblings. Net effect of any
    failure mode: zero or fewer findings, never a crashed crawl.
    """
    from audit.analyzer.semantic.base import AnalysisContext
    from audit.analyzer.semantic.runner import analyze_page

    semantic_ctx = AnalysisContext(
        body=result.body,
        page=None,  # The Playwright Page isn't currently surfaced
        # out of JsFetcher; if a future analyzer needs it, JsFetcher
        # can be extended to attach it to FetchResult the same way it
        # already attaches axe_violations.
        page_url=result.url,
    )
    findings = await analyze_page(semantic_ctx, ctx.semantic_analyzers)
    _persist_semantic(ctx, page_id=page_id, findings=findings)


def _persist_semantic(
    ctx: _WorkerContext,
    *,
    page_id: int,
    findings: list[Any],
) -> None:
    """Upsert semantic findings into ``page_a11y_findings``.

    Same row-by-row insert pattern as ``_persist_axe`` — SQLite at our
    scale handles 100k inserts cleanly. A per-row sqlite3 error logs
    + drops; the rest of the page's findings still land.

    Note: semantic findings carry no element screenshot — the semantic
    pass runs against the static HTML body with no live Playwright page,
    so there's no rendered element to capture (out of scope for the
    scan-time screenshot feature).
    """
    written = 0
    for f in findings:
        try:
            repo.upsert_semantic_finding(
                ctx.conn,
                page_id=page_id,
                scan_id=ctx.scan_id,
                **f.to_repo_kwargs(),
            )
            written += 1
        except sqlite3.Error as exc:
            log.warning(
                "semantic.persist_failed",
                criterion=f.criterion_sc,
                page_id=page_id,
                error=str(exc),
            )
    if written > 0 or ctx.semantic_analyzers:
        repo.increment_scan_method_coverage(
            ctx.conn,
            scan_id=ctx.scan_id,
            method="semantic",
        )
        ctx.summary.semantic_pages_analyzed += 1
        ctx.summary.semantic_findings_total += written


def _previous_completed_scan(
    conn: sqlite3.Connection, seed_url: str, current_scan_id: int
) -> int | None:
    """Most-recent completed scan of the same logical site, excluding ``current``.

    Matching uses :func:`audit.crawler.url_policy.compare_key`, which drops
    ports on loopback hosts so a dev-server port change doesn't hide the
    prior scan from the auto-diff.
    """
    target = url_policy.compare_key(seed_url)
    rows = conn.execute(
        """
        SELECT id, seed_url FROM scans
         WHERE status = 'completed' AND id <> ?
         ORDER BY id DESC
        """,
        (current_scan_id,),
    ).fetchall()
    for row in rows:
        if url_policy.compare_key(str(row["seed_url"])) == target:
            return int(row["id"])
    return None


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
               failure_reason = NULL,
               page_count = ?,
               error_count = ?
         WHERE id = ?
        """,
        (summary.status, int(page_count), summary.errors, scan_id),
    )
