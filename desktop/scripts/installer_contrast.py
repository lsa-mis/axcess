"""Measure the text contrast of every Windows installer screen.

check-installer-accessibility.ps1 saves, for each setup and uninstall
screen, a screenshot (<screen>.png) and every named element on it with its
box (<screen>.json). Axe.Windows does not measure colour contrast, so this
does, against SC 1.4.3 Contrast (Minimum), Level AA: 4.5:1 for text. The
installer's text is small, so the large-text 3:1 allowance is not used.

For each element the background is the colour most of its box has, and
the text colour is the colour, among those covering at least a few
pixels, that stands out most from it. Anti-aliased and ClearType edges
mix the text and background colours channel by channel, so they never
stand out more than the text itself, and one-off colours are ignored.
Buttons and fields are measured inside the frame Windows draws around
them, so the frame cannot pass for text. A checkbox or radio circle can
still be measured with its label; that can only make a result look
better, never fail good text.

  uv run python desktop/scripts/installer_contrast.py desktop/out/installer-a11y

Prints every measurement, writes contrast.txt beside the screenshots, and
exits 1 when any text is below 4.5:1.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

MINIMUM = 4.5
# Pixels of a colour needed before it counts as the text colour.
MIN_PIXELS = 4
# Win32 classes whose box includes a frame Windows draws around the text.
FRAMED = {"Button": 3, "Edit": 3}

RGB = tuple[int, int, int]


def luminance(rgb: RGB) -> float:
    """Relative luminance, as WCAG 2.2 defines it."""

    def channel(value: int) -> float:
        c = value / 255
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (channel(v) for v in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a: RGB, b: RGB) -> float:
    high, low = sorted((luminance(a), luminance(b)), reverse=True)
    return (high + 0.05) / (low + 0.05)


@dataclass(frozen=True)
class Measurement:
    screen: str
    name: str
    ratio: float
    text: RGB
    background: RGB

    @property
    def passes(self) -> bool:
        return self.ratio >= MINIMUM

    def line(self) -> str:
        verdict = "ok  " if self.passes else "FAIL"
        text = "".join(f"{v:02x}" for v in self.text)
        background = "".join(f"{v:02x}" for v in self.background)
        return (
            f"{verdict} {self.ratio:5.2f}:1  #{text} on #{background}  {self.screen}: {self.name!r}"
        )


def measure(image: Image.Image, box: tuple[int, int, int, int]) -> tuple[float, RGB, RGB] | None:
    """(ratio, text colour, background) inside ``box``, or None if nothing is drawn."""
    left, top, right, bottom = box
    left, top = max(left, 0), max(top, 0)
    right, bottom = min(right, image.width), min(bottom, image.height)
    if right - left < 2 or bottom - top < 2:
        return None
    counts = Counter(image.crop((left, top, right, bottom)).convert("RGB").getdata())
    background = counts.most_common(1)[0][0]
    candidates = [c for c, n in counts.items() if c != background and n >= MIN_PIXELS]
    if not candidates:
        return None
    text = max(candidates, key=lambda c: contrast(c, background))
    return contrast(text, background), text, background


def measure_screen(png: Path) -> list[Measurement]:
    elements = json.loads(png.with_suffix(".json").read_text(encoding="utf-8-sig"))
    image = Image.open(png)
    results = []
    for element in elements:
        inset = FRAMED.get(element.get("className", ""), 0)
        box = (
            element["left"] + inset,
            element["top"] + inset,
            element["left"] + element["width"] - inset,
            element["top"] + element["height"] - inset,
        )
        found = measure(image, box)
        if found:
            ratio, text, background = found
            results.append(Measurement(png.stem, element["name"], ratio, text, background))
    return results


def main(directory: str) -> int:
    folder = Path(directory)
    screens = sorted(folder.glob("*.png"))
    if not screens:
        print(f"No screenshots in {folder}.")
        return 1
    results = [m for png in screens for m in measure_screen(png)]
    report = "\n".join(m.line() for m in results)
    (folder / "contrast.txt").write_text(report + "\n", encoding="utf-8")
    print(report)
    failures = [m for m in results if not m.passes]
    summary = f"{len(results)} text elements on {len(screens)} screens"
    print(f"{summary}; {len(failures)} below {MINIMUM}:1.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "out/installer-a11y"))
