"""Store one golden as the difference from another, as a unified diff.

A draft export is its final export plus draft labeling: a notice, an extra
column, a front sheet. Committing both in full doubled the export goldens
for a few lines of labeling. ``make_delta`` records only that difference,
in the unified diff format ``diff -u`` and ``patch`` use, so it reads like
any other diff in review, and ``apply_delta`` turns the final back into the
draft. ``tests/unit/test_export_goldens.py`` then checks a draft as
``draft == apply_delta(final, recorded delta)``.

The format is exact, not just readable:

* Lines split on ``"\\n"`` only, and each keeps its ending, so a ``"\\r\\n"``
  row ending or a bare ``"\\r"`` inside a CSV field comes back byte for byte.
  (``str.splitlines`` would also split on ``"\\r"``, form feeds and more.)
* A last line without a newline is followed by the usual
  ``\\ No newline at end of file`` marker.
* ``apply_delta`` is strict. Every hunk must start at the line its header
  names, every context and removed line must match the text it is applied
  to exactly, and the line counts must agree with the header. A delta that
  no longer fits its base raises ``DeltaError``. Unlike ``patch``, it never
  retries a hunk at an offset or with fuzz.
"""

from __future__ import annotations

import difflib
import re

NO_NEWLINE = "\\ No newline at end of file\n"

_HUNK_HEADER = re.compile(r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@\n")


class DeltaError(ValueError):
    """A delta that is malformed or does not fit the text it is applied to."""


def split_lines(text: str) -> list[str]:
    """Split on ``"\\n"`` only, keeping it; ``"".join`` gives ``text`` back."""
    parts = text.split("\n")
    lines = [part + "\n" for part in parts[:-1]]
    if parts[-1]:
        lines.append(parts[-1])
    return lines


def make_delta(before: str, after: str, *, before_name: str, after_name: str, context: int) -> str:
    """The unified diff that turns ``before`` into ``after``; ``""`` if they are equal."""
    old, new = split_lines(before), split_lines(after)
    matcher = difflib.SequenceMatcher(None, old, new, autojunk=False)
    out: list[str] = []
    for group in matcher.get_grouped_opcodes(context):
        if not out:
            out += [f"--- {before_name}\n", f"+++ {after_name}\n"]
        first, last = group[0], group[-1]
        out.append(f"@@ -{_range(first[1], last[2])} +{_range(first[3], last[4])} @@\n")
        for tag, i1, i2, j1, j2 in group:
            if tag == "equal":
                out += [_body(" ", line) for line in old[i1:i2]]
                continue
            if tag in {"replace", "delete"}:
                out += [_body("-", line) for line in old[i1:i2]]
            if tag in {"replace", "insert"}:
                out += [_body("+", line) for line in new[j1:j2]]
    return "".join(out)


def apply_delta(before: str, delta: str) -> str:
    """Apply a ``make_delta`` diff to ``before``, strictly (see the module docstring)."""
    if not delta:
        return before
    old = split_lines(before)
    lines = split_lines(delta)
    if len(lines) < 3 or not lines[0].startswith("--- ") or not lines[1].startswith("+++ "):
        raise DeltaError("a delta starts with '--- ' and '+++ ' header lines and has a hunk")
    out: list[str] = []
    position = 0  # the next line of ``old`` not yet copied or consumed
    index = 2
    while index < len(lines):
        header = _HUNK_HEADER.fullmatch(lines[index])
        if header is None:
            raise DeltaError(
                f"delta line {index + 1}: expected a hunk header, got {lines[index]!r}"
            )
        old_start, old_count, new_start, new_count = _counts(header)
        # An empty range names the line before it, so it is already 0-based.
        start = old_start - 1 if old_count else old_start
        if start < position or start > len(old):
            raise DeltaError(f"delta line {index + 1}: hunk at line {old_start} is out of order")
        out += old[position:start]
        position = start
        if len(out) != (new_start - 1 if new_count else new_start):
            raise DeltaError(f"delta line {index + 1}: hunk lands at line {len(out) + 1}")
        index += 1
        consumed = produced = 0  # lines of the base read, lines of the result written
        while consumed < old_count or produced < new_count:
            if index >= len(lines):
                raise DeltaError("the delta ends inside a hunk")
            tag, text = lines[index][:1], lines[index][1:]
            index += 1
            if index < len(lines) and lines[index] == NO_NEWLINE:
                if not text.endswith("\n"):
                    raise DeltaError(f"delta line {index}: a malformed no-newline marker")
                text = text[:-1]
                index += 1
            if tag == "+":
                out.append(text)
                produced += 1
                continue
            if tag not in {" ", "-"}:
                raise DeltaError(f"delta line {index}: unexpected hunk line {lines[index - 1]!r}")
            if position >= len(old) or old[position] != text:
                found = old[position] if position < len(old) else "end of text"
                raise DeltaError(
                    f"delta line {index}: line {position + 1} does not match; "
                    f"expected {text!r}, found {found!r}"
                )
            if tag == " ":
                out.append(text)
                produced += 1
            consumed += 1
            position += 1
        if consumed != old_count or produced != new_count:
            raise DeltaError(f"delta line {index}: the hunk's line counts disagree with its header")
    out += old[position:]
    return "".join(out)


def _range(start: int, stop: int) -> str:
    """A hunk range in unified diff form, as ``difflib.unified_diff`` writes it."""
    length = stop - start
    if length == 1:
        return str(start + 1)
    # An empty range names the line just before it.
    return f"{start + 1 if length else start},{length}"


def _body(tag: str, line: str) -> str:
    return f"{tag}{line}" if line.endswith("\n") else f"{tag}{line}\n{NO_NEWLINE}"


def _counts(header: re.Match[str]) -> tuple[int, int, int, int]:
    old_start, old_count, new_start, new_count = header.groups()
    return (
        int(old_start),
        1 if old_count is None else int(old_count),
        int(new_start),
        1 if new_count is None else int(new_count),
    )
