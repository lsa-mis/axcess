"""Tiny WCAG contrast-ratio helper.

Used in Phase 2 to verify that re-picked design tokens meet AAA (7:1 for
normal text, 3:1 for non-text / focus indicators). Not part of the test
suite — kept here so future token tweaks have a one-shot way to check.

    python audits/contrast_helper.py            # prints the canonical token matrix
    python audits/contrast_helper.py FG BG      # prints the ratio for one pair

The matrix at the bottom mirrors what `tailwind.config.ts` and
`static/styles.css` declare; if you add or change a token, add the pair
here and re-run.
"""

from __future__ import annotations

import sys


def srgb_to_linear(channel_8bit: int) -> float:
    c = channel_8bit / 255
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def luminance(hex_color: str) -> float:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return 0.2126 * srgb_to_linear(r) + 0.7152 * srgb_to_linear(g) + 0.0722 * srgb_to_linear(b)


def contrast(c1: str, c2: str) -> float:
    l1, l2 = luminance(c1), luminance(c2)
    if l1 < l2:
        l1, l2 = l2, l1
    return (l1 + 0.05) / (l2 + 0.05)


def grade(ratio: float, *, large_text: bool = False) -> str:
    """Return AAA / AA / fail label per WCAG 1.4.6 (AAA) and 1.4.3 (AA)."""
    aaa_threshold = 4.5 if large_text else 7.0
    aa_threshold = 3.0 if large_text else 4.5
    if ratio >= aaa_threshold:
        return "AAA"
    if ratio >= aa_threshold:
        return "AA"
    return "FAIL"


# Canonical token matrix. Edit when tokens move.
PAIRS: list[tuple[str, str, str, str]] = [
    # (label, fg, bg, intended-use)
    # ---- New AAA-targeted Tailwind tokens (Phase 2) ----
    ("fg.DEFAULT on surface", "#111827", "#FFFFFF", "primary body text"),
    ("fg.DEFAULT on surface-muted", "#111827", "#F3F4F6", "primary body text on muted card"),
    ("fg.muted on surface", "#374151", "#FFFFFF", "secondary text"),
    ("fg.muted on surface-muted", "#374151", "#F3F4F6", "secondary text on muted card"),
    ("fg.subtle on surface", "#475263", "#FFFFFF", "tertiary / caption text"),
    ("fg.subtle on surface-muted", "#475263", "#F3F4F6", "tertiary / caption text on muted card"),
    ("fg.subtle on surface-subtle", "#475263", "#F9FAFB", "tertiary / caption on subtle"),
    # Brand
    ("UMich Blue on white", "#00274C", "#FFFFFF", "primary action / link"),
    ("UMich Maize on Blue", "#FFCB05", "#00274C", "logo + accent on dark"),
    ("UMich Blue on Maize", "#00274C", "#FFCB05", "Maize-bg surfaces (rare)"),
    # Sidebar (dark-blue surface)
    ("sidebar caption on UMich Blue", "#C9D4E0", "#00274C", "sidebar legend / footer"),
    ("sidebar text on UMich Blue", "#FFFFFF", "#00274C", "sidebar primary text"),
    # Severity (text on tinted background)
    ("sev.critical on sev.critical-bg", "#7A0000", "#FEE2E2", "critical badge"),
    ("sev.major on sev.major-bg", "#6B2E00", "#FFEBC7", "major badge"),
    ("sev.minor on sev.minor-bg", "#4F4200", "#FEF9C3", "minor badge"),
    ("sev.info on sev.info-bg", "#1F2937", "#E5E7EB", "info badge"),
    # Severity foreground on plain white (for inline severity text outside the chip)
    ("sev.critical on white", "#7A0000", "#FFFFFF", "critical text inline"),
    ("sev.major on white", "#6B2E00", "#FFFFFF", "major text inline"),
    ("sev.minor on white", "#4F4200", "#FFFFFF", "minor text inline"),
    # Focus ring (non-text — AAA SC 1.4.11 = 3:1)
    ("focus ring on white", "#00274C", "#FFFFFF", "focus indicator"),
    ("focus ring on UMich Blue", "#FFCB05", "#00274C", "focus on dark surface"),
    # ---- Legacy Jinja-only tokens (styles.css) ----
    ("legacy --accent on --bg (light)", "#003F75", "#FAFAFA", "Jinja link color"),
    ("legacy --fg-muted on --bg (light)", "#3F3F3F", "#FAFAFA", "Jinja secondary text"),
    ("legacy table-header fg on tint", "#3F3F3F", "#D8D8D8", "Jinja table header"),
]


def print_matrix() -> None:
    width = max(len(p[0]) for p in PAIRS) + 2
    print(f"{'pair':<{width}} {'fg':<8} {'bg':<8}  ratio  grade  use")
    print("-" * (width + 50))
    for label, fg, bg, use in PAIRS:
        r = contrast(fg, bg)
        g = grade(r)
        marker = "✓" if g == "AAA" else ("·" if g == "AA" else "✗")
        print(f"{label:<{width}} {fg:<8} {bg:<8} {r:5.2f}  {g:<5} {marker} {use}")


if __name__ == "__main__":
    if len(sys.argv) == 3:
        fg, bg = sys.argv[1], sys.argv[2]
        r = contrast(fg, bg)
        print(f"{fg} on {bg}: {r:.2f}:1 — {grade(r)} (normal text)")
        print(f"{fg} on {bg}: {r:.2f}:1 — {grade(r, large_text=True)} (large text)")
    else:
        print_matrix()
