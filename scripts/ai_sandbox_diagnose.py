"""Print what the private AI's network check sees inside the OS sandbox.

For CI logs when the check fails: the check itself only says it did not
pass. Runs the same probe command and prints its exit code and output.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

from audit.ai.sandbox import _probe_argv, build_sandbox


def main() -> int:
    root = Path(tempfile.mkdtemp(prefix="axd-"))
    for name in ("runtime", "models", "scratch"):
        (root / name).mkdir()
    sandbox = build_sandbox(root / "runtime", root / "models", root / "scratch")
    command = sandbox.command(_probe_argv())
    print("command prefix:", " ".join(sandbox.prefix[:3]), "...")
    if sys.platform == "darwin":
        print("profile:\n" + sandbox.prefix[2])
    result = subprocess.run(command, capture_output=True, text=True, timeout=20, check=False)
    print("exit:", result.returncode)
    print("stdout:", result.stdout.strip()[:2000])
    print("stderr:", result.stderr.strip()[:2000])
    probe = (
        "import socket\ns=socket.socket();s.settimeout(1)\ntry:\n"
        " s.connect(('1.1.1.1',443));print('CONNECTED')\n"
        "except OSError as e:\n print('errno',e.errno,e)"
    )
    raw = subprocess.run(
        sandbox.command([str(Path(sys.executable).resolve()), "-I", "-S", "-c", probe]),
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    print("raw connect:", raw.returncode, raw.stdout.strip(), raw.stderr.strip()[:500])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
