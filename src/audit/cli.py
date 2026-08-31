"""Command-line interface for the audit tool."""

from __future__ import annotations

import asyncio
import getpass
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from audit.blob_store import BlobStore
from audit.config import get_settings
from audit.crawler.orchestrator import CrawlConfig, CrawlSummary, run_crawl
from audit.db.schema import connect
from audit.exports.collector import collect_scan
from audit.exports.csv_export import render_csv
from audit.exports.jira_export import render_jira_csv
from audit.exports.json_export import render_json
from audit.exports.markdown_report import render_markdown
from audit.exports.xlsx_export import render_xlsx
from audit.protected.companion import (
    CompanionCrawlStats,
    CompanionError,
    CompanionTlsConfig,
    ProtectedCompanionClient,
    ProtectedCompanionRunner,
)
from audit.protected.repository import purge_expired_protected_data
from audit.protected.vaults import (
    has_irreversible_protected_vault,
    resolve_configured_protected_vault,
)
from audit.synthesizer.findings import synthesize_findings

app = typer.Typer(
    help=(
        "Axcess — local, offline web accessibility auditor "
        "(images-of-text detection, keyboard-trap probing, and more)."
    ),
    no_args_is_help=True,
    add_completion=False,
)
console = Console()
protected_companion_app = typer.Typer(
    help=(
        "Run the paired local browser for an authorized protected scan. "
        "It never accepts site passwords, MFA factors, or browser session state."
    ),
    no_args_is_help=True,
    add_completion=False,
)
app.add_typer(protected_companion_app, name="protected-companion")


def _companion_tls(
    certificate: Path,
    private_key: Path,
    ca_bundle: Path | None,
) -> CompanionTlsConfig:
    try:
        return CompanionTlsConfig(
            certificate=certificate,
            private_key=private_key,
            ca_bundle=ca_bundle,
        )
    except CompanionError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=2) from None


@protected_companion_app.command("pair")
def protected_companion_pair(
    server: Annotated[str, typer.Option("--server", help="Exact HTTPS Axcess service origin.")],
    enrollment_id: Annotated[str, typer.Option("--enrollment-id", help="One-time enrollment id.")],
    certificate: Annotated[
        Path,
        typer.Option(
            "--certificate",
            exists=True,
            readable=True,
            help="Local companion mTLS certificate.",
        ),
    ],
    private_key: Annotated[
        Path,
        typer.Option(
            "--private-key",
            exists=True,
            readable=True,
            help="Local companion mTLS private key.",
        ),
    ],
    ca_bundle: Annotated[
        Path | None,
        typer.Option("--ca-bundle", exists=True, readable=True, help="Optional private CA bundle."),
    ] = None,
) -> None:
    """Claim one scan-bound pairing with a one-time code entered privately."""
    tls = _companion_tls(certificate, private_key, ca_bundle)
    # The pairing code is deliberately prompted, never accepted as a command
    # argument (shell history/process listings), config value, or environment
    # variable. It is not a target password or MFA factor.
    pairing_code = getpass.getpass("One-time pairing code: ")

    async def claim() -> dict[str, object]:
        async with ProtectedCompanionClient(
            server=server, enrollment_id=enrollment_id, tls=tls
        ) as client:
            return await client.claim(pairing_code)

    try:
        response = asyncio.run(claim())
    except CompanionError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from None
    finally:
        pairing_code = ""
    console.print(
        f"[green]Paired[/green] companion for protected scan #{response.get('scan_id', '?')}. "
        "Run the companion command next to open the headed manual sign-in browser."
    )


