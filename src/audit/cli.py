"""Command-line interface for the audit tool."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from audit.config import get_settings
from audit.crawler.orchestrator import CrawlConfig, CrawlSummary, run_crawl
from audit.db.schema import connect
from audit.exports.collector import collect_scan
from audit.exports.csv_export import render_csv
from audit.exports.jira_export import render_jira_csv
from audit.exports.json_export import render_json
from audit.exports.markdown_report import render_markdown
from audit.synthesizer.findings import synthesize_findings

app = typer.Typer(
    help=(
        "AccessibleAccessibility — local, offline web accessibility auditor "
        "(images-of-text detection, keyboard-trap probing, and more)."
    ),
    no_args_is_help=True,
    add_completion=False,
)
console = Console()


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
    use_js: Annotated[
        bool,
        typer.Option(
            "--use-js",
            help=(
                "Render every page with Playwright (chromium). Slower but "
                "handles SPAs and sites behind Cloudflare / WAF challenges. "
                "Auto-escalation on challenge pages happens either way."
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
            js_eager=use_js,
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


_EXPORT_FORMATS = ("csv", "json", "jira", "markdown")
_EXPORT_EXT = {"csv": "csv", "json": "json", "jira": "jira.csv", "markdown": "md"}


@app.command()
def export(
    scan_id: Annotated[
        int | None,
        typer.Argument(help="Scan id to export. Defaults to the latest scan."),
    ] = None,
    fmt: Annotated[
        str,
        typer.Option("--format", "-f", help="csv | json | jira | markdown"),
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

        scan = collect_scan(conn, scan_id, ui_base_url=ui_base)
    finally:
        conn.close()

    rendered = {
        "csv": render_csv,
        "json": render_json,
        "jira": render_jira_csv,
        "markdown": render_markdown,
    }[fmt_lower](scan)

    target = output or (settings.data_dir / "exports" / f"scan_{scan_id}.{_EXPORT_EXT[fmt_lower]}")
    target.parent.mkdir(parents=True, exist_ok=True)
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


if __name__ == "__main__":
    app()
