"""Scheduler-safe retention command tests for protected reports."""

from __future__ import annotations

import sqlite3
import sys
import types
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from typer.testing import CliRunner

from audit import cli
from audit.config import Settings
from audit.protected.crypto import DeterministicLocalKms, ProtectedVault
from audit.protected.models import (
    DataClassification,
    ProtectedArtifactCreate,
    ProtectedArtifactType,
    ProtectedEnvironment,
    ProtectedScanCreate,
    ProtectedScopeFingerprints,
    ProtectedWorkSpec,
)
from audit.protected.repository import create_protected_scan, store_protected_artifact
from audit.protected.vaults import resolve_configured_protected_vault


class _RevocableKms(DeterministicLocalKms):
    """A test KMS that models real per-scan historical-key revocation."""

    def __init__(self, *, key_id: str = "um-test-kms-a", fail_destroy: bool = False) -> None:
        super().__init__(b"protected-maintenance-test-kms", key_id=key_id)
        self.destroyed_contexts: list[bytes] = []
        self.fail_destroy = fail_destroy

    @property
    def supports_irreversible_scan_key_destruction(self) -> bool:
        return True

    def destroy_scan_key(self, *, context: bytes) -> None:
        self.destroyed_contexts.append(context)
        if self.fail_destroy:
            raise RuntimeError("provider endpoint https://kms.example.test/secret-path failed")


def _settings(tmp_db: sqlite3.Connection, tmp_path: Path, **overrides: object) -> Settings:
    db_path = Path(str(tmp_db.execute("PRAGMA database_list").fetchone()[2]))
    values: dict[str, object] = {
        "data_dir": tmp_path / "data",
        "db_path": db_path,
        "blob_dir": tmp_path / "data" / "blobs",
        "log_dir": tmp_path / "data" / "logs",
        # This intentionally proves that emergency feature disable cannot
        # suspend retention cleanup for reports already stored locally.
        "protected_scans_enabled": False,
    }
    values.update(overrides)
    return Settings(**values)


def _due_protected_report(
    conn: sqlite3.Connection,
    *,
    vault: ProtectedVault,
    scan_id: int = 842,
) -> int:
    """Create one due report plus ciphertext without putting a raw URL in SQLite."""

    seed_url = "https://app.example.test/secure/"
    alias = "protected://report/" + "a" * 64
    conn.execute(
        "INSERT INTO scans (id, seed_url, status, config_json) VALUES (?, ?, 'completed', ?)",
        (scan_id, alias, '{"protected_work_spec":"encrypted","seed_url":"' + alias + '"}'),
    )
    create_protected_scan(
        conn,
        scan_id=scan_id,
        protected_scan=ProtectedScanCreate(
            target_owner="U-M Application Team",
            environment=ProtectedEnvironment.STAGING,
            data_classification=DataClassification.SENSITIVE,
            authorized_by="wolverineid:auditor",
            authorization_acknowledged=True,
            least_privilege_account_acknowledged=True,
            approved_target_origins=("https://app.example.test",),
        ),
        work_spec=ProtectedWorkSpec(
            seed_url=seed_url,
            approved_target_origins=("https://app.example.test",),
            index_hmac_key="d" * 64,
            config={"max_pages": 10},
        ),
        scope_fingerprints=ProtectedScopeFingerprints(
            target="a" * 64,
            auth="b" * 64,
            cdn="c" * 64,
        ),
        seed_locator="c" * 64,
        vault=vault,
        now=datetime.now(UTC),
    )
    store_protected_artifact(
        conn,
        scan_id=scan_id,
        vault=vault,
        artifact=ProtectedArtifactCreate(
            artifact_type=ProtectedArtifactType.REDACTED_EVIDENCE,
            content_type="text/plain",
            reviewed_and_redacted=True,
            content=b"reviewed evidence",
        ),
    )
    # Evidence is written while live; make it due only after that normal
    # storage path succeeds, just as a scheduler would encounter it later.
    due_at = (datetime.now(UTC) - timedelta(minutes=1)).strftime("%Y-%m-%d %H:%M:%S")
    conn.execute(
        "UPDATE protected_scans SET cleanup_at = ? WHERE scan_id = ?",
        (due_at, scan_id),
    )
    conn.commit()
    return scan_id


