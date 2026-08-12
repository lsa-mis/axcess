"""Focused tests for the protected-scan persistence and evidence boundary."""

from __future__ import annotations

import hashlib
import hmac
import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

import pytest

from audit.crawler.orchestrator import CrawlConfig
from audit.protected.crypto import (
    DeterministicLocalKms,
    ProtectedDataIntegrityError,
    ProtectedVault,
)
from audit.protected.models import (
    AgentEnrollmentCreate,
    DataClassification,
    ProtectedArtifactCreate,
    ProtectedArtifactType,
    ProtectedEnvironment,
    ProtectedIndexFinding,
    ProtectedIndexPipeline,
    ProtectedPageIndex,
    ProtectedScanCreate,
    ProtectedScanStatus,
    ProtectedScopeFingerprints,
    ProtectedWorkSpec,
    scope_fingerprint_message,
)
from audit.protected.redaction import redact_mapping, redact_text, redact_url
from audit.protected.repository import (
    AgentEnrollmentError,
    ProtectedDataError,
    ProtectedEvidencePurgedError,
    claim_agent_enrollment,
    create_agent_enrollment,
    create_protected_scan,
    decrypt_protected_artifact,
    destroy_protected_scan_key,
    find_active_protected_scan_by_seed_locator,
    get_protected_scan,
    get_protected_work_spec,
    purge_expired_protected_data,
    record_protected_audit_event,
    record_protected_page_index,
    set_protected_scan_status,
    store_protected_artifact,
)
from audit.web.protected_api import _protected_public_config_json, _protected_work_config

# Keep synthetic retention windows independent of the wall clock. The former
# 2026 date made every "evidence is still available" case start failing once
# the real date crossed its seven-day cleanup deadline.
_CREATED_AT = datetime(2099, 8, 4, 12, 0, tzinfo=UTC)
_PAIRING_CODE = "michigan-protected-agent-pairing-code-1234"


def _alias(seed_url: str) -> str:
    token = hmac.new(b"protected-test-alias", seed_url.encode(), hashlib.sha256).hexdigest()
    return f"protected://report/{token}"


def _locator(seed_url: str) -> str:
    return hmac.new(b"protected-test-locator", seed_url.encode(), hashlib.sha256).hexdigest()


def _scan(conn: sqlite3.Connection, seed_url: str = "https://app.example.edu/") -> int:
    alias = _alias(seed_url)
    cursor = conn.execute(
        "INSERT INTO scans (seed_url, status, config_json) VALUES (?, 'running', ?)",
        (
            alias,
            json.dumps({"protected_work_spec": "encrypted", "seed_url": alias}),
        ),
    )
    assert cursor.lastrowid is not None
    return int(cursor.lastrowid)


def _vault() -> ProtectedVault:
    return ProtectedVault(DeterministicLocalKms(b"unit-test-local-kms-seed"))


class _RecordingProductionKms(DeterministicLocalKms):
    """Test double for a production KMS with context-scoped revocation."""

    def __init__(
        self,
        *,
        fail_destroy: bool = False,
        key_id: str = "test-production-kms",
    ) -> None:
        super().__init__(b"recording-production-kms", key_id=key_id)
        self.destroyed_contexts: list[bytes] = []
        self.fail_destroy = fail_destroy

    @property
    def supports_irreversible_scan_key_destruction(self) -> bool:
        return True

    def destroy_scan_key(self, *, context: bytes) -> None:
        self.destroyed_contexts.append(context)
        if self.fail_destroy:
            raise RuntimeError("simulated KMS revocation outage")


def _work_spec(
    seed_url: str = "https://app.example.edu/",
    *,
    approved_target_origins: tuple[str, ...] = ("https://app.example.edu",),
    approved_auth_origins: tuple[str, ...] = ("https://login.example.edu",),
    approved_cdn_origins: tuple[str, ...] = ("https://cdn.example.edu",),
) -> ProtectedWorkSpec:
    return ProtectedWorkSpec(
        seed_url=seed_url,
        approved_target_origins=approved_target_origins,
        approved_auth_origins=approved_auth_origins,
        approved_cdn_origins=approved_cdn_origins,
        index_hmac_key="d" * 64,
        config={"max_pages": 10, "axe_enabled": True, "alfa_enabled": False},
    )


def _request(**overrides: object) -> ProtectedScanCreate:
    values: dict[str, object] = {
        "target_owner": "Accessible Michigan",
        "environment": ProtectedEnvironment.STAGING,
        "data_classification": DataClassification.SENSITIVE,
        "authorized_by": "wolverineid:auditor",
        "authorization_acknowledged": True,
        "least_privilege_account_acknowledged": True,
        "approved_target_origins": ("https://app.example.edu",),
        "approved_auth_origins": ("https://login.example.edu",),
        "approved_cdn_origins": ("https://cdn.example.edu",),
    }
    values.update(overrides)
    return ProtectedScanCreate.model_validate(values)


def _scope_fingerprints(
    *,
    approved_target_origins: tuple[str, ...] = ("https://app.example.edu",),
    approved_auth_origins: tuple[str, ...] = ("https://login.example.edu",),
    approved_cdn_origins: tuple[str, ...] = ("https://cdn.example.edu",),
) -> ProtectedScopeFingerprints:
    """Use domain-separated opaque tags like the browser boundary does."""

    def tag(label: Literal["target", "auth", "cdn"], origins: tuple[str, ...]) -> str:
        return hmac.new(
            b"protected-test-scope-fingerprints",
            scope_fingerprint_message(label, origins),
            hashlib.sha256,
        ).hexdigest()

    return ProtectedScopeFingerprints(
        target=tag("target", approved_target_origins),
        auth=tag("auth", approved_auth_origins),
        cdn=tag("cdn", approved_cdn_origins),
    )


def _protected_scan(conn: sqlite3.Connection) -> tuple[int, ProtectedVault]:
    seed_url = "https://app.example.edu/"
    scan_id = _scan(conn, seed_url)
    vault = _vault()
    create_protected_scan(
        conn,
        scan_id=scan_id,
        protected_scan=_request(),
        work_spec=_work_spec(seed_url),
        scope_fingerprints=_scope_fingerprints(),
        seed_locator=_locator(seed_url),
        vault=vault,
        now=_CREATED_AT,
    )
    return scan_id, vault


def _protected_scan_with_vault(conn: sqlite3.Connection, vault: ProtectedVault) -> int:
    """Create a deterministic protected report with a caller-controlled KMS."""

    seed_url = "https://app.example.edu/"
    scan_id = _scan(conn, seed_url)
    create_protected_scan(
        conn,
        scan_id=scan_id,
        protected_scan=_request(),
        work_spec=_work_spec(seed_url),
        scope_fingerprints=_scope_fingerprints(),
        seed_locator=_locator(seed_url),
        vault=vault,
        now=_CREATED_AT,
    )
    return scan_id