@protected_companion_app.command("run")
def protected_companion_run(
    server: Annotated[str, typer.Option("--server", help="Exact HTTPS Axcess service origin.")],
    enrollment_id: Annotated[str, typer.Option("--enrollment-id", help="Claimed enrollment id.")],
    certificate: Annotated[
        Path,
        typer.Option(
            "--certificate",
            exists=True,
            readable=True,
            help="Local companion mTLS certificate.",
        ),
    ],
    private_key: Annotated[
        Path,
        typer.Option(
            "--private-key",
            exists=True,
            readable=True,
            help="Local companion mTLS private key.",
        ),
    ],
    ca_bundle: Annotated[
        Path | None,
        typer.Option("--ca-bundle", exists=True, readable=True, help="Optional private CA bundle."),
    ] = None,
) -> None:
    """Open a headed browser, wait for human sign-in, then crawl read-only."""
    tls = _companion_tls(certificate, private_key, ca_bundle)

    async def run() -> CompanionCrawlStats:
        async with ProtectedCompanionClient(
            server=server, enrollment_id=enrollment_id, tls=tls
        ) as client:
            return await ProtectedCompanionRunner(client).run()

    try:
        stats = asyncio.run(run())
    except KeyboardInterrupt:
        console.print("[yellow]Protected scan interrupted; browser session was closed.[/yellow]")
        raise typer.Exit(code=130) from None
    except CompanionError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from None
    console.print(
        "[green]Protected scan completed.[/green] "
        f"{stats.pages_indexed} page(s) indexed; {stats.issue_leads_indexed} issue lead(s); "
        f"{stats.images_checked} image(s) checked."
    )


@app.command("protected-maintenance")
def protected_maintenance() -> None:
    """Perform scheduled, KMS-backed seven-day protected-evidence cleanup.

    This command is intentionally independent of ``protected_scans_enabled``:
    an emergency feature disable must not suspend mandatory retention cleanup.
    It accepts no target, scan ID, KMS path, credential, or key argument. The
    deployment's reviewed vault factory is the only supported source of a
    production KMS, and output reports a count only so cron/system logs never
    become another protected-report metadata channel.
    """

    settings = get_settings()
    vault = resolve_configured_protected_vault(settings)
    if not has_irreversible_protected_vault(vault):
        console.print(
            "[red]Protected maintenance requires a configured production KMS "
            "with irreversible per-scan key destruction.[/red]"
        )
        raise typer.Exit(code=2)
    if not settings.db_path.is_file():
        console.print(
            "[red]Protected maintenance could not open the configured audit database.[/red]"
        )
        raise typer.Exit(code=1)

    conn = None
    try:
        conn = connect(settings.db_path)
        purged_scan_ids = purge_expired_protected_data(conn, vault=vault)
    except Exception:
        # KMS adapters can raise provider diagnostics containing endpoint or
        # account details. The repository has already failed closed (no row is
        # marked erased until its key revoke succeeds); keep scheduler output
        # equally non-sensitive and rely on approved deployment observability
        # to diagnose the provider integration.
        console.print(
            "[red]Protected maintenance did not complete; protected evidence "
            "was not marked erased.[/red]"
        )
        raise typer.Exit(code=1) from None
    finally:
        if conn is not None:
            conn.close()

    console.print(
        "[green]Protected maintenance completed.[/green] "
        f"{len(purged_scan_ids)} protected report(s) cryptographically erased."
    )


