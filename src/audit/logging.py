"""Structured logging setup using structlog.

Logs go to stderr and, when a directory is given, to a rotating file. The
file matters: a desktop scan runs inside Electron, where stderr is not
something the auditor can reach. Without it the only record of a scan was
whatever could be reconstructed from database rows afterwards, which is how
three consecutive failed sign-in scans were diagnosed by comparing HTML
hashes rather than by reading what happened.
"""

from __future__ import annotations

import logging
import logging.handlers
import sys
from pathlib import Path
from typing import Any

import structlog

# One scan's worth of page-level lines is small; keeping a few rotations
# means a failure can still be inspected after a couple of later runs.
_MAX_LOG_BYTES = 5_000_000
_LOG_BACKUPS = 3
LOG_FILENAME = "axcess.log"


def configure_logging(verbose: bool = False, log_dir: Path | None = None) -> Path | None:
    """Configure stdlib + structlog. Idempotent; safe to call repeatedly.

    Returns the log file path when file logging was established, so a caller
    can tell the user where to look.
    """
    level = logging.DEBUG if verbose else logging.INFO
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stderr)]
    log_path: Path | None = None
    if log_dir is not None:
        try:
            log_dir.mkdir(parents=True, exist_ok=True)
            log_path = log_dir / LOG_FILENAME
            handlers.append(
                logging.handlers.RotatingFileHandler(
                    log_path,
                    maxBytes=_MAX_LOG_BYTES,
                    backupCount=_LOG_BACKUPS,
                    encoding="utf-8",
                )
            )
        except OSError:
            # A log file is diagnostic, never a precondition for scanning.
            log_path = None

    logging.basicConfig(format="%(message)s", level=level, handlers=handlers, force=True)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            # No colour: the same rendered line goes to the file, and escape
            # codes there make it unreadable in an editor.
            structlog.dev.ConsoleRenderer(colors=False),
        ],
        # Route through stdlib so both handlers above receive every line.
        # structlog's default factory prints directly and bypasses them,
        # which is why nothing ever reached the configured log directory.
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.make_filtering_bound_logger(level),
        cache_logger_on_first_use=False,
    )
    return log_path


def get_logger(name: str | None = None) -> Any:
    """Return a structlog bound logger."""
    return structlog.get_logger(name)