def test_protected_scan_retains_approval_metadata_but_not_a_plaintext_data_key(
    tmp_db: sqlite3.Connection,
) -> None:
    scan_id = _scan(tmp_db)
    record = create_protected_scan(
        tmp_db,
        scan_id=scan_id,
        protected_scan=_request(),
        work_spec=_work_spec(),
        scope_fingerprints=_scope_fingerprints(),
        seed_locator=_locator("https://app.example.edu/"),
        vault=_vault(),
        now=_CREATED_AT,
    )

    assert record.scan_id == scan_id
    assert record.target_origin_count == 1
    assert record.auth_origin_count == 1
    assert record.cdn_origin_count == 1
    assert record.target_scope_fingerprint == _scope_fingerprints().target
    assert record.cleanup_at == _CREATED_AT + timedelta(days=7)
    assert record.is_evidence_available is True
    assert get_protected_scan(tmp_db, scan_id=scan_id) == record

    row = tmp_db.execute(
        """
        SELECT wrapped_data_key, kms_key_id, local_ai_allowed
          FROM protected_scans WHERE scan_id = ?
        """,
        (scan_id,),
    ).fetchone()
    assert row is not None
    assert isinstance(row["wrapped_data_key"], bytes)
    assert len(row["wrapped_data_key"]) > 32
    assert row["kms_key_id"] == "local-dev-memory"
    assert row["local_ai_allowed"] == 0
    columns = {
        str(column["name"])
        for column in tmp_db.execute("PRAGMA table_info(protected_scans)").fetchall()
    }
    assert {
        "approved_target_origins_json",
        "approved_auth_origins_json",
        "approved_cdn_origins_json",
    }.isdisjoint(columns)
    # Exact hostnames exist only in the encrypted work-spec ciphertext, not
    # in ordinary SQLite metadata, returned record JSON, or a SQL dump.
    plain_metadata = json.dumps(record.model_dump(mode="json"), sort_keys=True)
    assert "app.example.edu" not in plain_metadata
    assert "login.example.edu" not in plain_metadata
    assert "cdn.example.edu" not in plain_metadata
    dump = "\n".join(tmp_db.iterdump())
    assert "app.example.edu" not in dump
    assert "login.example.edu" not in dump
    assert "cdn.example.edu" not in dump


def test_work_spec_encrypts_the_seed_and_keeps_only_an_opaque_public_alias(
    tmp_db: sqlite3.Connection,
) -> None:
    seed_url = "https://app.example.edu/restricted/accessibility/review/"
    scan_id = _scan(tmp_db, seed_url)
    vault = _vault()
    create_protected_scan(
        tmp_db,
        scan_id=scan_id,
        protected_scan=_request(),
        work_spec=_work_spec(seed_url),
        scope_fingerprints=_scope_fingerprints(),
        seed_locator=_locator(seed_url),
        vault=vault,
        now=_CREATED_AT,
    )

    public_row = tmp_db.execute(
        "SELECT seed_url, config_json FROM scans WHERE id = ?", (scan_id,)
    ).fetchone()
    private_row = tmp_db.execute(
        """
        SELECT work_spec_nonce, work_spec_ciphertext, seed_locator
          FROM protected_scans WHERE scan_id = ?
        """,
        (scan_id,),
    ).fetchone()
    assert public_row is not None and private_row is not None
    assert str(public_row["seed_url"]).startswith("protected://report/")
    assert seed_url not in str(public_row["seed_url"])
    assert seed_url not in str(public_row["config_json"])
    assert seed_url.encode() not in bytes(private_row["work_spec_ciphertext"])
    assert str(private_row["seed_locator"]) == _locator(seed_url)
    assert seed_url not in "\n".join(tmp_db.iterdump())

    work = get_protected_work_spec(tmp_db, scan_id=scan_id, vault=vault)
    assert work.seed_url == seed_url
    assert work.approved_target_origins == ("https://app.example.edu",)
    assert work.approved_auth_origins == ("https://login.example.edu",)
    assert work.approved_cdn_origins == ("https://cdn.example.edu",)
    assert work.config["max_pages"] == 10
    assert (
        find_active_protected_scan_by_seed_locator(tmp_db, seed_locator=_locator(seed_url))
        == scan_id
    )


def test_work_spec_rejects_a_plaintext_public_scan_row(tmp_db: sqlite3.Connection) -> None:
    seed_url = "https://app.example.edu/secure/"
    scan_id = int(
        tmp_db.execute(
            "INSERT INTO scans (seed_url, status, config_json) VALUES (?, 'running', '{}')",
            (seed_url,),
        ).lastrowid
        or 0
    )
    with pytest.raises(ProtectedDataError, match="opaque public alias"):
        create_protected_scan(
            tmp_db,
            scan_id=scan_id,
            protected_scan=_request(),
            work_spec=_work_spec(seed_url),
            scope_fingerprints=_scope_fingerprints(),
            seed_locator=_locator(seed_url),
            vault=_vault(),
            now=_CREATED_AT,
        )


def test_work_spec_rejects_exact_origin_in_an_opaque_public_config(
    tmp_db: sqlite3.Connection,
) -> None:
    """An opaque scan alias is insufficient when its config leaks scope."""

    seed_url = "https://app.example.edu/secure/"
    scan_id = _scan(tmp_db, seed_url)
    alias = _alias(seed_url)
    tmp_db.execute(
        "UPDATE scans SET config_json = ? WHERE id = ?",
        (
            # The escaped colon proves repository validation uses parsed JSON
            # rather than a raw substring search for the private origin.
            '{"protected_work_spec":"encrypted","seed_url":"'
            + alias
            + '","approved_target_origins":["https\\u003a//app.example.edu"]}',
            scan_id,
        ),
    )
    with pytest.raises(ProtectedDataError, match="private scope"):
        create_protected_scan(
            tmp_db,
            scan_id=scan_id,
            protected_scan=_request(),
            work_spec=_work_spec(seed_url),
            scope_fingerprints=_scope_fingerprints(),
            seed_locator=_locator(seed_url),
            vault=_vault(),
            now=_CREATED_AT,
        )


def test_work_spec_scope_must_match_the_approved_request(tmp_db: sqlite3.Connection) -> None:
    """The encrypted companion allowlist cannot silently broaden approval."""

    seed_url = "https://app.example.edu/secure/"
    scan_id = _scan(tmp_db, seed_url)
    with pytest.raises(ProtectedDataError, match="scope does not match"):
        create_protected_scan(
            tmp_db,
            scan_id=scan_id,
            protected_scan=_request(),
            work_spec=_work_spec(seed_url, approved_auth_origins=()),
            scope_fingerprints=_scope_fingerprints(),
            seed_locator=_locator(seed_url),
            vault=_vault(),
            now=_CREATED_AT,
        )


def test_public_config_keeps_only_alias_and_local_ai_endpoint_stays_encrypted() -> None:
    config = CrawlConfig(
        seed_url="https://app.example.edu/secure/",
        user_agent="organization-specific-agent",
        vlm_base_url="http://127.0.0.1:11434",
        vlm_model="um-local-vision",
    )
    alias = "protected://report/" + "c" * 32

    public = json.loads(_protected_public_config_json(config, alias))
    local_ai_work = _protected_work_config(config, allow_local_ai=True)
    no_ai_work = _protected_work_config(config, allow_local_ai=False)

    assert public["seed_url"] == alias
    assert public["protected_work_spec"] == "encrypted"
    assert config.seed_url not in json.dumps(public)
    assert "user_agent" not in public
    assert "vlm_base_url" not in public
    assert "vlm_model" not in public
    assert local_ai_work["vlm_base_url"] == "http://127.0.0.1:11434"
    assert local_ai_work["vlm_model"] == "um-local-vision"
    assert "seed_url" not in local_ai_work
    assert "user_agent" not in local_ai_work
    assert "vlm_base_url" not in no_ai_work
    assert "vlm_model" not in no_ai_work


