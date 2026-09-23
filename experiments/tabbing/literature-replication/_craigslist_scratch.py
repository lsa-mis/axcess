"""Scratch: list every changed KAFE-MATRIX.md table cell, old -> new. Safe to delete."""
import pathlib
import re
import subprocess

HERE = pathlib.Path(__file__).parent


def tables(text: str) -> list[tuple[list[str], dict[str, list[str]]]]:
    out, header, rows = [], None, {}
    for line in text.splitlines() + [""]:
        if line.startswith("|"):
            cells = [c.strip() for c in re.split(r"(?<!\\)\|", line)[1:-1]]
            if header is None:
                header = cells
            elif not set("".join(cells)) <= set("-: "):
                rows[cells[0]] = cells
        elif header is not None:
            out.append((header, rows))
            header, rows = None, {}
    return out


old = tables(subprocess.run(["git", "show", "HEAD:./KAFE-MATRIX.md"], cwd=HERE,
                            capture_output=True, text=True, check=True).stdout)
new = tables((HERE / "KAFE-MATRIX.md").read_text())
for (h_old, r_old), (h_new, r_new) in zip(old, new):
    if h_old != h_new:
        print("HEADER", " | ".join(f"{a} → {b}" for a, b in zip(h_old, h_new) if a != b))
    for key in r_old:
        a, b = r_old[key], r_new.get(key)
        if b is None:
            print("ROW GONE", key)
            continue
        diffs = [f"{h}: {x} → {y}" for h, x, y in zip(h_new, a, b) if x != y]
        if diffs:
            print(f"- **{key}** — " + "; ".join(diffs))