@app.command()
def crawl(
    url: Annotated[str, typer.Argument(help="Seed URL to crawl.")],
    max_pages: Annotated[
        int, typer.Option("--max-pages", "-n", min=1, help="Maximum pages to fetch.")
    ] = 500,
    max_depth: Annotated[
        int, typer.Option("--max-depth", "-d", min=1, help="Maximum crawl depth.")
    ] = 10,
    include_subdomain: Annotated[
        bool, typer.Option("--include-subdomain", help="Follow links on subdomains.")
    ] = False,
    whole_host: Annotated[
        bool,
        typer.Option(
            "--whole-host",
            help=(
                "Follow every in-host link instead of staying under the seed URL's "
                "path. Default is path-scoped (e.g. /bicentennial/ crawls only that "
                "section)."
            ),
        ),
    ] = False,
    rps: Annotated[
        float, typer.Option("--rps", min=0.1, help="Max requests per second per host.")
    ] = 2.0,
    ignore_robots: Annotated[
        bool,
        typer.Option("--ignore-robots", help="Skip robots.txt (authorized testing only)."),
    ] = False,
    skip_ocr: Annotated[
        bool,
        typer.Option("--skip-ocr", help="Skip OCR (fetch + image download only)."),
    ] = False,
    skip_vlm: Annotated[
        bool,
        typer.Option("--skip-vlm", help="Skip VLM classification stage."),
    ] = False,
    skip_synthesize: Annotated[
        bool,
        typer.Option(
            "--skip-synthesize",
            help="Skip end-of-crawl finding synthesis. Run `audit synthesize` later.",
        ),
    ] = False,
    skip_axe: Annotated[
        bool,
        typer.Option(
            "--skip-axe",
            help=(
                "Skip the WCAG axe-core DOM scan. The scan adds ~50-150 ms "
                "per Playwright-rendered page and is on by default."
            ),
        ),
    ] = False,
    axe_level: Annotated[
        str,
        typer.Option(
            "--axe-level",
            help="WCAG level filter for axe rules: A, AA (default), or AAA.",
        ),
    ] = "AA",
    skip_semantic: Annotated[
        bool,
        typer.Option(
            "--skip-semantic",
            help=(
                "Skip per-criterion semantic (LLM) analyzers. Each enabled "
                "criterion adds ~1 local Ollama call per page; default set "
                "is 10 criteria. Disable for fast iterations or when no "
                "Ollama daemon is reachable."
            ),
        ),
    ] = False,
    semantic_criteria: Annotated[
        str,
        typer.Option(
            "--semantic-criteria",
            help=(
                "Comma-separated WCAG SCs to evaluate (e.g. '2.4.4,1.3.1'). "
                "Empty = use the default Phase-9 wave-1 set."
            ),
        ),
    ] = "",
    keyboard_probe: Annotated[
        bool,
        typer.Option(
            "--keyboard-probe",
            help=(
                "Deprecated no-op: the SC 2.1.2 keyboard-trap probe now "
                "runs by default. Use --skip-keyboard to disable it."
            ),
        ),
    ] = False,
    skip_keyboard: Annotated[
        bool,
        typer.Option(
            "--skip-keyboard",
            help=(
                "Skip the SC 2.1.2 (No Keyboard Trap) dynamic probe. "
                "Saves ~1-3s per rendered page at the cost of losing "
                "bidirectional keyboard-exit review leads."
            ),
        ),
    ] = False,
    keyboard_max_focusable: Annotated[
        int,
        typer.Option(
            "--keyboard-max-focusable",
            min=5,
            max=500,
            help=(
                "Cap on how many focusable elements the keyboard probe "
                "tests per page. Default 50 covers realistic pages; raise "
                "for very dense forms, lower for fast iteration."
            ),
        ),
    ] = 50,
    skip_responsive: Annotated[
        bool,
        typer.Option(
            "--skip-responsive",
            help=(
                "Skip the responsive/zoom probe (320px reflow, ~200% zoom "
                "text clipping, WCAG text-spacing override). Saves ~1-2s "
                "per rendered page."
            ),
        ),
    ] = False,
    skip_focus: Annotated[
        bool,
        typer.Option(
            "--skip-focus",
            help=(
                "Skip the focus-obscured probe (SC 2.4.11 — focusable elements "
                "hidden behind sticky/fixed overlays)."
            ),
        ),
    ] = False,
    skip_visual: Annotated[
        bool,
        typer.Option(
            "--skip-visual",
            help=(
                "Skip the visual (VLM) probe (SC 1.3.2 Meaningful Sequence). "
                "Needs a local vision model; one screenshot + VLM call per page."
            ),
        ),
    ] = False,
    interaction: Annotated[
        bool,
        typer.Option(
            "--interaction",
            help=(
                "Operate each page's controls (menus, tabs, disclosure "
                "buttons) and re-run axe on every state a click reveals. "
                "Finds defects that do not exist until something is "
                "clicked. Off by default: it is the only pass that "
                "modifies the page, and it costs one axe run per revealed "
                "state. Never clicks a control whose name looks "
                "destructive (sign out, delete, remove)."
            ),
        ),
    ] = False,
    skip_screenshots: Annotated[
        bool,
        typer.Option(
            "--skip-screenshots",
            help=(
                "Skip capturing a circled location screenshot for each "
                "live-page finding. Those images are embedded in the Excel "
                "report as visual evidence; skipping saves crawl time."
            ),
        ),
    ] = False,
    use_js: Annotated[
        bool,
        typer.Option(
            "--use-js",
            help=(
                "Deprecated no-op: every page is rendered with Playwright "
                "by default now. Use --static-only for the fast path."
            ),
        ),
    ] = False,
    static_only: Annotated[
        bool,
        typer.Option(
            "--static-only",
            help=(
                "Fast link-inventory crawl: fetch pages with plain HTTP and "
                "skip browser rendering except for SPA/WAF pages. WARNING: "
                "disables axe, keyboard, and responsive checks on every "
                "statically-fetched page — image-of-text + semantic "
                "pipelines still run."
            ),
        ),
    ] = False,
    compare_to: Annotated[
        int | None,
        typer.Option(
            "--compare-to",
            help=(
                "Scan id to diff against. Defaults to auto-discovering the most "
                "recent completed scan of the same logical site (port-tolerant "
                "on loopback hosts)."
            ),
        ),
    ] = None,
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Verbose logging.")] = False,
) -> None:
    """Crawl a site and store page records in the audit DB."""
    _ = verbose  # structlog config will consume this in Phase 2+
    # Deprecated opt-ins that are now the defaults. Accept silently so
    # existing scripts keep working; the new opt-OUTs are authoritative.
    _ = use_js
    _ = keyboard_probe
    settings = get_settings()
    settings.ensure_dirs()
    conn = connect(settings.db_path)
    try:
        config = CrawlConfig(
            seed_url=url,
            max_pages=max_pages,
            max_depth=max_depth,
            allow_subdomains=include_subdomain,
            whole_host=whole_host,
            rps=rps,
            ignore_robots=ignore_robots,
            user_agent=settings.user_agent,
            request_timeout_s=settings.request_timeout_s,
            ocr_enabled=not skip_ocr,
            ocr_language=settings.ocr_language,
            ocr_max_workers=settings.ocr_max_workers,
            ocr_min_confidence=settings.ocr_min_confidence,
            ocr_min_word_count=settings.ocr_min_word_count,
            vlm_enabled=not skip_vlm,
            vlm_model=settings.vlm_model,
            vlm_base_url=settings.ollama_base_url,
            vlm_prompt_name=settings.vlm_prompt_name,
            vlm_concurrency=settings.vlm_concurrency,
            synthesize_enabled=not skip_synthesize,
            compare_to=compare_to,
            js_eager=not static_only,
            axe_enabled=not skip_axe,
            axe_level=axe_level.upper(),
            semantic_enabled=not skip_semantic,
            keyboard_probe_enabled=not skip_keyboard,
            keyboard_probe_max_focusable=keyboard_max_focusable,
            responsive_checks_enabled=not skip_responsive,
            focus_checks_enabled=not skip_focus,
            visual_checks_enabled=not skip_visual,
            interaction_checks_enabled=interaction,
            capture_screenshots=not skip_screenshots,
        )
        if static_only:
            console.print(
                "[yellow]--static-only:[/yellow] pages are fetched without a "
                "browser, so the axe, keyboard-trap, and responsive checks "
                "are skipped on statically-fetched pages. Re-run without "
                "--static-only for full coverage."
            )
        # Override the default semantic-criteria tuple when the user
        # passed `--semantic-criteria 2.4.4,1.3.1`. Dataclass is frozen,
        # so we rebuild it via `replace()` — the orchestrator validates
        # SC formatting and logs + drops any malformed entry.
        if semantic_criteria:
            from dataclasses import replace as _dc_replace

            config = _dc_replace(
                config,
                semantic_criteria=tuple(
                    s.strip() for s in semantic_criteria.split(",") if s.strip()
                ),
            )
        console.print(f"[cyan]Starting crawl[/cyan] of {url} (max_pages={max_pages})…")
        try:
            summary = asyncio.run(run_crawl(conn, config))
        except KeyboardInterrupt:
            console.print("[yellow]Interrupted.[/yellow] Run again to resume.")
            raise typer.Exit(code=130) from None
        _render_summary(conn, summary)
        if summary.status != "completed":
            raise typer.Exit(code=1)
    finally:
        conn.close()