def test_protected_maintenance_erases_due_reports_without_feature_flag(
    tmp_db: sqlite3.Connection,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    kms = _RevocableKms()
    vault = ProtectedVault(kms)
    scan_id = _due_protected_report(tmp_db, vault=vault)
    monkeypatch.setattr(cli, "get_settings", lambda: _settings(tmp_db, tmp_path))
    monkeypatch.setattr(cli, "resolve_configured_protected_vault", lambda _settings: vault)

    result = CliRunner().invoke(cli.app, ["protected-maintenance"])

    assert result.exit_code == 0, result.output
    assert "1 protected report(s) cryptographically erased" in result.output
    assert str(scan_id) not in result.output
    assert "app.example.test" not in result.output
    assert kms.destroyed_contexts == [f"scan:{scan_id}".encode("ascii")]
    row = tmp_db.execute(
        "SELECT wrapped_data_key, evidence_purged_at, key_destroyed_at "
        "FROM protected_scans WHERE scan_id = ?",
        (scan_id,),
    ).fetchone()
    assert row is not None
    assert row["wrapped_data_key"] is None
    assert row["evidence_purged_at"] is not None
    assert row["key_destroyed_at"] is not None
    assert (
        int(
            tmp_db.execute(
                "SELECT COUNT(*) FROM protected_artifacts WHERE scan_id = ?", (scan_id,)
            ).fetchone()[0]
        )
        == 0
    )


@pytest.mark.parametrize(
    "vault",
    [
        None,
        ProtectedVault(DeterministicLocalKms(b"protected-maintenance-local-kms")),
    ],
)
def test_protected_maintenance_requires_a_configured_revocable_vault(
    tmp_db: sqlite3.Connection,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    vault: ProtectedVault | None,
) -> None:
    monkeypatch.setattr(cli, "get_settings", lambda: _settings(tmp_db, tmp_path))
    monkeypatch.setattr(cli, "resolve_configured_protected_vault", lambda _settings: vault)

    result = CliRunner().invoke(cli.app, ["protected-maintenance"])

    assert result.exit_code == 2
    assert "requires a configured production KMS" in result.output
    assert "local-kms" not in result.output


@pytest.mark.parametrize("failure", ("wrong_kms", "destroy_failure"))
def test_protected_maintenance_fails_closed_without_provider_diagnostics(
    tmp_db: sqlite3.Connection,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    kms_a = _RevocableKms(key_id="um-test-kms-a")
    scan_id = _due_protected_report(tmp_db, vault=ProtectedVault(kms_a))
    if failure == "wrong_kms":
        command_vault = ProtectedVault(_RevocableKms(key_id="um-test-kms-b"))
    else:
        command_vault = ProtectedVault(_RevocableKms(fail_destroy=True))
    monkeypatch.setattr(cli, "get_settings", lambda: _settings(tmp_db, tmp_path))
    monkeypatch.setattr(cli, "resolve_configured_protected_vault", lambda _settings: command_vault)

    result = CliRunner().invoke(cli.app, ["protected-maintenance"])

    assert result.exit_code == 1
    assert "did not complete" in result.output
    assert "kms.example.test" not in result.output
    assert str(scan_id) not in result.output
    row = tmp_db.execute(
        "SELECT wrapped_data_key, evidence_purged_at, key_destroyed_at "
        "FROM protected_scans WHERE scan_id = ?",
        (scan_id,),
    ).fetchone()
    assert row is not None
    assert row["wrapped_data_key"] is not None
    assert row["evidence_purged_at"] is None
    assert row["key_destroyed_at"] is None
    assert (
        int(
            tmp_db.execute(
                "SELECT COUNT(*) FROM protected_artifacts WHERE scan_id = ?", (scan_id,)
            ).fetchone()[0]
        )
        == 1
    )


def test_protected_maintenance_succeeds_without_due_reports(
    tmp_db: sqlite3.Connection,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    vault = ProtectedVault(_RevocableKms())
    monkeypatch.setattr(cli, "get_settings", lambda: _settings(tmp_db, tmp_path))
    monkeypatch.setattr(cli, "resolve_configured_protected_vault", lambda _settings: vault)

    result = CliRunner().invoke(cli.app, ["protected-maintenance"])

    assert result.exit_code == 0, result.output
    assert "0 protected report(s) cryptographically erased" in result.output


def test_configured_vault_factory_is_loaded_from_current_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The CLI/server share a narrow administrator-configured factory seam."""

    module = types.ModuleType("axcess_test_kms_factory")
    expected = ProtectedVault(_RevocableKms())

    def build_vault(settings: Settings) -> ProtectedVault:
        assert settings.protected_kms_vault_factory == "axcess_test_kms_factory:build_vault"
        return expected

    module.build_vault = build_vault  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, module.__name__, module)
    settings = Settings(protected_kms_vault_factory="axcess_test_kms_factory:build_vault")

    assert resolve_configured_protected_vault(settings) is expected
    assert (
        resolve_configured_protected_vault(Settings(protected_kms_vault_factory="bad path")) is None
    )
