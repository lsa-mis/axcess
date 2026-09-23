"""Committed golden files for the web API characterization tests.

The goldens under ``golden/`` pin what the FastAPI app exposes today so a
refactor of ``create_app()`` can be shown to leave it unchanged. They are
only ever rewritten on purpose: set ``AXCESS_UPDATE_GOLDEN=1`` and the tests
write what they observe instead of comparing, then skip so the run cannot be
mistaken for a pass. A missing golden is a failure, never a silent pass.

Failures carry a unified diff of the pretty-printed JSON rather than a bare
``assert``: this module is not rewritten by pytest, and a structural diff of
two large documents is the only readable form anyway.
"""

from __future__ import annotations

import difflib
import json
import os
from pathlib import Path
from typing import Any

import pytest

GOLDEN_DIR = Path(__file__).resolve().parent / "golden"
UPDATE_ENV = "AXCESS_UPDATE_GOLDEN"
_MAX_DIFF_LINES = 200
_INLINE_WIDTH = 100


def _regenerate_hint() -> str:
    return (
        f"Regenerate with `{UPDATE_ENV}=1 uv run pytest tests/ui/test_api_surface.py "
        "tests/ui/test_api_contract.py` and review the golden diff before committing it."
    )


def _updating() -> bool:
    return os.environ.get(UPDATE_ENV) == "1"


def _format(value: Any, indent: int) -> str:
    # Like ``json.dumps(indent=2)``, except a container that fits on one line
    # stays on one line, so short records and parameter lists are one diff
    # line instead of a dozen. Key order is kept as given: it is part of what is
    # pinned (OpenAPI path order follows route registration order).
    inline = json.dumps(value, ensure_ascii=False)
    if not isinstance(value, dict | list) or not value or indent + len(inline) <= _INLINE_WIDTH:
        return inline
    pad = " " * (indent + 2)
    if isinstance(value, dict):
        items = [
            f"{pad}{json.dumps(key, ensure_ascii=False)}: {_format(item, indent + 2)}"
            for key, item in value.items()
        ]
        return "{\n" + ",\n".join(items) + "\n" + " " * indent + "}"
    items = [f"{pad}{_format(item, indent + 2)}" for item in value]
    return "[\n" + ",\n".join(items) + "\n" + " " * indent + "]"


def _pretty(data: Any) -> str:
    return _format(data, 0) + "\n"


def _load(name: str) -> Any:
    path = GOLDEN_DIR / name
    if not path.is_file():
        pytest.fail(f"Golden file {path} is missing. {_regenerate_hint()}", pytrace=False)
    return json.loads(path.read_text(encoding="utf-8"))


def _write(name: str, data: Any) -> None:
    GOLDEN_DIR.mkdir(exist_ok=True)
    (GOLDEN_DIR / name).write_text(_pretty(data), encoding="utf-8")


def _changed_entries(expected: Any, actual: Any) -> str:
    # A diff hunk can sit far below the key that owns it (an endpoint label,
    # "routes"), so name the top-level entries that changed up front.
    if not (isinstance(expected, dict) and isinstance(actual, dict)):
        return ""
    keys = [*expected, *(key for key in actual if key not in expected)]
    missing = object()
    changed = [key for key in keys if expected.get(key, missing) != actual.get(key, missing)]
    if not changed:
        return "Same content, different key order (route registration order, say).\n"
    return f"Changed entries: {', '.join(changed)}\n"


def _diff(expected: Any, actual: Any, label: str) -> str:
    lines = list(
        difflib.unified_diff(
            _pretty(expected).splitlines(),
            _pretty(actual).splitlines(),
            fromfile=f"golden {label}",
            tofile=f"observed {label}",
            lineterm="",
        )
    )
    if len(lines) > _MAX_DIFF_LINES:
        lines = [*lines[:_MAX_DIFF_LINES], f"... {len(lines) - _MAX_DIFF_LINES} more diff lines"]
    return _changed_entries(expected, actual) + "\n".join(lines)


def check_golden_entry(name: str, key: str, actual: Any) -> None:
    """Compare ``actual`` with ``golden[name][key]``, or record it when updating."""
    if _updating():
        path = GOLDEN_DIR / name
        existing = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
        existing[key] = actual
        _write(name, dict(sorted(existing.items())))
        pytest.skip(f"Wrote {name} [{key}]; rerun without {UPDATE_ENV} to verify.")
    golden = _load(name)
    if key not in golden:
        pytest.fail(f"Golden {name} has no entry {key!r}. {_regenerate_hint()}", pytrace=False)
    if actual != golden[key]:
        pytest.fail(
            f"{name} [{key}] no longer matches the golden.\n"
            f"{_diff(golden[key], actual, key)}\nIf the change is intended: {_regenerate_hint()}",
            pytrace=False,
        )


def check_golden_document(name: str, actual: Any) -> None:
    """Require ``json.dumps(actual)`` to equal the golden's exactly, key order included."""
    if _updating():
        _write(name, actual)
        pytest.skip(f"Wrote {name}; rerun without {UPDATE_ENV} to verify.")
    expected = _load(name)
    # Reloading a pretty-printed dump and dumping it compactly reproduces the
    # original compact string, so this is the exact-string comparison.
    if json.dumps(actual) != json.dumps(expected):
        pytest.fail(
            f"{name} no longer matches the golden exactly.\n"
            f"{_diff(expected, actual, name)}\nIf the change is intended: {_regenerate_hint()}",
            pytrace=False,
        )
