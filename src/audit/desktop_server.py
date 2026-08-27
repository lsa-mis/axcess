"""Desktop-owned Axcess server entry point.

The Electron shell launches this module as a child process.  It applies the
bundled migrations before accepting requests, then binds exclusively to the
loopback address selected by the shell.  Runtime paths are supplied through
the normal ``AUDIT_*`` settings so desktop data never lands inside the signed
application bundle.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

import uvicorn
from yoyo import get_backend, read_migrations

from audit.config import get_settings


def bundled_migrations_dir() -> Path:
    """Return the migrations shipped with the Python package or executable."""

    return Path(__file__).resolve().parent / "db" / "migrations"


def apply_desktop_migrations(db_path: Path, migrations_dir: Path | None = None) -> None:
    """Bring a desktop database forward before the web application imports."""

    source = (migrations_dir or bundled_migrations_dir()).resolve()
    if not source.is_dir():
        raise RuntimeError(f"Bundled database migrations are missing: {source}")

    resolved_db = db_path.expanduser().resolve()
    resolved_db.parent.mkdir(parents=True, exist_ok=True)
    backend = get_backend(f"sqlite:///{resolved_db.as_posix()}")
    migrations = read_migrations(str(source))
    with backend.lock():
        backend.apply_migrations(backend.to_apply(migrations))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the Axcess desktop backend.")
    parser.add_argument("--host", default="127.0.0.1")
    launch = parser.add_mutually_exclusive_group(required=True)
    launch.add_argument("--port", type=int)
    launch.add_argument(
        "--verify-runtime",
        action="store_true",
        help="verify bundled backend, browser, Alfa, and OCR dependencies, then exit",
    )
    return parser


async def verify_runtime() -> dict[str, str]:
    """Exercise every external runtime required by a packaged desktop scan."""

    def progress(component: str) -> None:
        print(f"Verifying packaged {component}...", file=sys.stderr, flush=True)

    from PIL import Image
    from playwright.async_api import async_playwright

    from audit.analyzer.alfa import AlfaAnalyzer, availability, chromium_executable_path
    from audit.analyzer.ocr.tesseract import run_tesseract
    from audit.crawler import url_policy

    progress("application assets")
    package_dir = Path(__file__).resolve().parent
    required_assets = {
        "axe_core": package_dir / "web" / "static" / "axe.min.js",
        "frontend": package_dir / "web" / "frontend" / "dist" / "index.html",
        "migrations": package_dir / "db" / "migrations",
        "rules": package_dir / "rules",
        "alfa_runner": package_dir / "alfa_runner" / "runner.mjs",
        "alfa_modules": package_dir / "alfa_runner" / "node_modules" / "@siteimprove" / "alfa-act",
    }
    missing = [name for name, path in required_assets.items() if not path.exists()]
    if missing:
        raise RuntimeError(f"Bundled desktop assets are missing: {', '.join(missing)}")

    progress("URL scope")
    scope = url_policy.build_scope("https://subdomain.example.edu/section/")
    if scope.seed_host != "subdomain.example.edu" or scope.path_prefix != "/section/":
        raise RuntimeError("Bundled URL scope dependencies could not initialize.")

    progress("Alfa availability")
    alfa_state = availability()
    if not alfa_state.available:
        raise RuntimeError(alfa_state.reason or "The bundled Alfa engine is unavailable.")

    progress("Chromium and axe-core")
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        try:
            page = await browser.new_page()
            await page.set_content("<main><h1>Axcess runtime check</h1></main>")
            heading = await page.locator("h1").inner_text()
            if heading != "Axcess runtime check":
                raise RuntimeError("Bundled Chromium did not render the verification page.")
            axe_source = required_assets["axe_core"].read_text(encoding="utf-8")
            await page.evaluate(axe_source)
            axe_version = await page.evaluate("window.axe && window.axe.version")
            if not isinstance(axe_version, str) or not axe_version:
                raise RuntimeError("Bundled axe-core rules could not run in Chromium.")
        finally:
            await browser.close()

    progress("Alfa browser analysis")
    chromium_path = await chromium_executable_path()
    if chromium_path is None:
        raise RuntimeError("Bundled Chromium executable could not be resolved for Alfa.")
    alfa = AlfaAnalyzer(
        user_agent="Axcess desktop runtime verification",
        chromium_path=chromium_path,
    )

    async def serve_alfa_fixture(
        reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        try:
            await reader.read(4096)
            body = b"<!doctype html><html lang=en><title>Axcess</title><main>Alfa check</main>"
            writer.write(
                b"HTTP/1.1 200 OK\r\n"
                b"Content-Type: text/html; charset=utf-8\r\n"
                + f"Content-Length: {len(body)}\r\n".encode()
                + b"Connection: close\r\n\r\n"
                + body
            )
            await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()

    fixture_server = await asyncio.start_server(serve_alfa_fixture, "127.0.0.1", 0)
    try:
        fixture_address = fixture_server.sockets[0].getsockname()
        await alfa.run(f"http://127.0.0.1:{fixture_address[1]}/", level="AA")
    finally:
        fixture_server.close()
        await fixture_server.wait_closed()

    import io

    progress("Tesseract OCR")
    image_buffer = io.BytesIO()
    Image.new("RGB", (120, 40), "white").save(image_buffer, format="PNG")
    ocr = run_tesseract(image_buffer.getvalue(), "eng")
    if "unknown" in ocr.engine_version:
        raise RuntimeError("Bundled Tesseract OCR executable is unavailable.")

    from openpyxl import Workbook

    progress("Excel report generation")
    workbook_buffer = io.BytesIO()
    workbook = Workbook()
    workbook.active["A1"] = "Axcess report runtime check"
    workbook.save(workbook_buffer)
    if not workbook_buffer.getvalue().startswith(b"PK"):
        raise RuntimeError("Bundled Excel report engine could not create a workbook.")

    # Importing the application validates FastAPI and all report/export module
    # imports after migrations have established the packaged schema.
    progress("FastAPI application")
    from audit.web.server import app

    if app.title != "Axcess":
        raise RuntimeError("Packaged FastAPI application could not be initialized.")

    return {
        "alfa": "available",
        "axe_core": "available",
        "axe_core_version": axe_version,
        "chromium": "available",
        "frontend": "available",
        "ocr": ocr.engine_version,
        "python_backend": "available",
        "reports": "available",
        "url_scope": "available",
    }


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    if args.verify_runtime:
        settings = get_settings()
        settings.ensure_dirs()
        apply_desktop_migrations(settings.db_path)
        print(json.dumps(asyncio.run(verify_runtime()), sort_keys=True))
        return
    if args.host not in {"127.0.0.1", "::1", "localhost"}:
        raise SystemExit("The desktop backend may only bind to the loopback interface.")
    if args.port is None:  # pragma: no cover - enforced by argparse
        raise SystemExit("Desktop backend port is required.")
    if not 1 <= args.port <= 65535:
        raise SystemExit("Desktop backend port must be between 1 and 65535.")

    settings = get_settings()
    settings.ensure_dirs()
    apply_desktop_migrations(settings.db_path)

    # Import only after migrations and directory setup. ``server`` constructs
    # its module-level FastAPI application using the current AUDIT_* settings.
    from audit.web.server import app

    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        log_level="warning",
        access_log=False,
    )


if __name__ == "__main__":
    main()