def test_work_spec_migration_scrubs_legacy_plaintext_seed_and_audit_detail(
    tmp_path: Path,
) -> None:
    """Upgrade a pre-work-spec database without leaving its scoped path behind."""

    conn = sqlite3.connect(tmp_path / "legacy-protected.db")
    migrations = Path(__file__).resolve().parents[2] / "src/audit/db/migrations"
    try:
        for path in sorted(migrations.glob("*.sql")):
            if path.name.endswith(".rollback.sql") or path.name >= "0013_protected_work_spec.sql":
                continue
            conn.executescript(path.read_text())
        seed_url = "https://app.example.edu/old-private-scope/"
        cur = conn.execute(
            "INSERT INTO scans (seed_url, status, config_json) VALUES (?, 'running', ?)",
            (seed_url, '{"seed_url":"' + seed_url + '"}'),
        )
        scan_id = int(cur.lastrowid or 0)
        conn.execute(
            """
            INSERT INTO protected_scans (
                scan_id, target_owner, environment, data_classification, authorized_by,
                authorization_acknowledged, least_privilege_account_acknowledged,
                approved_target_origins_json, kms_key_id, wrapped_data_key, cleanup_at
            ) VALUES (?, 'owner', 'staging', 'sensitive', 'auditor', 1, 1, '[]',
                      'legacy-test-kms', X'01020304', '2030-01-01 00:00:00')
            """,
            (scan_id,),
        )
        conn.execute(
            """
            INSERT INTO protected_audit_events (scan_id, actor_subject, event_type, details_json)
            VALUES (?, 'auditor', 'protected_scan.requested', ?)
            """,
            (scan_id, '{"seed":"' + seed_url + '"}'),
        )
        conn.commit()

        conn.executescript((migrations / "0013_protected_work_spec.sql").read_text())
        row = conn.execute(
            "SELECT seed_url, config_json, status FROM scans WHERE id = ?", (scan_id,)
        ).fetchone()
        detail_rows = conn.execute(
            "SELECT details_json FROM protected_audit_events WHERE scan_id = ?", (scan_id,)
        ).fetchall()
        assert row is not None
        assert row[0] == f"protected://legacy/{scan_id}"
        assert "old-private-scope" not in row[1]
        assert row[2] == "interrupted"
        assert all("old-private-scope" not in str(detail[0]) for detail in detail_rows)
        assert all(seed_url not in str(detail[0]) for detail in detail_rows)
    finally:
        conn.close()


def test_origin_scope_migration_removes_plaintext_origins_and_invalidates_v1_work(
    tmp_path: Path,
) -> None:
    """A pre-0016 database cannot retain or run a plaintext scope fallback."""

    conn = sqlite3.connect(tmp_path / "legacy-protected-origin-scope.db")
    migrations = Path(__file__).resolve().parents[2] / "src/audit/db/migrations"
    seed_url = "https://app.example.edu/old-private-scope/"
    target_origin = "https://app.example.edu"
    auth_origin = "https://login.example.edu"
    cdn_origin = "https://cdn.example.edu"
    try:
        for path in sorted(migrations.glob("*.sql")):
            if path.name.endswith(".rollback.sql") or path.name >= "0016_":
                continue
            conn.executescript(path.read_text())
        alias = "protected://report/" + "f" * 64
        scan = conn.execute(
            "INSERT INTO scans (seed_url, status, config_json) VALUES (?, 'running', ?)",
            (alias, '{"protected_work_spec":"encrypted","seed_url":"' + alias + '"}'),
        )
        scan_id = int(scan.lastrowid or 0)
        conn.execute(
            """
            INSERT INTO protected_scans (
                scan_id, target_owner, environment, data_classification, authorized_by,
                authorization_acknowledged, least_privilege_account_acknowledged,
                approved_target_origins_json, approved_auth_origins_json,
                approved_cdn_origins_json, kms_key_id, wrapped_data_key,
                work_spec_version, work_spec_nonce, work_spec_ciphertext, seed_locator,
                cleanup_at
            ) VALUES (?, 'owner', 'staging', 'sensitive', 'auditor', 1, 1,
                      ?, ?, ?, 'legacy-test-kms', X'01020304', 1, X'0102030405060708090A0B0C',
                      X'01020304', ?, '2030-01-01 00:00:00')
            """,
            (
                scan_id,
                json.dumps([target_origin]),
                json.dumps([auth_origin]),
                json.dumps([cdn_origin]),
                "d" * 64,
            ),
        )
        conn.execute(
            """
            INSERT INTO protected_audit_events (scan_id, actor_subject, event_type, details_json)
            VALUES (?, 'auditor', 'protected_scan.requested', ?)
            """,
            (scan_id, json.dumps({"approved_origin": target_origin})),
        )
        conn.commit()

        conn.executescript(
            (migrations / "0016_protected_origin_scope_confidentiality.sql").read_text()
        )
        columns = {str(column[1]) for column in conn.execute("PRAGMA table_info(protected_scans)")}
        assert {
            "approved_target_origins_json",
            "approved_auth_origins_json",
            "approved_cdn_origins_json",
        }.isdisjoint(columns)
        row = conn.execute(
            """
            SELECT target_origin_count, auth_origin_count, cdn_origin_count,
                   target_scope_fingerprint, auth_scope_fingerprint, cdn_scope_fingerprint,
                   work_spec_version, work_spec_nonce, work_spec_ciphertext, seed_locator,
                   protection_status
              FROM protected_scans WHERE scan_id = ?
            """,
            (scan_id,),
        ).fetchone()
        assert row == (1, 1, 1, None, None, None, None, None, None, None, "interrupted")
        scan_row = conn.execute("SELECT status FROM scans WHERE id = ?", (scan_id,)).fetchone()
        assert scan_row == ("interrupted",)
        details = conn.execute(
            "SELECT details_json FROM protected_audit_events WHERE scan_id = ?", (scan_id,)
        ).fetchall()
        dump = "\n".join(conn.iterdump())
        assert all(target_origin not in str(detail[0]) for detail in details)
        assert target_origin not in dump
        assert auth_origin not in dump
        assert cdn_origin not in dump
        assert seed_url not in dump

        # The yoyo rollback is deliberately lossy: it may restore schema
        # compatibility for an older binary, never the removed origin data.
        conn.executescript(
            (migrations / "0016_protected_origin_scope_confidentiality.rollback.sql").read_text()
        )
        restored = conn.execute(
            """
            SELECT approved_target_origins_json, approved_auth_origins_json,
                   approved_cdn_origins_json
              FROM protected_scans WHERE scan_id = ?
            """,
            (scan_id,),
        ).fetchone()
        assert restored == ("[]", "[]", "[]")
        assert target_origin not in "\n".join(conn.iterdump())
    finally:
        conn.close()


def test_index_hmac_key_migration_invalidates_retry_unsafe_v2_companion_work(
    tmp_path: Path,
) -> None:
    """A v2 handoff must not resume with fresh random page/occurrence aliases."""

    conn = sqlite3.connect(tmp_path / "legacy-protected-index-ids.db")
    migrations = Path(__file__).resolve().parents[2] / "src/audit/db/migrations"
    try:
        for path in sorted(migrations.glob("*.sql")):
            if path.name.endswith(".rollback.sql") or path.name >= "0018_":
                continue
            conn.executescript(path.read_text())
        alias = "protected://report/" + "a" * 64
        scan = conn.execute(
            "INSERT INTO scans (seed_url, status, config_json) VALUES (?, 'running', ?)",
            (alias, '{"protected_work_spec":"encrypted","seed_url":"' + alias + '"}'),
        )
        scan_id = int(scan.lastrowid or 0)
        conn.execute(
            """
            INSERT INTO protected_scans (
                scan_id, target_owner, environment, data_classification, authorized_by,
                authorization_acknowledged, least_privilege_account_acknowledged,
                target_origin_count, auth_origin_count, cdn_origin_count,
                target_scope_fingerprint, auth_scope_fingerprint, cdn_scope_fingerprint,
                kms_key_id, wrapped_data_key, work_spec_version, work_spec_nonce,
                work_spec_ciphertext, seed_locator, run_lease_id, run_lease_expires_at,
                cleanup_at
            ) VALUES (?, 'owner', 'staging', 'sensitive', 'auditor', 1, 1,
                      1, 0, 0, ?, ?, ?, 'legacy-test-kms', X'01020304', 2,
                      X'0102030405060708090A0B0C', X'01020304', ?, ?,
                      '2030-01-01 00:00:00', '2030-01-01 00:00:00')
            """,
            (scan_id, "b" * 64, "c" * 64, "d" * 64, "e" * 64, "lease-" + "f" * 32),
        )
        conn.execute(
            """
            INSERT INTO protected_agent_enrollments (
                id, scan_id, identity_subject, pairing_code_hash,
                certificate_fingerprint, status, expires_at
            ) VALUES ('legacy-agent', ?, 'auditor', 'scrypt-verifier', ?, 'claimed',
                      '2030-01-01 00:00:00')
            """,
            (scan_id, "1" * 64),
        )
        conn.commit()

        conn.executescript((migrations / "0018_protected_index_hmac_key.sql").read_text())
        protected = conn.execute(
            """
            SELECT protection_status, work_spec_version, work_spec_nonce,
                   work_spec_ciphertext, seed_locator, run_lease_id
              FROM protected_scans WHERE scan_id = ?
            """,
            (scan_id,),
        ).fetchone()
        assert protected == ("interrupted", None, None, None, None, None)
        assert conn.execute("SELECT status FROM scans WHERE id = ?", (scan_id,)).fetchone() == (
            "interrupted",
        )
        assert conn.execute(
            "SELECT status FROM protected_agent_enrollments WHERE id = 'legacy-agent'"
        ).fetchone() == ("revoked",)
        events = conn.execute(
            "SELECT event_type, details_json FROM protected_audit_events WHERE scan_id = ?",
            (scan_id,),
        ).fetchall()
        assert ("protected_index_key.migration_required", "{}") in events

        # The yoyo rollback is deliberately non-restorative: a v2 work item
        # would resurrect random retry identifiers and coverage duplication.
        conn.executescript((migrations / "0018_protected_index_hmac_key.rollback.sql").read_text())
        assert conn.execute(
            "SELECT work_spec_version FROM protected_scans WHERE scan_id = ?", (scan_id,)
        ).fetchone() == (None,)
    finally:
        conn.close()


