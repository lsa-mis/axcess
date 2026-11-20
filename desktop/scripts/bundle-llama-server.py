"""Bundle the pinned llama.cpp server builds into desktop/llama-runtime.

The private AI service in Axcess Desktop runs ``llama-server``. Shipping it
inside the app means the AI setup downloads only the model files. This
script downloads the builds that ``src/audit/ai/catalog.json`` pins for one
platform, checks each against its SHA-256, and unpacks it as:

    desktop/llama-runtime/<accelerator>/...   (metal, vulkan or cpu)

The backend finds it through AUDIT_LLAMA_SERVER_DIR (desktopEnvironment in
src/runtime.cjs) and tries the builds in catalog order: a GPU build first,
then the CPU build.

Standard library only, so it runs before ``uv sync`` too:

    python desktop/scripts/bundle-llama-server.py [--platform linux-x64]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import shutil
import stat
import sys
import tarfile
import tempfile
import urllib.request
import zipfile
from pathlib import Path

DESKTOP = Path(__file__).resolve().parent.parent
CATALOG = DESKTOP.parent / "src" / "audit" / "ai" / "catalog.json"
DESTINATION = DESKTOP / "llama-runtime"
SERVER_NAMES = ("llama-server", "llama-server.exe")


def platform_key() -> str:
    machine = platform.machine().lower()
    arch = "arm64" if machine in {"arm64", "aarch64"} else "x64"
    if sys.platform.startswith("win"):
        return f"win32-{arch}"
    if sys.platform.startswith("linux"):
        return f"linux-{arch}"
    return f"{sys.platform}-{arch}"


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def unpack(archive: Path, dest: Path) -> None:
    root = dest.resolve()
    if archive.name.endswith(".zip"):
        with zipfile.ZipFile(archive) as zf:
            for member in zf.infolist():
                if not (dest / member.filename).resolve().is_relative_to(root):
                    raise SystemExit(f"Unsafe path in {archive.name}: {member.filename}")
            zf.extractall(dest)  # noqa: S202 - every member path checked above
    else:
        with tarfile.open(archive, "r:gz") as tf:
            tf.extractall(dest, filter="data")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--platform", default=platform_key())
    args = parser.parse_args()
    release = json.loads(CATALOG.read_text(encoding="utf-8"))["llama_cpp"]
    assets = release["assets"].get(args.platform)
    if not assets:
        print(f"No llama.cpp build is pinned for {args.platform}.", file=sys.stderr)
        return 1
    shutil.rmtree(DESTINATION, ignore_errors=True)
    DESTINATION.mkdir(parents=True)
    with tempfile.TemporaryDirectory() as tmp:
        for asset in assets:
            url = (
                "https://github.com/ggml-org/llama.cpp/releases/download/"
                f"{release['version']}/{asset['name']}"
            )
            archive = Path(tmp) / asset["name"]
            print(f"Downloading {url}")
            with urllib.request.urlopen(url, timeout=120) as response, archive.open("wb") as fh:  # noqa: S310 - fixed https URL
                shutil.copyfileobj(response, fh)
            actual = sha256_of(archive)
            if actual != asset["sha256"] or archive.stat().st_size != asset["size"]:
                print(
                    f"{asset['name']} does not match its pinned checksum "
                    f"(expected {asset['sha256']}, got {actual}).",
                    file=sys.stderr,
                )
                return 1
            dest = DESTINATION / asset["accelerator"]
            unpack(archive, dest)
            servers = [p for name in SERVER_NAMES for p in dest.rglob(name) if p.is_file()]
            if not servers:
                print(f"{asset['name']} has no llama-server in it.", file=sys.stderr)
                return 1
            for server in servers:
                server.chmod(server.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
            licence = next(iter(dest.rglob("LICENSE*")), None)
            print(f"{asset['accelerator']}: {servers[0].relative_to(DESKTOP)}")
            if licence is None:
                print(f"warning: no licence file in {asset['name']}", file=sys.stderr)
    (DESTINATION / "VERSION").write_text(release["version"] + "\n", encoding="utf-8")
    print(f"llama.cpp {release['version']} bundled in {DESTINATION}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