def _render_summary(conn, summary: CrawlSummary) -> None:  # type: ignore[no-untyped-def]
    row = conn.execute(
        "SELECT page_count, error_count FROM scans WHERE id = ?", (summary.scan_id,)
    ).fetchone()

    table = Table(title=f"Crawl summary (scan #{summary.scan_id})", show_header=False)
    table.add_column("metric", style="bold")
    table.add_column("value", justify="right")
    table.add_row("Seed URL", summary.seed_url)
    table.add_row("Status", summary.status)
    table.add_row("Pages fetched", str(summary.pages_fetched))
    table.add_row("Pages in DB", str(row["page_count"] if row else 0))
    table.add_row("Images persisted", str(summary.images_persisted))
    if summary.svg_text_hits:
        table.add_row("Inline SVG text hits", str(summary.svg_text_hits))
    if summary.image_errors:
        table.add_row("Image download errors", str(summary.image_errors))
    if summary.ocr_analyzed:
        table.add_row("Images OCR'd", str(summary.ocr_analyzed))
        table.add_row("Text-candidate images", str(summary.ocr_text_candidates))
    if summary.vlm_classified:
        table.add_row("Images VLM-classified", str(summary.vlm_classified))
    if summary.vlm_errors:
        table.add_row("VLM errors", str(summary.vlm_errors))
    if summary.axe_pages_scanned:
        table.add_row("Pages axe-scanned (WCAG)", str(summary.axe_pages_scanned))
        table.add_row("Axe violations total", str(summary.axe_violations_total))
    if summary.keyboard_pages_probed:
        table.add_row("Pages keyboard-probed (SC 2.1.2)", str(summary.keyboard_pages_probed))
        table.add_row("Keyboard traps total", str(summary.keyboard_traps_total))
    if summary.responsive_pages_probed:
        table.add_row(
            "Pages responsive-probed (1.4.4/.10/.12)",
            str(summary.responsive_pages_probed),
        )
        table.add_row("Responsive findings total", str(summary.responsive_findings_total))
    if summary.focus_pages_probed:
        table.add_row("Pages focus-probed (SC 2.4.11)", str(summary.focus_pages_probed))
        table.add_row("Focus-obscured findings total", str(summary.focus_findings_total))
    if summary.visual_pages_probed:
        table.add_row("Pages visually probed (SC 1.3.2)", str(summary.visual_pages_probed))
        table.add_row("Visual-sequence findings total", str(summary.visual_findings_total))
    if summary.findings_written:
        table.add_row("Findings written", str(summary.findings_written))
        for level in ("critical", "major", "minor", "info"):
            count = summary.findings_by_severity.get(level, 0)
            if count:
                table.add_row(f"  {level}", str(count))
    if summary.compare_to_scan_id is not None:
        table.add_row("Compared against scan", f"#{summary.compare_to_scan_id}")
        table.add_row("  first-seen", str(summary.first_seen))
        table.add_row("  resolved", str(summary.resolved))
    table.add_row("Page errors", str(summary.errors))
    if summary.pages_skipped_robots:
        table.add_row("Skipped (robots.txt)", str(summary.pages_skipped_robots))
    console.print(table)


