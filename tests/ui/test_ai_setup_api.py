"""The desktop AI setup API exists only on desktop and changes the live settings."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from audit.ai.state import AIConfig, save_config
from audit.config import Settings
from audit.web.server import create_app


@pytest.fixture
def db(seeded_db: tuple[Path, Path, int], tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("AUDIT_ACCESS_TOKEN", "")
    monkeypatch.setenv("AUDIT_DATA_DIR", str(tmp_path))
    # No real Ollama is contacted: point the port-11434 check nowhere.
    monkeypatch.setattr("audit.ai.manager.system_ollama", lambda: None)
    return seeded_db[0]


def test_ai_routes_are_absent_outside_the_desktop_app(db: Path, tmp_path: Path) -> None:
    with TestClient(create_app(db_path=db, blob_dir=tmp_path / "blobs")) as client:
        assert client.get("/api/ai/plan").status_code == 404
        assert client.post("/api/ai/install", json={"tier": "small"}).status_code in {404, 405}


def test_plan_describes_this_computer_and_every_size(
    db: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AUDIT_DESKTOP", "1")
    with TestClient(create_app(db_path=db, blob_dir=tmp_path / "blobs")) as client:
        plan = client.get("/api/ai/plan").json()
        assert [t["id"] for t in plan["tiers"]] == ["small", "standard", "large"]
        assert plan["current"] is None
        assert plan["install"]["state"] == "idle"
        assert plan["program"]["licence"] == "MIT"
        for tier in plan["tiers"]:
            assert (
                tier["download_bytes"] == tier["models_bytes"] + plan["program"]["download_bytes"]
            )
        bad = client.post("/api/ai/install", json={"tier": "huge"})
        assert bad.status_code == 422


def test_saved_setup_chooses_the_models_the_app_uses(
    db: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AUDIT_DESKTOP", "1")
    save_config(
        Settings(data_dir=tmp_path, desktop=True),
        AIConfig(
            source="system",
            base_url="http://127.0.0.1:1",
            tier="small",
            text_model="text:test",
            vision_model="vision:test",
        ),
    )
    with TestClient(create_app(db_path=db, blob_dir=tmp_path / "blobs")) as client:
        capability = client.get("/api/capabilities/local-analysis").json()
        assert capability["vision"]["model"] == "vision:test"
        assert capability["semantic"]["models"] == ["text:test"]
        status = client.get("/api/suggestions/status").json()
        assert status["reason"] != "turned_off"
        assert client.delete("/api/ai").status_code == 204
        assert client.get("/api/ai/plan").json()["current"] is None
