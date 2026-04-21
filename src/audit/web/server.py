"""Local review UI. Phase 0 stub — expands during Phase 6."""

from __future__ import annotations

from fastapi import FastAPI

from audit import __version__

app = FastAPI(title="Image Text Audit", version=__version__)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": __version__}


@app.get("/")
def index() -> dict[str, str]:
    return {
        "message": "Image Text Audit — UI not yet implemented. See PLAN.md Phase 6.",
        "version": __version__,
    }
