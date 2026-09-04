"""Browser-facing comparison validation and ingress guards, without a listener."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from audit.db.schema import connect
from audit.web.server import create_app

pytestmark = pytest.mark.ui


def _pair(seeded_db: tuple[Path, Path, int]) -> tuple[int, int]:
    path, _, old = seeded_db
    with connect(path) as conn:
        conn.execute("UPDATE scans SET started_at='2026-09-01 12:00:00' WHERE id=?", (old,))
        current = int(
            conn.execute(
                "INSERT INTO scans(seed_url,status,config_json,started_at) "
                "VALUES('http://EXAMPLE.com:80','completed','{}','2026-09-02 12:00:00')"
            ).lastrowid
            or 0
        )
    return old, current


def test_comparison_api_and_chronological_predecessor(
    client: TestClient,
    seeded_db: tuple[Path, Path, int],
) -> None:
    old, current = _pair(seeded_db)
    response = client.get(f"/api/scans/{current}/comparison")
    assert response.status_code == 200
    data = response.json()
    assert data["current"]["id"] == current
    assert data["baseline"]["id"] == old
    assert data["page_size"] == 50
    assert data["coverage"]
    assert client.get(f"/api/scans/{old}").json()["previous_scan_id"] is None
    assert client.get(f"/api/scans/{current}").json()["previous_scan_id"] == old
    assert client.get(f"/api/scans/{old}/comparison").json()["baseline"] is None
    assert client.get(f"/api/scans/{current}/diff?compare_to={old}").status_code == 200


@pytest.mark.parametrize(
    "query,status",
    [
        ("compare_to=999999", 404),
        ("compare_to=0", 422),
        ("page_size=51", 422),
        ("page_size=0", 422),
        ("page=0", 422),
        ("category=resolved", 422),
        ("pipeline=sql", 422),
    ],
)
def test_comparison_api_validation(
    client: TestClient,
    seeded_db: tuple[Path, Path, int],
    query: str,
    status: int,
) -> None:
    _, current = _pair(seeded_db)
    assert client.get(f"/api/scans/{current}/comparison?{query}").status_code == status


def test_comparison_api_does_not_read_protected_baseline(
    client: TestClient,
    seeded_db: tuple[Path, Path, int],
) -> None:
    old, current = _pair(seeded_db)
    with connect(seeded_db[0]) as conn:
        conn.execute("ALTER TABLE protected_scans RENAME TO saved_protected_scans")
        conn.execute("CREATE TABLE protected_scans(scan_id INTEGER, authorized_by TEXT)")
        conn.execute("INSERT INTO protected_scans VALUES(?,'private-reviewer')", (old,))
    response = client.get(f"/api/scans/{current}/comparison?compare_to={old}")
    assert response.status_code == 403
    assert "private-reviewer" not in response.text
    # The automatic predecessor also skips protected reports.
    assert client.get(f"/api/scans/{current}/comparison").json()["baseline"] is None


def test_comparison_api_requires_configured_ingress_token(
    seeded_db: tuple[Path, Path, int],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, current = _pair(seeded_db)
    monkeypatch.setenv("AUDIT_ACCESS_TOKEN", "comparison-test-token")
    client = TestClient(create_app(db_path=seeded_db[0], blob_dir=seeded_db[1]))
    path = f"/api/scans/{current}/comparison"
    assert client.get(path).status_code == 401
    response = client.get(path, headers={"X-Access-Token": "comparison-test-token"})
    assert response.status_code == 200