def test_vault_encrypts_text_and_redacts_auth_values_before_persistence(
    tmp_db: sqlite3.Connection,
) -> None:
    scan_id, vault = _protected_scan(tmp_db)
    artifact = store_protected_artifact(
        tmp_db,
        scan_id=scan_id,
        vault=vault,
        artifact=ProtectedArtifactCreate(
            artifact_type=ProtectedArtifactType.REDACTED_EVIDENCE,
            content_type="text/plain",
            label="Request evidence for person@example.edu",
            metadata={
                "url": "https://app.example.edu/account?code=oauth-secret&page=2",
                "authorization": "Bearer never-store-this",
            },
            reviewed_and_redacted=True,
            content=(
                b"Authorization: Bearer never-store-this\n"
                b"https://app.example.edu/account?token=never-store-this&page=2\n"
                b"Contact person@example.edu or 734-555-0100"
            ),
        ),
    )

    db_row = tmp_db.execute(
        "SELECT ciphertext, metadata_json FROM protected_artifacts WHERE id = ?", (artifact.id,)
    ).fetchone()
    assert db_row is not None
    assert b"never-store-this" not in bytes(db_row["ciphertext"])
    assert "never-store-this" not in str(db_row["metadata_json"])
    assert artifact.label == "Request evidence for <redacted-email>"

    decrypted = decrypt_protected_artifact(
        tmp_db, scan_id=scan_id, artifact_id=artifact.id, vault=vault
    ).decode()
    assert "never-store-this" not in decrypted
    assert "Authorization: <redacted>" in decrypted
    assert "token=%3Credacted%3E" in decrypted
    assert "<redacted-email>" in decrypted
    assert "<redacted-phone>" in decrypted


def test_artifact_json_redaction_and_raw_browser_state_rejection(
    tmp_db: sqlite3.Connection,
) -> None:
    scan_id, vault = _protected_scan(tmp_db)
    artifact = store_protected_artifact(
        tmp_db,
        scan_id=scan_id,
        vault=vault,
        artifact=ProtectedArtifactCreate(
            artifact_type=ProtectedArtifactType.REDACTED_EVIDENCE,
            content_type="application/json",
            reviewed_and_redacted=True,
            content=b'{"cookie":"session-value","safe":"visible"}',
        ),
    )
    decrypted = decrypt_protected_artifact(
        tmp_db, scan_id=scan_id, artifact_id=artifact.id, vault=vault
    )
    assert decrypted == b'{"cookie":"<redacted>","safe":"visible"}'

    with pytest.raises(ValueError, match="raw HTML"):
        ProtectedArtifactCreate(
            artifact_type=ProtectedArtifactType.REDACTED_EVIDENCE,
            content_type="text/html",
            reviewed_and_redacted=True,
            content=b"<p>no</p>",
        )
    with pytest.raises(ValueError, match="browser state"):
        ProtectedArtifactCreate(
            artifact_type=ProtectedArtifactType.REDACTED_EVIDENCE,
            content_type="application/storage-state+json",
            reviewed_and_redacted=True,
            content=b"{}",
        )
    with pytest.raises(ProtectedDataError, match="browser state"):
        store_protected_artifact(
            tmp_db,
            scan_id=scan_id,
            vault=vault,
            artifact=ProtectedArtifactCreate(
                artifact_type=ProtectedArtifactType.REDACTED_EVIDENCE,
                content_type="application/json",
                reviewed_and_redacted=True,
                content=b'{"cookies":[{"name":"session","value":"never-store"}]}',
            ),
        )


def test_seven_day_purge_deletes_ciphertext_and_wrapped_key(tmp_db: sqlite3.Connection) -> None:
    # Retention is crypto-erasure, not ordinary local-test cleanup.  It needs
    # an adapter that can revoke historical backup decrypt paths.
    vault = ProtectedVault(_RecordingProductionKms())
    scan_id = _protected_scan_with_vault(tmp_db, vault)
    artifact = store_protected_artifact(
        tmp_db,
        scan_id=scan_id,
        vault=vault,
        artifact=ProtectedArtifactCreate(
            artifact_type=ProtectedArtifactType.PROTECTED_EXPORT,
            content_type="text/markdown",
            reviewed_and_redacted=True,
            content=b"# Redacted report",
        ),
    )

    assert (
        purge_expired_protected_data(tmp_db, now=_CREATED_AT + timedelta(days=6), vault=vault) == []
    )
    assert purge_expired_protected_data(
        tmp_db, now=_CREATED_AT + timedelta(days=7), vault=vault
    ) == [scan_id]
    assert (
        purge_expired_protected_data(tmp_db, now=_CREATED_AT + timedelta(days=8), vault=vault) == []
    )

    record = get_protected_scan(tmp_db, scan_id=scan_id)
    assert record is not None
    assert record.is_evidence_available is False
    row = tmp_db.execute(
        """
        SELECT wrapped_data_key, work_spec_nonce, work_spec_ciphertext, seed_locator,
               evidence_purged_at, key_destroyed_at
          FROM protected_scans WHERE scan_id = ?
        """,
        (scan_id,),
    ).fetchone()
    assert row is not None
    assert row["wrapped_data_key"] is None
    assert row["work_spec_nonce"] is None
    assert row["work_spec_ciphertext"] is None
    assert row["seed_locator"] is None
    assert row["evidence_purged_at"] is not None
    assert row["key_destroyed_at"] is not None
    artifact_count = tmp_db.execute(
        "SELECT COUNT(*) FROM protected_artifacts WHERE scan_id = ?", (scan_id,)
    ).fetchone()[0]
    assert artifact_count == 0
    with pytest.raises(ProtectedEvidencePurgedError):
        decrypt_protected_artifact(tmp_db, scan_id=scan_id, artifact_id=artifact.id, vault=vault)
    with pytest.raises(ProtectedEvidencePurgedError):
        get_protected_work_spec(tmp_db, scan_id=scan_id, vault=vault)
    assert (
        find_active_protected_scan_by_seed_locator(
            tmp_db, seed_locator=_locator("https://app.example.edu/")
        )
        is None
    )
    with pytest.raises(ProtectedEvidencePurgedError):
        create_agent_enrollment(
            tmp_db,
            scan_id=scan_id,
            enrollment=AgentEnrollmentCreate(
                identity_subject="wolverineid:auditor",
                certificate_fingerprint="a" * 64,
                expires_at=_CREATED_AT + timedelta(days=8, hours=1),
            ),
            pairing_code=_PAIRING_CODE,
            now=_CREATED_AT + timedelta(days=7),
        )


