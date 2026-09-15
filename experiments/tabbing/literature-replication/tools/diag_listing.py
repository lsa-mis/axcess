"""One-off: print the real token order in a Drive listing so the parser can match it."""

from __future__ import annotations

from tools import drivemeta

page = drivemeta.read_text(
    drivemeta.folder_url(drivemeta.__dict__.get("_", "") or "1pU6osxQUgAH6EfZ93sMcG9LPxgwstUYS"),
    drivemeta.ByteBudget(limit=5_000_000),
)

tokens = []
for m in drivemeta._TOKEN_RE.finditer(page):
    kind = "ID" if m.group(1) is not None else "LB"
    tokens.append((m.start(), kind, m.group(1) or m.group(2)))

print(f"{len(page)} bytes, {len(tokens)} tokens")
start = next(
    (i for i, t in enumerate(tokens) if t[2] and "citiprogram" in str(t[2])), None
)
print("citiprogram first seen at token", start)
lo = max(0, (start or 0) - 12)
for pos, kind, val in tokens[lo : (start or 0) + 12]:
    print(f"  {pos:>8} {kind} {str(val)[:90]!r}")
