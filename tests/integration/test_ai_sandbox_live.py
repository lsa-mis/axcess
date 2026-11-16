"""The private AI's Linux sandbox, run for real with Bubblewrap.

Skipped where Bubblewrap is missing or cannot create namespaces (many CI
containers). Inside the sandbox the probe only attempts a TCP connection,
which the private network namespace refuses before it leaves the computer.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import sysconfig
from pathlib import Path

import pytest

from audit.ai.sandbox import NETWORK_PROBE_FLAG, build_sandbox
from audit.ai.sandbox import test_network_boundary as check_network

REPO = Path(__file__).parents[2]

pytestmark = pytest.mark.skipif(
    not sys.platform.startswith("linux") or shutil.which("bwrap") is None,
    reason="needs Linux with Bubblewrap",
)


def _sandbox(tmp_path: Path, runtime: Path):
    sandbox = build_sandbox(runtime, tmp_path / "models", tmp_path / "scratch")
    (tmp_path / "models").mkdir(exist_ok=True)
    (tmp_path / "scratch").mkdir(exist_ok=True)
    smoke = subprocess.run(  # noqa: S603 - fixed command in the test sandbox
        sandbox.command(["/usr/bin/true"]), capture_output=True, check=False
    )
    if smoke.returncode != 0:
        pytest.skip(f"Bubblewrap cannot run here: {smoke.stderr.decode()[:120]}")
    return sandbox


def test_network_probe_passes_inside_the_real_sandbox(tmp_path: Path) -> None:
    check_network(_sandbox(tmp_path, tmp_path))


def test_packaged_style_entry_answers_the_probe_inside_the_sandbox(tmp_path: Path) -> None:
    """The flag the packaged backend gets, through the real entry script.

    The repository (with its virtual environment) is the read-only runtime
    here so the unpackaged entry script can import Axcess inside the sandbox.
    A virtual environment's ``python`` can be a link through folders the
    sandbox does not mount, so run the real interpreter with the
    environment's packages on ``PYTHONPATH``.
    """
    sandbox = _sandbox(tmp_path, REPO)
    paths = sysconfig.get_paths()
    env = {**os.environ, "PYTHONPATH": os.pathsep.join([paths["purelib"], str(REPO / "src")])}
    result = subprocess.run(  # noqa: S603 - fixed probe in the test sandbox
        sandbox.command(
            [
                str(Path(sys.executable).resolve()),
                str(REPO / "desktop" / "backend_entry.py"),
                NETWORK_PROBE_FLAG,
            ]
        ),
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stderr[-500:]
    assert result.stdout.strip() == "AXCESS_NETWORK_BLOCKED"
