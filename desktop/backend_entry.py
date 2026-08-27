"""PyInstaller entry point for the Axcess desktop backend."""

from multiprocessing import freeze_support

from audit.desktop_server import main


if __name__ == "__main__":
    # ProcessPoolExecutor workers (used by OCR) re-enter this frozen
    # executable. Without freeze_support they parse the server CLI instead of
    # starting a worker, so OCR fails with a spurious ``--port`` error.
    freeze_support()
    main()