@app.command()
def synthesize(
    scan_id: Annotated[
        int | None,
        typer.Argument(help="Scan id to re-synthesize. Defaults to the latest scan."),
    ] = None,
    compare_to: Annotated[
        int | None,
        typer.Option(
            "--compare-to",
            help=(
                "Diff against this scan id and write first-seen / resolved rows "
                "to finding_history. Omit to skip history materialization."
            ),
        ),
    ] = None,
) -> None:
    """Re-compute findings for a scan without re-crawling."""
    settings = get_settings()
    conn = connect(settings.db_path)
    try:
        if scan_id is None:
            row = conn.execute("SELECT id FROM scans ORDER BY id DESC LIMIT 1").fetchone()
            if row is None:
                console.print("[yellow]No scans in the database.[/yellow]")
                raise typer.Exit(code=1)
            scan_id = int(row["id"])

        result = synthesize_findings(conn, scan_id=scan_id, compare_to=compare_to)
        conn.execute(
            "UPDATE scans SET finding_count = ? WHERE id = ?",
            (result.findings_written, scan_id),
        )

        table = Table(title=f"Synthesis complete (scan #{scan_id})", show_header=False)
        table.add_column("metric", style="bold")
        table.add_column("value", justify="right")
        table.add_row("Findings written", str(result.findings_written))
        for level in ("critical", "major", "minor", "info"):
            table.add_row(f"  {level}", str(result.by_severity.get(level, 0)))
        if compare_to is not None:
            table.add_row("Compared against scan", f"#{compare_to}")
            table.add_row("  first-seen", str(result.first_seen))
            table.add_row("  resolved", str(result.resolved))
        console.print(table)
    finally:
        conn.close()