def test_retention_revokes_a_production_key_before_removing_ciphertext(
    tmp_db: sqlite3.Connection,
) -> None:
    """A successful purge proves the KMS call happens before SQLite cleanup."""

    class InspectingKms(_RecordingProductionKms):
        def __init__(self) -> None:
            super().__init__()
            self.artifact_counts_at_destroy: list[int] = []

        def destroy_scan_key(self, *, context: bytes) -> None:
            self.artifact_counts_at_destroy.append(
                int(tmp_db.execute("SELECT COUNT(*) FROM protected_artifacts").fetchone()[0])
            )
            super().destroy_scan_key(context=context)

    kms = InspectingKms()
    vault = ProtectedVault(kms)
    scan_id = _protected_scan_with_vault(tmp_db, vault)
    artifact = store_protected_artifact(
        tmp_db,
        scan_id=scan_id,
        vault=vault,
        artifact=ProtectedArtifactCreate(
            artifact_type=ProtectedArtifactType.REDACTED_EVIDENCE,
            content_type="text/plain",
            reviewed_and_redacted=True,
            content=b"reviewed evidence",
        ),
    )

    assert purge_expired_protected_data(
        tmp_db, now=_CREATED_AT + timedelta(days=7), vault=vault
    ) == [scan_id]
    assert kms.destroyed_contexts == [f"scan:{scan_id}".encode("ascii")]
    assert kms.artifact_counts_at_destroy == [1]
    assert (
        tmp_db.execute("SELECT 1 FROM protected_artifacts WHERE id = ?", (artifact.id,)).fetchone()
        is None
    )
    row = tmp_db.execute(
        "SELECT wrapped_data_key, key_destroyed_at FROM protected_scans WHERE scan_id = ?",
        (scan_id,),
    ).fetchone()
    assert row is not None
    assert row["wrapped_data_key"] is None
    assert row["key_destroyed_at"] is not None


def test_retention_kms_failure_keeps_ciphertext_and_key_metadata(
    tmp_db: sqlite3.Connection,
) -> None:
    """Never call a failed KMS revocation a completed crypto-erasure."""

    kms = _RecordingProductionKms(fail_destroy=True)
    vault = ProtectedVault(kms)
    scan_id = _protected_scan_with_vault(tmp_db, vault)
    artifact = store_protected_artifact(
        tmp_db,
        scan_id=scan_id,
        vault=vault,
        artifact=ProtectedArtifactCreate(
            artifact_type=ProtectedArtifactType.REDACTED_EVIDENCE,
            content_type="text/plain",
            reviewed_and_redacted=True,
            content=b"reviewed evidence",
        ),
    )

    with pytest.raises(ProtectedDataError, match="scan-key destruction failed"):
        purge_expired_protected_data(tmp_db, now=_CREATED_AT + timedelta(days=7), vault=vault)

    assert kms.destroyed_contexts == [f"scan:{scan_id}".encode("ascii")]
    row = tmp_db.execute(
        "SELECT wrapped_data_key, evidence_purged_at, key_destroyed_at FROM protected_scans "
        "WHERE scan_id = ?",
        (scan_id,),
    ).fetchone()
    assert row is not None
    assert row["wrapped_data_key"] is not None
    assert row["evidence_purged_at"] is None
    assert row["key_destroyed_at"] is None
    assert (
        tmp_db.execute("SELECT 1 FROM protected_artifacts WHERE id = ?", (artifact.id,)).fetchone()
        is not None
    )


def test_kms_binding_rejects_a_reconfigured_vault_before_private_work_or_write(
    tmp_db: sqlite3.Connection,
) -> None:
    """A new server KMS must not unwrap or append to KMS-A report evidence."""

    vault_a = ProtectedVault(_RecordingProductionKms(key_id="um-kms-a"))
    scan_id = _protected_scan_with_vault(tmp_db, vault_a)
    vault_b = ProtectedVault(_RecordingProductionKms(key_id="um-kms-b"))

    with pytest.raises(ProtectedDataError, match="protected companion work is unavailable"):
        get_protected_work_spec(tmp_db, scan_id=scan_id, vault=vault_b)
    with pytest.raises(ProtectedDataError, match="key manager is unavailable"):
        store_protected_artifact(
            tmp_db,
            scan_id=scan_id,
            vault=vault_b,
            artifact=ProtectedArtifactCreate(
                artifact_type=ProtectedArtifactType.REDACTED_EVIDENCE,
                content_type="text/plain",
                reviewed_and_redacted=True,
                content=b"reviewed evidence",
            ),
        )
    assert (
        int(
            tmp_db.execute(
                "SELECT COUNT(*) FROM protected_artifacts WHERE scan_id = ?", (scan_id,)
            ).fetchone()[0]
        )
        == 0
    )


def test_retention_refuses_wrong_or_nonrevocable_kms_without_removing_evidence(
    tmp_db: sqlite3.Connection,
) -> None:
    """KMS-B/no-op adapters cannot falsely mark a KMS-A report erased."""

    kms_a = _RecordingProductionKms(key_id="um-kms-a")
    vault_a = ProtectedVault(kms_a)
    scan_id = _protected_scan_with_vault(tmp_db, vault_a)
    artifact = store_protected_artifact(
        tmp_db,
        scan_id=scan_id,
        vault=vault_a,
        artifact=ProtectedArtifactCreate(
            artifact_type=ProtectedArtifactType.REDACTED_EVIDENCE,
            content_type="text/plain",
            reviewed_and_redacted=True,
            content=b"reviewed evidence",
        ),
    )
    kms_b = _RecordingProductionKms(key_id="um-kms-b")

    with pytest.raises(ProtectedDataError, match="key manager is unavailable"):
        purge_expired_protected_data(
            tmp_db,
            now=_CREATED_AT + timedelta(days=7),
            vault=ProtectedVault(kms_b),
        )
    assert kms_a.destroyed_contexts == []
    assert kms_b.destroyed_contexts == []

    # Even an adapter reporting the same KMS identifier cannot perform
    # retention cleanup unless it can truly revoke historical key paths.
    no_op_vault = ProtectedVault(DeterministicLocalKms(b"nonrevocable-kms-a", key_id="um-kms-a"))
    with pytest.raises(ProtectedDataError, match="irreversible key manager"):
        purge_expired_protected_data(
            tmp_db,
            now=_CREATED_AT + timedelta(days=7),
            vault=no_op_vault,
        )

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
        tmp_db.execute("SELECT 1 FROM protected_artifacts WHERE id = ?", (artifact.id,)).fetchone()
        is not None
    )


def test_report_deletion_key_revoke_is_bound_to_stored_kms_and_capability(
    tmp_db: sqlite3.Connection,
) -> None:
    """The deletion seam fails closed before an unrelated/no-op KMS is called."""

    kms_a = _RecordingProductionKms(key_id="um-kms-a")
    scan_id = _protected_scan_with_vault(tmp_db, ProtectedVault(kms_a))
    kms_b = _RecordingProductionKms(key_id="um-kms-b")

    with pytest.raises(ProtectedDataError, match="key manager is unavailable"):
        destroy_protected_scan_key(tmp_db, scan_id=scan_id, vault=ProtectedVault(kms_b))
    assert kms_a.destroyed_contexts == []
    assert kms_b.destroyed_contexts == []

    with pytest.raises(ProtectedDataError, match="irreversible key manager"):
        destroy_protected_scan_key(
            tmp_db,
            scan_id=scan_id,
            vault=ProtectedVault(DeterministicLocalKms(b"nonrevocable-kms-a", key_id="um-kms-a")),
        )
    assert kms_a.destroyed_contexts == []


