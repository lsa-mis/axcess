"""The desktop AI setup API exists only on desktop and changes the live settings."""

from __future__ import annotations

import asyncio
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from audit.ai.manager import AIManager
from audit.ai.state import AIConfig, AIPreferences, save_config, save_preferences
from audit.config import Settings
from audit.db.schema import connect
from audit.web.server import create_app

from .test_fix_suggestions import FakeProvider, FakeVerifier, _add_finding


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


def test_skip_choice_persists_and_blocks_model_requests(
    db: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AUDIT_DESKTOP", "1")
    settings = Settings(data_dir=tmp_path, desktop=True)
    save_preferences(settings, AIPreferences())
    with TestClient(create_app(db_path=db, blob_dir=tmp_path / "blobs")) as client:
        assert client.get("/api/ai/preferences").json() == {
            "enabled": False,
            "choice_recorded": False,
        }
        assert client.put("/api/ai/preferences", json={"enabled": False}).json() == {
            "enabled": False,
            "choice_recorded": True,
        }
        local = client.get("/api/capabilities/local-analysis").json()
        assert local["ai_enabled"] is False
        assert not local["vision"]["available"]
        assert not local["semantic"]["available"]
        assert "off" in local["vision"]["reason"]
        assert client.get("/api/suggestions/status").json()["reason"] == "turned_off"
        for key in ("skip_vlm", "skip_semantic"):
            for value in (False, None, 0):
                response = client.post(
                    "/api/scans", json={"url": "https://example.com", key: value}
                )
                assert response.status_code == 409
        invalid = client.put("/api/ai/preferences", json={"enabled": "false"})
        assert invalid.status_code == 422
        assert client.put("/api/ai/preferences", json={"enabled": True}).status_code == 503
    with TestClient(create_app(db_path=db, blob_dir=tmp_path / "blobs")) as client:
        assert client.get("/api/ai/preferences").json()["choice_recorded"]
        assert client.get("/api/suggestions/status").json()["reason"] == "turned_off"


def test_local_login_cannot_request_ai_while_off(
    db: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AUDIT_DESKTOP", "1")
    save_preferences(
        Settings(data_dir=tmp_path, desktop=True),
        AIPreferences(enabled=False, choice_recorded=True),
    )
    with TestClient(
        create_app(db_path=db, blob_dir=tmp_path / "blobs"),
        base_url="http://127.0.0.1:8765",
        client=("127.0.0.1", 45678),
    ) as client:
        response = client.post(
            "/api/local-login-scans",
            headers={"origin": "http://127.0.0.1:8765"},
            json={
                "seed_url": "https://app.example.test/secure/",
                "approved_auth_origins": [],
                "authorization_acknowledged": True,
                "skip_ocr": False,
                "skip_vlm": False,
                "image_analysis_acknowledged": True,
            },
        )
        assert response.status_code == 409
        assert "AI features are off" in response.json()["detail"]


def test_toggle_and_new_model_work_are_serialized(
    db: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AUDIT_DESKTOP", "1")
    save_preferences(
        Settings(data_dir=tmp_path, desktop=True),
        AIPreferences(enabled=True, choice_recorded=True),
    )
    entered = threading.Event()
    release = threading.Event()
    original = AIManager.set_enabled

    def delayed_off(manager, enabled):
        entered.set()
        assert release.wait(5)
        return original(manager, enabled)

    monkeypatch.setattr(AIManager, "set_enabled", delayed_off)
    with (
        TestClient(create_app(db_path=db, blob_dir=tmp_path / "blobs")) as client,
        ThreadPoolExecutor(max_workers=2) as executor,
    ):
        off = executor.submit(client.put, "/api/ai/preferences", json={"enabled": False})
        assert entered.wait(2)
        scan = executor.submit(
            client.post,
            "/api/scans",
            json={"url": "https://example.com", "skip_vlm": False},
        )
        # Let the other request arrive while the off transition holds admission.
        time.sleep(0.05)
        try:
            assert not scan.done()
        finally:
            release.set()
        assert off.result(timeout=3).status_code == 200
        assert scan.result(timeout=3).status_code == 409


def test_active_scan_prevents_toggle(
    db: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AUDIT_DESKTOP", "1")
    with TestClient(create_app(db_path=db, blob_dir=tmp_path / "blobs")) as client:
        with connect(db) as conn:
            conn.execute("UPDATE scans SET status = 'running'")
        response = client.put("/api/ai/preferences", json={"enabled": False})
        assert response.status_code == 409
        assert "current scan" in response.json()["detail"]


def test_cancelled_answer_must_finish_before_off_and_saved_answers_stay_readable(
    db: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AUDIT_DESKTOP", "1")
    save_preferences(
        Settings(data_dir=tmp_path, desktop=True),
        AIPreferences(enabled=True, choice_recorded=True),
    )
    entered = threading.Event()
    release = threading.Event()

    class BlockingProvider(FakeProvider):
        async def generate(self, prompt, *, model, image):
            entered.set()
            assert await asyncio.to_thread(release.wait, 5)
            return await super().generate(prompt, model=model, image=image)

    with connect(db) as conn:
        scan_id = conn.execute("SELECT id FROM scans LIMIT 1").fetchone()["id"]
    finding_id = _add_finding(db, scan_id)
    provider = BlockingProvider()
    with TestClient(
        create_app(
            db_path=db,
            blob_dir=tmp_path / "blobs",
            suggestion_provider=provider,
            suggestion_verifier=FakeVerifier(),
        )
    ) as client:
        try:
            path = f"/api/scans/{scan_id}/suggestions"
            body = {"occurrence_kind": "a11y", "occurrence_id": finding_id}
            queued = client.post(path, json=body)
            assert queued.status_code == 202
            sid = queued.json()["id"]
            assert entered.wait(3)
            assert client.put("/api/ai/preferences", json={"enabled": False}).status_code == 409
            assert client.post(f"{path}/{sid}/cancel").status_code == 200
            # Canceling the row does not mean the model request has ended.
            assert client.put("/api/ai/preferences", json={"enabled": False}).status_code == 409
        finally:
            release.set()
        # Run another answer to completion so we can read it with AI off.
        queued = client.post(path, json=body)
        sid = queued.json()["id"]
        for _ in range(100):
            answer = client.get(f"{path}/{sid}").json()
            if answer["status"] == "ready":
                break
            time.sleep(0.02)
        assert answer["status"] == "ready"
        for _ in range(100):
            response = client.put("/api/ai/preferences", json={"enabled": False})
            if response.status_code == 200:
                break
            time.sleep(0.02)
        assert response.status_code == 200
        assert client.get(f"{path}/{sid}").json()["result"] == answer["result"]
        assert client.post(path, json=body).status_code == 403
        assert len(provider.prompts) == 2