_EXPORT_FORMATS = ("csv", "json", "jira", "markdown", "xlsx")
_EXPORT_EXT = {
    "csv": "csv",
    "json": "json",
    "jira": "jira.csv",
    "markdown": "md",
    "xlsx": "xlsx",
}


@app.command()
def export(
    scan_id: Annotated[
        int | None,
        typer.Argument(help="Scan id to export. Defaults to the latest scan."),
    ] = None,
    fmt: Annotated[
        str,
        typer.Option("--format", "-f", help="csv | json | jira | markdown | xlsx"),
    ] = "csv",
    output: Annotated[
        Path | None,
        typer.Option(
            "--output",
            "-o",
            help="Output file path. Omit to write under data/exports/scan_<id>.<ext>.",
        ),
    ] = None,
    ui_base: Annotated[
        str,
        typer.Option("--ui-base", help="Base URL used in deep links inside exports."),
    ] = "http://127.0.0.1:8765",
) -> None:
    """Write a scan's findings to CSV, JSON, Jira CSV, or a Markdown report."""
    fmt_lower = fmt.lower()
    if fmt_lower not in _EXPORT_FORMATS:
        console.print(
            f"[red]Unknown --format {fmt!r}.[/red] Use one of: {', '.join(_EXPORT_FORMATS)}."
        )
        raise typer.Exit(code=2)

    settings = get_settings()
    settings.ensure_dirs()
    conn = connect(settings.db_path)
    try:
        if scan_id is None:
            row = conn.execute("SELECT id FROM scans ORDER BY id DESC LIMIT 1").fetchone()
            if row is None:
                console.print("[yellow]No scans in the database.[/yellow]")
                raise typer.Exit(code=1)
            scan_id = int(row["id"])

        # The CLI has no identity-aware-proxy assertion or protected-report
        # permission. Never let its ordinary filesystem writers become a
        # bypass for authenticated-site evidence; the browser workflow has a
        # dedicated, explicit redacted in-memory download instead.
        protected = conn.execute(
            "SELECT 1 FROM protected_scans WHERE scan_id = ?", (scan_id,)
        ).fetchone()
        if protected is not None:
            console.print(
                "[red]Protected scans cannot be exported from the CLI.[/red] "
                "Use the identity-protected redacted export in the protected report UI."
            )
            raise typer.Exit(code=1)

        scan = collect_scan(conn, scan_id, ui_base_url=ui_base)
        rendered: str | bytes
        if fmt_lower == "xlsx":
            # xlsx builds its issue table live from the open connection;
            # the blob store lets it embed per-finding evidence screenshots.
            rendered = render_xlsx(scan, conn=conn, blob_store=BlobStore(get_settings().blob_dir))
        else:
            rendered = {
                "csv": render_csv,
                "json": render_json,
                "jira": render_jira_csv,
                "markdown": render_markdown,
            }[fmt_lower](scan)
    finally:
        conn.close()

    target = output or (settings.data_dir / "exports" / f"scan_{scan_id}.{_EXPORT_EXT[fmt_lower]}")
    target.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(rendered, bytes):
        target.write_bytes(rendered)
    else:
        target.write_text(rendered, encoding="utf-8")
    console.print(
        f"[green]Wrote[/green] {target}  ([cyan]{fmt_lower}[/cyan], {scan.finding_count} findings)"
    )


