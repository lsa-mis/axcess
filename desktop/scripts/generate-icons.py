"""Regenerate native icons from the outlined SVG; no network or system fonts.

Run from the repository root: uv run python desktop/scripts/generate-icons.py
Requires the project's Pillow and installed Playwright Chromium dependencies.
Normal desktop builds use the committed outputs and do not run this script.
"""

from io import BytesIO
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright


def main() -> None:
    assets = Path(__file__).resolve().parents[1] / "assets"
    svg = (assets / "axcess.svg").read_text(encoding="utf-8")
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page(
                viewport={"width": 1024, "height": 1024},
                device_scale_factor=2,
                offline=True,
            )
            page.set_content(
                "<style>html,body{margin:0}svg{display:block;width:1024px;"
                "height:1024px}</style>" + svg
            )
            screenshot = page.screenshot(omit_background=True)
        finally:
            browser.close()

    with Image.open(BytesIO(screenshot)) as rendered:
        master = rendered.convert("RGBA").resize((1024, 1024), Image.Resampling.LANCZOS)
    master.save(assets / "axcess.png", optimize=True)
    master.save(
        assets / "axcess.ico",
        sizes=[(size, size) for size in (16, 24, 32, 48, 64, 128, 256)],
    )
    master.save(assets / "axcess.icns")
    print("Generated Axcess PNG, ICO, and ICNS desktop icons.")


if __name__ == "__main__":
    main()
