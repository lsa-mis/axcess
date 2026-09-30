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
import signal
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import IO, Any

import uvicorn
from yoyo import get_backend, read_migrations

from audit.config import get_settings


def bundled_migrations_dir() -> Path:
    """Return the migrations shipped with the Python package or executable."""

    return Path(__file__).resolve().parent / "db" / "migrations"


def _try_lock_file(handle: IO[bytes]) -> None:
    """Take a non-blocking exclusive lock; raises ``OSError`` when it is held."""

    handle.seek(0)
    if sys.platform == "win32":
        import msvcrt

        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
    else:
        import fcntl

        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


def _unlock_file(handle: IO[bytes]) -> None:
    handle.seek(0)
    if sys.platform == "win32":
        import msvcrt

        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl

        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


@contextmanager
def exclusive_migration_lock(db_path: Path, timeout: float = 30.0) -> Iterator[None]:
    """Serialize desktop migrations with a lock the OS releases on process death.

    yoyo records its own lock as a database row, which outlives a backend that
    is killed while holding it and then blocks every later launch.  A file lock
    cannot be abandoned that way, so it is the authority here.
    """

    lock_path = db_path.with_name(f"{db_path.name}.migrate.lock")
    with open(lock_path, "a+b") as handle:
        deadline = time.monotonic() + timeout
        while True:
            try:
                _try_lock_file(handle)
                break
            except OSError as error:
                if time.monotonic() >= deadline:
                    raise RuntimeError(
                        "Another Axcess process is still updating the database."
                    ) from error
                time.sleep(0.2)
        try:
            yield
        finally:
            _unlock_file(handle)


def release_abandoned_migration_lock(backend: Any) -> None:
    """Drop a yoyo lock row; call only while holding the migration file lock.

    With the file lock held no other desktop backend can be migrating, so any
    row still present was left by a process that died before removing it.
    """

    row = backend.execute("SELECT pid FROM yoyo_lock").fetchone()
    backend.rollback()
    if row is None:
        return
    print(
        f"Releasing migration lock left by exited process {row[0]}.",
        file=sys.stderr,
        flush=True,
    )
    backend.break_lock()


def apply_desktop_migrations(
    db_path: Path,
    migrations_dir: Path | None = None,
    lock_timeout: float = 30.0,
) -> None:
    """Bring a desktop database forward before the web application imports."""

    source = (migrations_dir or bundled_migrations_dir()).resolve()
    if not source.is_dir():
        raise RuntimeError(f"Bundled database migrations are missing: {source}")

    resolved_db = db_path.expanduser().resolve()
    resolved_db.parent.mkdir(parents=True, exist_ok=True)
    with exclusive_migration_lock(resolved_db, lock_timeout):
        backend = get_backend(f"sqlite:///{resolved_db.as_posix()}")
        migrations = read_migrations(str(source))
        release_abandoned_migration_lock(backend)
        with backend.lock():
            backend.apply_migrations(backend.to_apply(migrations))


def exit_cleanly_on_terminate() -> None:
    """Turn SIGTERM into ``SystemExit`` so startup cleanup runs when the shell quits.

    Python's default SIGTERM action ends the process without unwinding, which
    skips the migration lock's cleanup.  uvicorn installs its own handlers once
    it is serving.
    """

    def _terminate(_signum: int, _frame: object) -> None:
        raise SystemExit(143)

    signal.signal(signal.SIGTERM, _terminate)


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

    await alfa.run("http://axcess-runtime.invalid/", level="AA")

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

    exit_cleanly_on_terminate()
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