def test_protected_page_index_is_idempotent_by_opaque_page_key(
    tmp_db: sqlite3.Connection,
) -> None:
    """A network retry cannot inflate protected scan coverage or occurrence totals."""

    scan_id, _vault = _protected_scan(tmp_db)
    enrollment = create_agent_enrollment(
        tmp_db,
        scan_id=scan_id,
        enrollment=AgentEnrollmentCreate(
            identity_subject="wolverineid:auditor",
            certificate_fingerprint="a" * 64,
            expires_at=_CREATED_AT + timedelta(minutes=15),
        ),
        pairing_code=_PAIRING_CODE,
        now=_CREATED_AT,
    )
    claimed = claim_agent_enrollment(
        tmp_db,
        enrollment_id=enrollment.id,
        pairing_code=_PAIRING_CODE,
        certificate_fingerprint="a" * 64,
        now=_CREATED_AT,
    )
    page = ProtectedPageIndex(
        page_key="a" * 64,
        status_code=200,
        axe_evaluated=True,
        axe_violations_total=1,
        findings=(
            ProtectedIndexFinding(
                pipeline=ProtectedIndexPipeline.AXE,
                rule_id="image-alt",
                occurrence_key="b" * 64,
                wcag_sc="1.1.1",
                wcag_scs=("1.1.1",),
                wcag_level="A",
                impact="serious",
            ),
        ),
    )

    first_page_id = record_protected_page_index(
        tmp_db,
        scan_id=scan_id,
        page=page,
        actor_subject="wolverineid:auditor",
        enrollment_id=claimed.id,
    )
    second_page_id = record_protected_page_index(
        tmp_db,
        scan_id=scan_id,
        page=page,
        actor_subject="wolverineid:auditor",
        enrollment_id=claimed.id,
    )

    assert second_page_id == first_page_id
    scan = tmp_db.execute(
        "SELECT page_count, axe_pages_scanned, axe_violations_total FROM scans WHERE id = ?",
        (scan_id,),
    ).fetchone()
    assert tuple(scan) == (1, 1, 1)
    assert (
        int(
            tmp_db.execute(
                "SELECT COUNT(*) FROM page_a11y_findings WHERE scan_id = ?", (scan_id,)
            ).fetchone()[0]
        )
        == 1
    )


def test_protected_page_index_enforces_persisted_budget_but_accepts_retries(
    tmp_db: sqlite3.Connection,
) -> None:
    """A valid companion cannot turn unbounded opaque events into a DB DoS."""

    from audit.protected import repository as protected_repository

    scan_id, _vault = _protected_scan(tmp_db)
    alias = _alias("https://app.example.edu/")
    tmp_db.execute(
        "UPDATE scans SET config_json = ? WHERE id = ?",
        (
            json.dumps(
                {
                    "protected_work_spec": "encrypted",
                    "seed_url": alias,
                    "max_pages": 1,
                }
            ),
            scan_id,
        ),
    )
    enrollment = create_agent_enrollment(
        tmp_db,
        scan_id=scan_id,
        enrollment=AgentEnrollmentCreate(
            identity_subject="wolverineid:auditor",
            certificate_fingerprint="e" * 64,
            expires_at=_CREATED_AT + timedelta(minutes=15),
        ),
        pairing_code=_PAIRING_CODE,
        now=_CREATED_AT,
    )
    claimed = claim_agent_enrollment(
        tmp_db,
        enrollment_id=enrollment.id,
        pairing_code=_PAIRING_CODE,
        certificate_fingerprint="e" * 64,
        now=_CREATED_AT,
    )
    set_protected_scan_status(
        tmp_db,
        scan_id=scan_id,
        status=ProtectedScanStatus.RUNNING,
        actor_subject="wolverineid:auditor",
    )
    first = ProtectedPageIndex(page_key="e" * 64, status_code=200)
    first_page_id = record_protected_page_index(
        tmp_db,
        scan_id=scan_id,
        page=first,
        actor_subject="wolverineid:auditor",
        enrollment_id=claimed.id,
    )

    # Lost-response retries remain valid even after the cap is reached.
    assert (
        record_protected_page_index(
            tmp_db,
            scan_id=scan_id,
            page=first,
            actor_subject="wolverineid:auditor",
            enrollment_id=claimed.id,
        )
        == first_page_id
    )
    with pytest.raises(ProtectedDataError, match="page-index capacity"):
        record_protected_page_index(
            tmp_db,
            scan_id=scan_id,
            page=first.model_copy(update={"page_key": "f" * 64}),
            actor_subject="wolverineid:auditor",
            enrollment_id=claimed.id,
        )

    assert (
        int(
            tmp_db.execute("SELECT COUNT(*) FROM pages WHERE scan_id = ?", (scan_id,)).fetchone()[0]
        )
        == 1
    )
    page_count = tmp_db.execute("SELECT page_count FROM scans WHERE id = ?", (scan_id,)).fetchone()
    assert page_count is not None and int(page_count["page_count"]) == 1

    # A corrupted/untrusted public config cannot widen companion authority
    # beyond the product hard limit, even before the normal request validator.
    tmp_db.execute(
        "UPDATE scans SET config_json = ? WHERE id = ?",
        (
            json.dumps(
                {
                    "protected_work_spec": "encrypted",
                    "seed_url": alias,
                    "max_pages": 100_001,
                }
            ),
            scan_id,
        ),
    )
    assert protected_repository._protected_index_page_limit(tmp_db, scan_id) == 10_000


def test_reauthentication_resumes_the_same_opaque_protected_index(
    tmp_db: sqlite3.Connection,
) -> None:
    """A manual re-authentication preserves prior page coverage, not a reset."""

    scan_id, _vault = _protected_scan(tmp_db)
    enrollment = create_agent_enrollment(
        tmp_db,
        scan_id=scan_id,
        enrollment=AgentEnrollmentCreate(
            identity_subject="wolverineid:auditor",
            certificate_fingerprint="c" * 64,
            expires_at=_CREATED_AT + timedelta(minutes=15),
        ),
        pairing_code=_PAIRING_CODE,
        now=_CREATED_AT,
    )
    claimed = claim_agent_enrollment(
        tmp_db,
        enrollment_id=enrollment.id,
        pairing_code=_PAIRING_CODE,
        certificate_fingerprint="c" * 64,
        now=_CREATED_AT,
    )
    page = ProtectedPageIndex(
        page_key="c" * 64,
        status_code=200,
        axe_evaluated=True,
        axe_violations_total=1,
        findings=(
            ProtectedIndexFinding(
                pipeline=ProtectedIndexPipeline.AXE,
                rule_id="button-name",
                occurrence_key="d" * 64,
                wcag_sc="4.1.2",
                wcag_scs=("4.1.2",),
                wcag_level="A",
                impact="serious",
            ),
        ),
    )

    set_protected_scan_status(
        tmp_db,
        scan_id=scan_id,
        status=ProtectedScanStatus.RUNNING,
        actor_subject="wolverineid:auditor",
    )
    first_page_id = record_protected_page_index(
        tmp_db,
        scan_id=scan_id,
        page=page,
        actor_subject="wolverineid:auditor",
        enrollment_id=claimed.id,
    )
    set_protected_scan_status(
        tmp_db,
        scan_id=scan_id,
        status=ProtectedScanStatus.AUTHENTICATION_REQUIRED,
        actor_subject="wolverineid:auditor",
    )
    set_protected_scan_status(
        tmp_db,
        scan_id=scan_id,
        status=ProtectedScanStatus.AWAITING_AUTHENTICATION,
        actor_subject="wolverineid:auditor",
    )
    set_protected_scan_status(
        tmp_db,
        scan_id=scan_id,
        status=ProtectedScanStatus.RUNNING,
        actor_subject="wolverineid:auditor",
    )
    resumed_page_id = record_protected_page_index(
        tmp_db,
        scan_id=scan_id,
        page=page,
        actor_subject="wolverineid:auditor",
        enrollment_id=claimed.id,
    )

    assert resumed_page_id == first_page_id
    counters = tmp_db.execute(
        "SELECT page_count, axe_pages_scanned, axe_violations_total FROM scans WHERE id = ?",
        (scan_id,),
    ).fetchone()
    assert tuple(counters) == (1, 1, 1)
    assert (
        tmp_db.execute("SELECT COUNT(*) FROM pages WHERE scan_id = ?", (scan_id,)).fetchone()[0]
        == 1
    )
    assert (
        tmp_db.execute(
            "SELECT COUNT(*) FROM page_a11y_findings WHERE scan_id = ?", (scan_id,)
        ).fetchone()[0]
        == 1
    )
    assert (
        tmp_db.execute(
            "SELECT COUNT(*) FROM protected_audit_events "
            "WHERE scan_id = ? AND event_type = 'protected_scan.index_reset'",
            (scan_id,),
        ).fetchone()[0]
        == 0
    )


