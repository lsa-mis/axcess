"""Serve tests/fixtures/site on http://127.0.0.1:8000 for manual crawler testing."""

from __future__ import annotations

import http.server
import os
import socketserver
import sys
from pathlib import Path


def main() -> None:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    root = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "site"
    if not root.exists():
        print(f"Fixture site not yet present at {root}", file=sys.stderr)
        sys.exit(1)
    os.chdir(root)

    class QuietHandler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            return

    with socketserver.TCPServer(("127.0.0.1", port), QuietHandler) as httpd:
        print(f"Serving {root} at http://127.0.0.1:{port}")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down.")


if __name__ == "__main__":
    main()