@app.command()
def serve(
    host: Annotated[str, typer.Option("--host", help="Bind address.")] = "127.0.0.1",
    port: Annotated[int, typer.Option("--port", min=1, max=65535, help="Bind port.")] = 8765,
    reload: Annotated[bool, typer.Option("--reload", help="Auto-reload on code change.")] = False,
) -> None:
    """Serve the local review UI at http://HOST:PORT."""
    import uvicorn

    settings = get_settings()
    settings.ensure_dirs()
    console.print(
        f"[cyan]Audit UI[/cyan] serving at http://{host}:{port}  (db: {settings.db_path})"
    )
    uvicorn.run(
        "audit.web.server:app",
        host=host,
        port=port,
        reload=reload,
        log_level="warning",
    )


@app.command()
def status() -> None:
    """Show status of the latest scan."""
    settings = get_settings()
    conn = connect(settings.db_path)
    try:
        row = conn.execute(
            "SELECT id, seed_url, status, page_count, error_count, finding_count, "
            "started_at, finished_at FROM scans ORDER BY id DESC LIMIT 1"
        ).fetchone()
        severities: dict[str, int] = {}
        if row is not None:
            cur = conn.execute(
                "SELECT severity, COUNT(*) AS n FROM findings WHERE scan_id = ? GROUP BY severity",
                (row["id"],),
            )
            severities = {r["severity"]: int(r["n"]) for r in cur}
    finally:
        conn.close()

    if row is None:
        console.print("[yellow]No scans yet.[/yellow]")
        raise typer.Exit(code=1)

    table = Table(title=f"Scan #{row['id']}", show_header=False)
    table.add_column("metric", style="bold")
    table.add_column("value")
    table.add_row("Seed URL", row["seed_url"])
    table.add_row("Status", row["status"])
    table.add_row("Pages", str(row["page_count"]))
    table.add_row("Errors", str(row["error_count"]))
    table.add_row("Findings", str(row["finding_count"]))
    for level in ("critical", "major", "minor", "info"):
        if severities.get(level):
            table.add_row(f"  {level}", str(severities[level]))
    table.add_row("Started", str(row["started_at"]))
    table.add_row("Finished", str(row["finished_at"] or "-"))
    console.print(table)


def companion_main() -> None:
    """Run the standalone local companion command.

    This is intentionally a narrow alias for ``audit protected-companion``:
    it exposes only the pre-bound pairing and headed manual-authentication
    subcommands, rather than the public crawler, exports, or database tools.
    """

    protected_companion_app()


if __name__ == "__main__":
    app()