def test_retention_deadline_blocks_private_access_before_scheduler_purges(
    tmp_db: sqlite3.Connection,
) -> None:
    """A stopped server cannot extend the seven-day evidence window."""

    scan_id, vault = _protected_scan(tmp_db)
    tmp_db.execute(
        "UPDATE protected_scans SET cleanup_at = '2000-01-01 00:00:00' WHERE scan_id = ?",
        (scan_id,),
    )

    record = get_protected_scan(tmp_db, scan_id=scan_id)
    assert record is not None
    assert record.evidence_purged_at is None
    assert record.is_evidence_available is False
    with pytest.raises(ProtectedEvidencePurgedError):
        get_protected_work_spec(tmp_db, scan_id=scan_id, vault=vault)
    with pytest.raises(ProtectedEvidencePurgedError):
        store_protected_artifact(
            tmp_db,
            scan_id=scan_id,
            vault=vault,
            artifact=ProtectedArtifactCreate(
                artifact_type=ProtectedArtifactType.REDACTED_EVIDENCE,
                content_type="text/plain",
                reviewed_and_redacted=True,
                content=b"reviewed redacted note",
            ),
        )
    with pytest.raises(ProtectedEvidencePurgedError):
        set_protected_scan_status(
            tmp_db,
            scan_id=scan_id,
            status=ProtectedScanStatus.RUNNING,
            actor_subject="wolverineid:auditor",
        )


def test_pending_agent_enrollment_cannot_claim_after_crypto_erasure(
    tmp_db: sqlite3.Connection,
) -> None:
    vault = ProtectedVault(_RecordingProductionKms())
    scan_id = _protected_scan_with_vault(tmp_db, vault)
    enrollment = create_agent_enrollment(
        tmp_db,
        scan_id=scan_id,
        enrollment=AgentEnrollmentCreate(
            identity_subject="wolverineid:auditor",
            certificate_fingerprint="a" * 64,
            expires_at=_CREATED_AT + timedelta(days=8),
        ),
        pairing_code=_PAIRING_CODE,
        now=_CREATED_AT,
    )
    purge_expired_protected_data(tmp_db, now=_CREATED_AT + timedelta(days=7), vault=vault)
    with pytest.raises(AgentEnrollmentError, match="unavailable"):
        claim_agent_enrollment(
            tmp_db,
            enrollment_id=enrollment.id,
            pairing_code=_PAIRING_CODE,
            certificate_fingerprint="a" * 64,
            now=_CREATED_AT + timedelta(days=7),
        )


def test_agent_enrollment_persists_only_an_scrypt_verifier_and_fingerprint(
    tmp_db: sqlite3.Connection,
) -> None:
    scan_id, _ = _protected_scan(tmp_db)
    enrollment = create_agent_enrollment(
        tmp_db,
        scan_id=scan_id,
        enrollment=AgentEnrollmentCreate(
            identity_subject="wolverineid:auditor",
            certificate_fingerprint="a" * 64,
            expires_at=_CREATED_AT + timedelta(hours=1),
        ),
        pairing_code=_PAIRING_CODE,
        now=_CREATED_AT,
        enrollment_id="enrollment-unit-test",
    )
    assert enrollment.status.value == "pending"
    raw_row = tmp_db.execute(
        "SELECT pairing_code_hash FROM protected_agent_enrollments WHERE id = ?", (enrollment.id,)
    ).fetchone()
    assert raw_row is not None
    assert str(raw_row["pairing_code_hash"]).startswith("scrypt$")
    assert _PAIRING_CODE not in str(raw_row["pairing_code_hash"])
    assert _PAIRING_CODE not in "\n".join(tmp_db.iterdump())

    with pytest.raises(AgentEnrollmentError, match="unavailable"):
        claim_agent_enrollment(
            tmp_db,
            enrollment_id=enrollment.id,
            pairing_code="wrong-pairing-code-0123456789",
            certificate_fingerprint="a" * 64,
            now=_CREATED_AT,
        )
    # A leaked pairing code cannot bind a different mTLS certificate after
    # the owner has already pre-bound this enrollment to certificate A.
    with pytest.raises(AgentEnrollmentError, match="unavailable"):
        claim_agent_enrollment(
            tmp_db,
            enrollment_id=enrollment.id,
            pairing_code=_PAIRING_CODE,
            certificate_fingerprint="b" * 64,
            now=_CREATED_AT,
        )
    claimed = claim_agent_enrollment(
        tmp_db,
        enrollment_id=enrollment.id,
        pairing_code=_PAIRING_CODE,
        certificate_fingerprint="AA:" * 31 + "AA",
        now=_CREATED_AT,
    )
    assert claimed.status.value == "claimed"
    assert claimed.certificate_fingerprint == "a" * 64


def test_protected_status_lifecycle_requires_reauthentication_and_never_reopens(
    tmp_db: sqlite3.Connection,
) -> None:
    """A companion cannot turn a terminal report back into a live crawl."""

    scan_id, _ = _protected_scan(tmp_db)
    assert (
        set_protected_scan_status(
            tmp_db,
            scan_id=scan_id,
            status=ProtectedScanStatus.RUNNING,
            actor_subject="wolverineid:auditor",
        ).protection_status
        is ProtectedScanStatus.RUNNING
    )
    assert (
        set_protected_scan_status(
            tmp_db,
            scan_id=scan_id,
            status=ProtectedScanStatus.AUTHENTICATION_REQUIRED,
            actor_subject="wolverineid:auditor",
        ).protection_status
        is ProtectedScanStatus.AUTHENTICATION_REQUIRED
    )
    # A fresh manual handoff is mandatory before the companion can crawl.
    assert (
        set_protected_scan_status(
            tmp_db,
            scan_id=scan_id,
            status=ProtectedScanStatus.AWAITING_AUTHENTICATION,
            actor_subject="wolverineid:auditor",
        ).protection_status
        is ProtectedScanStatus.AWAITING_AUTHENTICATION
    )
    set_protected_scan_status(
        tmp_db,
        scan_id=scan_id,
        status=ProtectedScanStatus.RUNNING,
        actor_subject="wolverineid:auditor",
    )
    set_protected_scan_status(
        tmp_db,
        scan_id=scan_id,
        status=ProtectedScanStatus.COMPLETED,
        actor_subject="wolverineid:auditor",
    )

    with pytest.raises(ProtectedDataError, match="transition"):
        set_protected_scan_status(
            tmp_db,
            scan_id=scan_id,
            status=ProtectedScanStatus.RUNNING,
            actor_subject="wolverineid:auditor",
        )


def test_only_one_companion_can_claim_a_protected_scan(
    tmp_db: sqlite3.Connection,
) -> None:
    """A leaked second pairing code cannot add another active companion."""

    scan_id, _ = _protected_scan(tmp_db)
    first = create_agent_enrollment(
        tmp_db,
        scan_id=scan_id,
        enrollment=AgentEnrollmentCreate(
            identity_subject="wolverineid:auditor",
            certificate_fingerprint="a" * 64,
            expires_at=_CREATED_AT + timedelta(hours=1),
        ),
        pairing_code=_PAIRING_CODE,
        now=_CREATED_AT,
    )
    claim_agent_enrollment(
        tmp_db,
        enrollment_id=first.id,
        pairing_code=_PAIRING_CODE,
        certificate_fingerprint="a" * 64,
        now=_CREATED_AT,
    )
    with pytest.raises(AgentEnrollmentError, match="unavailable"):
        create_agent_enrollment(
            tmp_db,
            scan_id=scan_id,
            enrollment=AgentEnrollmentCreate(
                identity_subject="wolverineid:auditor",
                certificate_fingerprint="a" * 64,
                expires_at=_CREATED_AT + timedelta(hours=1),
            ),
            pairing_code="michigan-second-protected-pairing-code-1234",
            now=_CREATED_AT,
        )


