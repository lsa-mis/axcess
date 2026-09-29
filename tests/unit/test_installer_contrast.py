"""The installer contrast check (desktop/scripts/installer_contrast.py).

It runs on the Windows runner against real screenshots; here it runs on
drawn ones whose colours are known, so its verdicts can be checked.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

_SCRIPT = Path(__file__).resolve().parents[2] / "desktop" / "scripts" / "installer_contrast.py"
_spec = importlib.util.spec_from_file_location("installer_contrast", _SCRIPT)
assert _spec and _spec.loader
contrast_check = importlib.util.module_from_spec(_spec)
sys.modules["installer_contrast"] = contrast_check  # @dataclass looks it up
_spec.loader.exec_module(contrast_check)

WHITE = (255, 255, 255)
FACE = (240, 240, 240)  # Windows' button face


def _text(draw: ImageDraw.ImageDraw, left: int, top: int, colour: tuple[int, int, int]) -> None:
    """Strokes like a word: solid cores with a softened edge on each."""
    for i in range(6):
        x = left + i * 6
        draw.rectangle((x, top, x + 1, top + 9), fill=colour)
        edge = tuple((c + w) // 2 for c, w in zip(colour, WHITE, strict=True))
        draw.point((x + 2, top + 4), fill=edge)


def test_contrast_matches_wcag() -> None:
    assert contrast_check.contrast((0, 0, 0), WHITE) == pytest.approx(21.0)
    assert contrast_check.contrast((0x76, 0x76, 0x76), WHITE) == pytest.approx(4.54, abs=0.01)


def test_black_text_passes_and_grey_text_fails() -> None:
    image = Image.new("RGB", (120, 40), WHITE)
    draw = ImageDraw.Draw(image)
    _text(draw, 2, 2, (0, 0, 0))
    _text(draw, 2, 22, (0x99, 0x99, 0x99))  # 2.85:1
    dark = contrast_check.measure(image, (0, 0, 120, 16))
    light = contrast_check.measure(image, (0, 20, 120, 36))
    assert dark and dark[0] == pytest.approx(21.0)
    assert light and light[0] == pytest.approx(2.85, abs=0.01)


def test_softened_edges_do_not_count_as_text() -> None:
    image = Image.new("RGB", (60, 20), WHITE)
    _text(ImageDraw.Draw(image), 2, 2, (0x59, 0x59, 0x59))
    found = contrast_check.measure(image, (0, 0, 60, 20))
    assert found and found[1] == (0x59, 0x59, 0x59)


def test_an_empty_box_is_not_measured() -> None:
    assert contrast_check.measure(Image.new("RGB", (40, 20), WHITE), (0, 0, 40, 20)) is None


def test_a_button_frame_does_not_pass_for_its_text(tmp_path: Path) -> None:
    image = Image.new("RGB", (100, 30), FACE)
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 99, 29), outline=(0, 0, 0), width=2)  # dark frame
    _text(draw, 10, 8, (0xA0, 0xA0, 0xA0))  # 2.3:1 on the face
    image.save(tmp_path / "setup-1.png")
    element = {
        "name": "Next >",
        "className": "Button",
        "left": 0,
        "top": 0,
        "width": 100,
        "height": 30,
    }
    (tmp_path / "setup-1.json").write_text(json.dumps([element]), encoding="utf-8")
    [result] = contrast_check.measure_screen(tmp_path / "setup-1.png")
    assert not result.passes
    assert contrast_check.main(str(tmp_path)) == 1
    assert "FAIL" in (tmp_path / "contrast.txt").read_text(encoding="utf-8")


def test_a_screen_of_good_text_passes(tmp_path: Path) -> None:
    image = Image.new("RGB", (100, 20), WHITE)
    _text(ImageDraw.Draw(image), 2, 2, (0, 0, 0))
    image.save(tmp_path / "setup-2.png")
    element = {
        "name": "Choose a folder",
        "className": "Static",
        "left": 0,
        "top": 0,
        "width": 100,
        "height": 20,
    }
    # PowerShell's Set-Content -Encoding UTF8 writes a byte-order mark.
    (tmp_path / "setup-2.json").write_text(json.dumps([element]), encoding="utf-8-sig")
    assert contrast_check.main(str(tmp_path)) == 0
