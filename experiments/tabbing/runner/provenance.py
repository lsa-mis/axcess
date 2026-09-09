"""Source fingerprints and output rules shared by the two experiment CLIs."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections.abc import Callable
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


def directory_sha256(root: Path) -> dict[str, str]:
    files = {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*.py"))
    }
    digest = hashlib.sha256(
        json.dumps(files, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return {**files, "_combined": digest}


def source_sha256(repo_root: Path = REPO_ROOT) -> dict[str, dict[str, str]]:
    return {
        "detector": directory_sha256(repo_root / "src/audit/analyzer/keyboard/kbdiff"),
        "runner": directory_sha256(repo_root / "experiments/tabbing/runner"),
    }


def safe_label(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", value):
        raise argparse.ArgumentTypeError(
            "label must be 1-64 letters, digits, underscores or hyphens, "
            "starting with a letter/digit"
        )
    return value


def bounded_int(minimum: int, maximum: int) -> Callable[[str], int]:
    def parse(value: str) -> int:
        try:
            result = int(value)
        except ValueError as exc:
            raise argparse.ArgumentTypeError("expected an integer") from exc
        if not minimum <= result <= maximum:
            raise argparse.ArgumentTypeError(f"must be between {minimum} and {maximum}")
        return result

    return parse


def require_new_outputs(*paths: Path) -> None:
    for path in paths:
        if path.exists():
            raise FileExistsError(f"refusing to overwrite {path}; use a new --label or --out")


def write_new(path: Path, content: str) -> None:
    """Exclusive creation also protects a run that starts during measurement."""
    with path.open("x", encoding="utf-8") as handle:
        handle.write(content)
