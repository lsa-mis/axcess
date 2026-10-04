"""The Inspector's style check (frontend ``lib/styleFingerprint.ts``), run in Node.

The comparison decides whether a saved copy is said to look different from
the page Axcess checked, so its threshold and its leniency rules are pinned
here. The module has no DOM dependency in these functions; Node (which strips
TypeScript types itself) runs it as it is. The element filter that numbers
the samples needs a browser and is checked against the capture in
tests/ui/test_inspector_capture_rendering.py.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

MODULE = Path(__file__).resolve().parents[2] / "src/audit/web/frontend/src/lib/styleFingerprint.ts"

NODE = shutil.which("node")

pytestmark = pytest.mark.skipif(NODE is None, reason="Node.js is not installed")


def _run(expression: str) -> Any:
    script = (
        f"const m = await import({json.dumps(MODULE.as_uri())});"
        f"process.stdout.write(JSON.stringify({expression}));"
    )
    assert NODE is not None
    # Our own fixed module and expressions, run by the Node found on PATH.
    result = subprocess.run(  # noqa: S603
        [NODE, "--input-type=module", "-e", script],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if result.returncode != 0 and "ERR_UNKNOWN_FILE_EXTENSION" in result.stderr:
        pytest.skip("this Node.js cannot run TypeScript files")
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def _sample(index: int, **overrides: str) -> dict[str, Any]:
    return {
        "index": index,
        "fontFamily": "inter",
        "fontWeight": "400",
        "color": "rgb(0, 0, 0)",
        "backgroundColor": "rgba(0, 0, 0, 0)",
        "textDecorationLine": "none",
        **overrides,
    }


def _compare(
    expected: list[dict[str, Any]],
    observed: list[dict[str, Any] | None],
    *,
    scheme: str = "light",
    frame_scheme: str = "light",
    forced: bool = False,
) -> dict[str, Any]:
    fingerprint = {"scheme": scheme, "forced_colors": False, "samples": expected}
    frame = {"scheme": frame_scheme, "forcedColors": forced}
    return _run(  # type: ignore[no-any-return]
        "(() => { const r = m.compareFingerprint("
        f"{json.dumps(fingerprint)}, {json.dumps(observed)}, {json.dumps(frame)});"
        " return {...r, differs: m.looksDifferent(r)}; })()"
    )


def test_identical_samples_match() -> None:
    samples = [_sample(i) for i in range(10)]
    result = _compare(samples, samples)
    assert result == {"checked": 10, "matched": 10, "colorsCompared": True, "differs": False}


def test_below_seventy_percent_is_said_to_differ() -> None:
    expected = [_sample(i) for i in range(10)]
    # 7 of 10 is exactly the threshold and passes; 6 of 10 does not.
    seven = [*expected[:7], *[_sample(i, fontFamily="times new roman") for i in range(7, 10)]]
    six = [*expected[:6], *[_sample(i, color="rgb(255, 0, 0)") for i in range(6, 10)]]
    assert _compare(expected, seven)["differs"] is False
    assert _compare(expected, six)["differs"] is True


def test_a_missing_element_counts_as_a_mismatch() -> None:
    expected = [_sample(i) for i in range(4)]
    result = _compare(expected, [expected[0], None, None, None])
    assert result["matched"] == 1
    assert result["differs"] is True


def test_quoting_case_and_colour_spelling_do_not_count_as_differences() -> None:
    expected = [_sample(0, fontFamily="open sans", backgroundColor="rgba(0, 0, 0, 0)")]
    observed = [_sample(0, fontFamily='"Open Sans"', backgroundColor="transparent")]
    observed[0]["color"] = "rgb(0,0,0)"
    assert _compare(expected, observed)["matched"] == 1


def test_colours_are_not_compared_when_the_frame_prefers_another_scheme() -> None:
    expected = [_sample(i) for i in range(5)]
    dark = [
        _sample(i, color="rgb(255, 255, 255)", backgroundColor="rgb(0, 0, 0)") for i in range(5)
    ]
    result = _compare(expected, dark, frame_scheme="dark")
    assert result["colorsCompared"] is False
    assert result["differs"] is False
    # Fonts still count.
    fonts = [_sample(i, fontWeight="700") for i in range(5)]
    assert _compare(expected, fonts, frame_scheme="dark")["differs"] is True
    assert _compare(expected, dark, forced=True)["colorsCompared"] is False


def test_nothing_to_compare_is_not_a_difference() -> None:
    assert _compare([], [])["differs"] is False
    assert (
        _run(
            "m.looksDifferent(m.compareFingerprint("
            "null, [], {scheme: 'light', forcedColors: false}))"
        )
        is False
    )


def test_first_family_and_colour_helpers() -> None:
    assert _run("m.firstFamily(\"'Helvetica Neue', Arial, sans-serif\")") == "helvetica neue"
    assert _run("m.firstFamily('')") == ""
    assert _run("m.normalizeColor('RGBA( 1 ,2,3 , 0.5 )')") == "rgba(1, 2, 3, 0.5)"