def test_companion_certificate_cannot_be_reused_for_another_protected_scan(
    tmp_db: sqlite3.Connection,
) -> None:
    """A claimed mTLS certificate is scan-bound, not a reusable agent key."""

    scan_a, _ = _protected_scan(tmp_db)
    other_seed = "https://another.example.edu/"
    scan_b = _scan(tmp_db, other_seed)
    create_protected_scan(
        tmp_db,
        scan_id=scan_b,
        protected_scan=_request(
            approved_target_origins=("https://another.example.edu",),
            approved_auth_origins=(),
            approved_cdn_origins=(),
        ),
        work_spec=_work_spec(
            other_seed,
            approved_target_origins=("https://another.example.edu",),
            approved_auth_origins=(),
            approved_cdn_origins=(),
        ),
        scope_fingerprints=_scope_fingerprints(
            approved_target_origins=("https://another.example.edu",),
            approved_auth_origins=(),
            approved_cdn_origins=(),
        ),
        seed_locator=_locator(other_seed),
        vault=_vault(),
        now=_CREATED_AT,
    )
    first = create_agent_enrollment(
        tmp_db,
        scan_id=scan_a,
        enrollment=AgentEnrollmentCreate(
            identity_subject="wolverineid:auditor",
            certificate_fingerprint="c" * 64,
            expires_at=_CREATED_AT + timedelta(hours=1),
        ),
        pairing_code=_PAIRING_CODE,
        now=_CREATED_AT,
    )
    second_code = "another-scan-protected-pairing-code-1234"
    second = create_agent_enrollment(
        tmp_db,
        scan_id=scan_b,
        enrollment=AgentEnrollmentCreate(
            identity_subject="wolverineid:auditor",
            certificate_fingerprint="c" * 64,
            expires_at=_CREATED_AT + timedelta(hours=1),
        ),
        pairing_code=second_code,
        now=_CREATED_AT,
    )
    fingerprint = "c" * 64
    claim_agent_enrollment(
        tmp_db,
        enrollment_id=first.id,
        pairing_code=_PAIRING_CODE,
        certificate_fingerprint=fingerprint,
        now=_CREATED_AT,
    )
    with pytest.raises(AgentEnrollmentError, match="enrolled"):
        claim_agent_enrollment(
            tmp_db,
            enrollment_id=second.id,
            pairing_code=second_code,
            certificate_fingerprint=fingerprint,
            now=_CREATED_AT,
        )


def test_audit_events_are_redacted_and_enrollment_cannot_cross_scans(
    tmp_db: sqlite3.Connection,
) -> None:
    scan_a, _ = _protected_scan(tmp_db)
    other_seed = "https://other.example.edu/"
    scan_b = _scan(tmp_db, other_seed)
    create_protected_scan(
        tmp_db,
        scan_id=scan_b,
        protected_scan=ProtectedScanCreate(
            target_owner="Other team",
            environment=ProtectedEnvironment.STAGING,
            data_classification=DataClassification.INTERNAL,
            authorized_by="wolverineid:other",
            authorization_acknowledged=True,
            least_privilege_account_acknowledged=True,
            approved_target_origins=("https://other.example.edu",),
        ),
        work_spec=_work_spec(
            other_seed,
            approved_target_origins=("https://other.example.edu",),
            approved_auth_origins=(),
            approved_cdn_origins=(),
        ),
        scope_fingerprints=_scope_fingerprints(
            approved_target_origins=("https://other.example.edu",),
            approved_auth_origins=(),
            approved_cdn_origins=(),
        ),
        seed_locator=_locator(other_seed),
        vault=_vault(),
        now=_CREATED_AT,
    )
    enrollment = create_agent_enrollment(
        tmp_db,
        scan_id=scan_a,
        enrollment=AgentEnrollmentCreate(
            identity_subject="wolverineid:auditor",
            certificate_fingerprint="a" * 64,
            expires_at=_CREATED_AT + timedelta(hours=1),
        ),
        pairing_code=_PAIRING_CODE,
        now=_CREATED_AT,
    )

    event_id = record_protected_audit_event(
        tmp_db,
        scan_id=scan_a,
        actor_subject="wolverineid:auditor",
        event_type="agent.heartbeat",
        details={
            "cookie": "do-not-store",
            "url": "https://app.example.edu/path?token=do-not-store",
        },
        enrollment_id=enrollment.id,
    )
    details = tmp_db.execute(
        "SELECT details_json FROM protected_audit_events WHERE id = ?", (event_id,)
    ).fetchone()["details_json"]
    assert "do-not-store" not in str(details)
    assert "<redacted>" in str(details)
    with pytest.raises(ProtectedDataError, match="does not belong"):
        record_protected_audit_event(
            tmp_db,
            scan_id=scan_b,
            actor_subject="wolverineid:other",
            event_type="agent.heartbeat",
            enrollment_id=enrollment.id,
        )


def test_crypto_rejects_wrong_scan_context_and_tampering() -> None:
    vault = _vault()
    wrapped = vault.create_wrapped_scan_key(1)
    encrypted = vault.encrypt(
        scan_id=1, artifact_id="artifact", data=b"private", wrapped_data_key=wrapped
    )
    assert (
        vault.decrypt(
            scan_id=1,
            artifact_id="artifact",
            nonce=encrypted.nonce,
            ciphertext=encrypted.ciphertext,
            wrapped_data_key=wrapped,
        )
        == b"private"
    )
    with pytest.raises(ProtectedDataIntegrityError):
        vault.decrypt(
            scan_id=2,
            artifact_id="artifact",
            nonce=encrypted.nonce,
            ciphertext=encrypted.ciphertext,
            wrapped_data_key=wrapped,
        )
    with pytest.raises(ProtectedDataIntegrityError):
        tampered_last_byte = bytes([encrypted.ciphertext[-1] ^ 0x01])
        vault.decrypt(
            scan_id=1,
            artifact_id="artifact",
            nonce=encrypted.nonce,
            ciphertext=encrypted.ciphertext[:-1] + tampered_last_byte,
            wrapped_data_key=wrapped,
        )


def test_origin_and_redaction_boundaries_are_strict() -> None:
    assert redact_url("https://user:pass@app.example.edu/a?code=secret&page=1#fragment") == (
        "https://app.example.edu/a?code=%3Credacted%3E&page=1"
    )
    assert "secret" not in redact_text("Bearer secret https://x.example.edu/?token=secret")
    assert redact_mapping({"session_cookie": "secret", "nested": {"otp": "123456"}}) == {
        "session_cookie": "<redacted>",
        "nested": {"otp": "<redacted>"},
    }
    assert redact_url("https://app.example.edu/?sessionToken=secret") == (
        "https://app.example.edu/?sessionToken=%3Credacted%3E"
    )
    assert redact_url("https://app.example.edu/?email=person@example.edu") == (
        "https://app.example.edu/?email=%3Credacted-email%3E"
    )
    with pytest.raises(ValueError, match="HTTPS"):
        _request(approved_target_origins=("http://app.example.edu",))
    with pytest.raises(ValueError, match="invalid port"):
        _request(approved_target_origins=("https://app.example.edu:0",))
    with pytest.raises(ValueError, match="userinfo"):
        _request(approved_target_origins=("https://user:pass@app.example.edu",))
    with pytest.raises(ValueError, match="hostname"):
        _request(approved_target_origins=("https://127.0.0.1",))
    with pytest.raises(ValueError, match="hostname"):
        _request(approved_target_origins=("https://app.localhost",))
    with pytest.raises(ValueError, match="local AI"):
        _request(allow_local_ai=True)
    with pytest.raises(ValueError, match="authentication material"):
        _request(authorized_by="Authorization: Bearer should-never-persist")
