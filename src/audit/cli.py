"""Command-line interface for the audit tool."""

from __future__ import annotations

from typing import Annotated

import typer
from rich.console import Console

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
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Verbose logging.")] = False,
) -> None:
    """Crawl a site and store pages, images, and context. (Phase 1 — not yet implemented.)"""
    _ = (
        url,
        max_pages,
        max_depth,
        include_subdomain,
        rps,
        ignore_robots,
        verbose,
    )  # silence unused until Phase 1 lands
    console.print(
        f"[yellow]Not yet implemented.[/yellow] Would crawl {url!r} "
        f"(max_pages={max_pages}, depth={max_depth})."
    )
    raise typer.Exit(code=1)


@app.command()
def status() -> None:
    """Show status of the latest scan. (Phase 1 — not yet implemented.)"""
    console.print("[yellow]Not yet implemented.[/yellow]")
    raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
