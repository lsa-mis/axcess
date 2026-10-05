"""New scan completes a web address typed without its scheme (``lib/webAddress.ts``).

A website gets https://; localhost, a *.localhost name and an IP address get
http://; an address that already names a scheme is left as typed. Run in
Node, which strips TypeScript types itself, like
tests/unit/test_style_fingerprint_compare.py.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

MODULE = Path(__file__).resolve().parents[2] / "src/audit/web/frontend/src/lib/webAddress.ts"
NODE = shutil.which("node")

pytestmark = pytest.mark.skipif(NODE is None, reason="Node.js is not installed")

CASES = {
    # A website: https://.
    "example.edu": "https://example.edu",
    "example.edu/section/": "https://example.edu/section/",
    "www.umich.edu/path?q=1#top": "https://www.umich.edu/path?q=1#top",
    "example.edu:8443/app": "https://example.edu:8443/app",
    "  umich.instructure.com/courses/  ": "https://umich.instructure.com/courses/",
    "//example.edu/x": "https://example.edu/x",
    # localhost and IP addresses: http://.
    "localhost": "http://localhost",
    "localhost:8000": "http://localhost:8000",
    "LOCALHOST:3000/app": "http://LOCALHOST:3000/app",
    "app.localhost:5173": "http://app.localhost:5173",
    "127.0.0.1": "http://127.0.0.1",
    "192.168.1.10:8080/admin": "http://192.168.1.10:8080/admin",
    "[::1]:8000/": "http://[::1]:8000/",
    # A scheme already there is kept as typed, wrong or right.
    "https://example.edu": "https://example.edu",
    "http://example.edu": "http://example.edu",
    "HTTPS://Example.edu": "HTTPS://Example.edu",
    "http://localhost:8000": "http://localhost:8000",
    "ftp://files.example.edu": "ftp://files.example.edu",
    "mailto:someone@example.edu": "mailto:someone@example.edu",
    # Nothing typed stays nothing.
    "": "",
    "   ": "",
}


def test_scheme_is_completed_as_the_rule_says() -> None:
    script = (
        f"const m = await import({json.dumps(MODULE.as_uri())});"
        f"const cases = {json.dumps(list(CASES))};"
        "process.stdout.write(JSON.stringify(cases.map((c) => m.withScheme(c))));"
    )
    assert NODE is not None
    # Our own fixed module and inputs, run by the Node found on PATH.
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
    got = dict(zip(CASES, json.loads(result.stdout), strict=True))
    wrong = {typed: (got[typed], want) for typed, want in CASES.items() if got[typed] != want}
    assert not wrong, wrong
