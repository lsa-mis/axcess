"""Render the Claude Design artboards to PNG files for the repo docs.

All paths below are under docs/images/diagrams/source/. For each
project/<Name>.dc.html this script:
  1. removes the support.js line and the x-dc script block,
  2. unwraps <x-dc> and <helmet>, moving helmet's <style> into <head>,
  3. replaces the Google Fonts <link> with local @font-face rules that point
     at the woff2 files in fonts/,
  4. writes render/<Name>.html (a throwaway file; delete it before you
     commit), and
  5. screenshots it with Playwright's Chromium headless shell at 2x into
     docs/images/diagrams/.

Run:  python3 docs/images/diagrams/source/render/build.py [Name ...]
The built-in SHELL default is a path on the machine that made the diagrams,
not Playwright's default location. Install the shell with
`uv run playwright install chromium` (or `make setup`), find it with
`find ~/Library/Caches/ms-playwright ~/.cache/ms-playwright -name headless_shell -type f`,
and set AXCESS_DIAGRAM_BROWSER to that path.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DESIGN = HERE.parent
PROJECT = DESIGN / "project"
FONTS = DESIGN / "fonts"
OUT_DIR = DESIGN.parent  # docs/images/diagrams
SHELL = os.environ.get(
    "AXCESS_DIAGRAM_BROWSER",
    "/opt/pw-browsers/chromium_headless_shell-1194/chrome-linux/headless_shell",
)

OUTPUT_NAMES = {
    "Main": "system-architecture.png",
    "ReportGroups": "report-groups.png",
    "LoginScan": "login-scan-flow.png",
    "PrivacyBoundary": "privacy-boundary.png",
    "ReleaseFlow": "release-flow.png",
    "CodeMap": "code-map.png",
}

LATIN = ("U+0000-00FF, U+0131, U+0152-0153, U+02BB-02BC, U+02C6, U+02DA, U+02DC, "
         "U+0304, U+0308, U+0329, U+2000-206F, U+20AC, U+2122, U+2191, U+2193, "
         "U+2212, U+2215, U+FEFF, U+FFFD")
LATIN_EXT = ("U+0100-02BA, U+02BD-02C5, U+02C7-02CC, U+02CE-02D7, U+02DD-02FF, U+0304, "
             "U+0308, U+0329, U+1D00-1DBF, U+1E00-1E9F, U+1EF2-1EFF, U+2020, "
             "U+20A0-20AB, U+20AD-20C0, U+2113, U+2C60-2C7F, U+A720-A7FF")


def font_faces() -> str:
    rules = []
    for family, stem in (("Atkinson Hyperlegible Next", "next"),
                         ("Atkinson Hyperlegible Mono", "mono")):
        for subset, rng in (("latin-ext", LATIN_EXT), ("latin", LATIN)):
            src = (FONTS / f"{stem}-{subset}.woff2").relative_to(DESIGN)
            rules.append(
                f'@font-face{{font-family:"{family}";font-style:normal;'
                f'font-weight:200 800;src:url("../{src.as_posix()}") format("woff2");'
                f"unicode-range:{rng};}}"
            )
    return "<style>" + "".join(rules) + "</style>"


def standalone(dc_html: str) -> tuple[str, int, int]:
    html = dc_html.replace('<script src="./support.js"></script>', "")
    match = re.search(r"data-props='(\{.*?\})'", html)
    if not match:
        raise ValueError("missing data-props preview size")
    preview = json.loads(match.group(1))["$preview"]
    html = re.sub(r'<script type="text/x-dc".*?</script>', "", html, flags=re.S)
    helmet = re.search(r"<helmet>(.*?)</helmet>", html, flags=re.S)
    if not helmet:
        raise ValueError("missing <helmet>")
    styles = "".join(re.findall(r"<style>.*?</style>", helmet.group(1), flags=re.S))
    html = html.replace(helmet.group(0), "")
    html = html.replace("<x-dc>", "").replace("</x-dc>", "")
    html = html.replace("</head>", font_faces() + styles + "</head>", 1)
    if "fonts.googleapis.com" in html or "<helmet" in html or "x-dc" in html:
        raise ValueError("canvas-only markup survived the conversion")
    return html, int(preview["width"]), int(preview["height"])


def render(name: str) -> Path:
    source = PROJECT / f"{name}.dc.html"
    html, width, height = standalone(source.read_text(encoding="utf-8"))
    page = HERE / f"{name}.html"
    page.write_text(html, encoding="utf-8")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / OUTPUT_NAMES[name]
    subprocess.run(
        [SHELL, "--no-sandbox", "--disable-gpu", "--hide-scrollbars",
         "--force-device-scale-factor=2", f"--window-size={width},{height}",
         f"--screenshot={out}", f"file://{page}"],
        check=True, capture_output=True, timeout=120,
    )
    print(f"{name}: {out} ({out.stat().st_size // 1024} KB, {width}x{height} at 2x)")
    return out


def main(argv: list[str]) -> None:
    names = argv or list(OUTPUT_NAMES)
    for name in names:
        render(name)


if __name__ == "__main__":
    main(sys.argv[1:])
