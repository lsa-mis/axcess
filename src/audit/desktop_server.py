"""Desktop-owned Axcess server entry point.

The Electron shell launches this module as a child process.  It applies the
bundled migrations before accepting requests, then binds exclusively to the
loopback address selected by the shell.  Runtime paths are supplied through
the normal ``AUDIT_*`` settings so desktop data never lands inside the signed
application bundle.
"""

from __future__ import annotations

import argparse
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
    parser.add_argument("--port", type=int, required=True)
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    if args.host not in {"127.0.0.1", "::1", "localhost"}:
        raise SystemExit("The desktop backend may only bind to the loopback interface.")
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
