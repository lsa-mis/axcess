"""Command-line interface for the audit tool."""

from __future__ import annotations

import asyncio
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from audit.config import get_settings
from audit.crawler.orchestrator import CrawlConfig, CrawlSummary, run_crawl
from audit.db.schema import connect

app = typer.Typer(
    help="Local offline web accessibility auditor for WCAG 1.4.5 (Images of Text).",
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
            rps=rps,
            ignore_robots=ignore_robots,
            user_agent=settings.user_agent,
            request_timeout_s=settings.request_timeout_s,
            ocr_enabled=not skip_ocr,
            ocr_language=settings.ocr_language,
            ocr_max_workers=settings.ocr_max_workers,
            ocr_min_confidence=settings.ocr_min_confidence,
            ocr_min_word_count=settings.ocr_min_word_count,
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
    table.add_row("Page errors", str(summary.errors))
    if summary.pages_skipped_robots:
        table.add_row("Skipped (robots.txt)", str(summary.pages_skipped_robots))
    console.print(table)


@app.command()
def status() -> None:
    """Show status of the latest scan."""
    settings = get_settings()
    conn = connect(settings.db_path)
    try:
        row = conn.execute(
            "SELECT id, seed_url, status, page_count, error_count, started_at, finished_at "
            "FROM scans ORDER BY id DESC LIMIT 1"
        ).fetchone()
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
    table.add_row("Started", str(row["started_at"]))
    table.add_row("Finished", str(row["finished_at"] or "-"))
    console.print(table)


if __name__ == "__main__":
    app()
