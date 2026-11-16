"""PyInstaller entry point for the Axcess desktop backend."""

import sys
from multiprocessing import freeze_support

if __name__ == "__main__" and sys.argv[1:] == ["--axcess-network-probe"]:
    # The private AI's isolation check runs this executable inside the OS
    # sandbox to prove outside connections are refused. Answer it before the
    # server's argument parser sees the flag. Keep the literal in step with
    # ``audit.ai.sandbox.NETWORK_PROBE_FLAG`` (a unit test checks).
    from audit.ai.sandbox import run_network_probe

    run_network_probe()

from audit.desktop_server import main

if __name__ == "__main__":
    # ProcessPoolExecutor workers (used by OCR) re-enter this frozen
    # executable. Without freeze_support they parse the server CLI instead of
    # starting a worker, so OCR fails with a spurious ``--port`` error.
    freeze_support()
    main()
