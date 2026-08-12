"""Security-contract tests for the protected-scan browser and agent APIs.

These tests deliberately exercise the route boundary instead of calling the
repository directly.  In particular, they prove that the shared LAN token is
not an identity credential, that a pairing code is one-use and never stored in
plaintext, and that a companion certificate cannot be reused for another
protected report.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import secrets
import sqlite3
import time
from collections.abc import Iterable, Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from audit.config import Settings
from audit.protected.crypto import DeterministicLocalKms, ProtectedVault

pytestmark = pytest.mark.ui

_IDENTITY_SECRET = hashlib.sha256(b"protected-route-test-proxy").hexdigest()
_AGENT_PROXY_SECRET = hashlib.sha256(b"protected-route-test-agent-proxy").hexdigest()
_REQUIRED_GROUP = "axcess-protected-scan"
_OWNER_SUBJECT = "wolverineid:accessibility-auditor"


class _RevocableTestKms(DeterministicLocalKms):
    """Test-only stand-in for an approved context-revocable KMS."""

    @property
    def supports_irreversible_scan_key_destruction(self) -> bool:
        return True

    def destroy_scan_key(self, *, context: bytes) -> None:
        # The route suite does not exercise historical-backup behavior. Its
        # unit coverage uses a recording KMS; this only models the production
        # capability gate so normal protected-route tests can create drafts.
        _ = context


def _request_payload(**overrides: object) -> dict[str, object]:
    """Return an approval-only request with no auth or browser-state fields."""
    payload: dict[str, object] = {
        "seed_url": "https://app.example.test/secure/",
        "target_owner": "U-M Application Team",
        "environment": "staging",
        "data_classification": "sensitive",
        "authorized_by": "wolverineid:accessibility-auditor",
        "authorization_acknowledged": True,
        "least_privilege_account_acknowledged": True,
        "approved_target_origins": ["https://app.example.test"],
        "approved_auth_origins": ["https://login.example.test"],
        "approved_cdn_origins": ["https://cdn.example.test"],
        "scan_engine": "both",
        "max_pages": 20,
        "max_depth": 3,
        "rps": 1.0,
    }
    payload.update(overrides)
    return payload


def _identity_headers(
    settings: Settings,
    *,
    method: str,
    path: str,
    subject: str | None = None,
    groups: tuple[str, ...] = (_REQUIRED_GROUP,),
) -> dict[str, str]:
    """Create a proxy assertion exactly as the trusted proxy would sign it."""
    resolved_subject = subject or _OWNER_SUBJECT
    timestamp = str(int(time.time()))
    nonce = secrets.token_urlsafe(18)
    groups_value = ",".join(sorted(groups))
    message = "\n".join((method.upper(), path, timestamp, nonce, resolved_subject, groups_value))
    signature = hmac.new(
        settings.protected_proxy_hmac_secret.get_secret_value().encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    headers = {
        settings.protected_identity_header: resolved_subject,
        settings.protected_groups_header: groups_value,
        settings.protected_timestamp_header: timestamp,
        settings.protected_identity_nonce_header: nonce,
        settings.protected_signature_header: signature,
    }
    if method.upper() not in {"GET", "HEAD", "OPTIONS"}:
        # TestClient serves this app at this exact origin. Protected browser
        # mutations require it just as a deployed proxy/browser flow does.
        headers["origin"] = settings.protected_public_origin
    return headers


def _agent_mtls_headers(
    settings: Settings,
    *,
    method: str,
    path: str,
    fingerprint: str,
    verified: str = "SUCCESS",
    timestamp: int | None = None,
    body: object | None = None,
    nonce: str | None = None,
) -> dict[str, str]:
    """Create the mTLS-proxy assertion that an actual TLS proxy injects.

    The companion does not know this HMAC.  A test supplies it here only to
    model the trusted proxy after it has completed client-certificate
    verification and stripped any similarly named inbound headers.
    """
    timestamp_value = str(timestamp if timestamp is not None else int(time.time()))
    normalized_verified = verified.strip().lower()
    normalized_fingerprint = fingerprint.strip().lower()
    nonce_value = nonce or secrets.token_urlsafe(18)
    # httpx serializes ``json=`` with compact separators. Keep the test-side
    # proxy assertion on the exact bytes FastAPI receives, so these tests do
    # not accidentally test a weaker semantic JSON binding.
    body_bytes = (
        b""
        if body is None
        else json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    )
    body_digest = hashlib.sha256(body_bytes).hexdigest()
    message = "\n".join(
        (
            method.upper(),
            path,
            timestamp_value,
            nonce_value,
            normalized_verified,
            normalized_fingerprint,
            body_digest,
        )
    )
    signature = hmac.new(
        settings.protected_agent_proxy_hmac_secret.get_secret_value().encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return {
        settings.protected_agent_verify_header: verified,
        settings.protected_agent_cert_header: fingerprint,
        settings.protected_agent_proxy_timestamp_header: timestamp_value,
        settings.protected_agent_proxy_nonce_header: nonce_value,
        settings.protected_agent_proxy_body_sha256_header: body_digest,
        settings.protected_agent_proxy_signature_header: signature,
    }


def _public_resolver(_: str) -> tuple[str, ...]:
    """Avoid DNS/network access while retaining the production IP policy."""
    return ("93.184.216.34",)


@pytest.fixture
def protected_client(
    seeded_db: tuple[Path, Path, int], monkeypatch: pytest.MonkeyPatch
) -> Iterator[tuple[TestClient, Settings, Path, int]]:
    """Create a protected-enabled app with an injected in-memory test KMS.

    The production policy re-resolves every hostname.  Tests inject a fixed
    public resolver so no test ever queries a live target, while preserving
    the exact-origin and public-address checks used by the API.
    """
    from audit.protected.egress import ProtectedEgressPolicy as RealPolicy
    from audit.web import protected_api, server

    db_path, blob_dir, public_scan_id = seeded_db
    settings = Settings(
        db_path=db_path,
        blob_dir=blob_dir,
        protected_scans_enabled=True,
        protected_proxy_hmac_secret=_IDENTITY_SECRET,
        protected_agent_proxy_hmac_secret=_AGENT_PROXY_SECRET,
        protected_public_origin="https://axcess.example.test",
    )

    class TestProtectedEgressPolicy(RealPolicy):
        def __init__(self, allowed_origins: Iterable[str]) -> None:
            super().__init__(allowed_origins, resolver=_public_resolver)

    monkeypatch.setattr(server, "get_settings", lambda: settings)
    monkeypatch.setattr(protected_api, "ProtectedEgressPolicy", TestProtectedEgressPolicy)
    vault = ProtectedVault(_RevocableTestKms(b"protected-route-test-kms"))
    with TestClient(
        server.create_app(db_path=db_path, blob_dir=blob_dir, protected_vault=vault),
        base_url=settings.protected_public_origin,
    ) as test_client:
        yield test_client, settings, db_path, public_scan_id


def _create_protected_draft(
    client: TestClient,
    settings: Settings,
    *,
    subject: str | None = None,
    **overrides: object,
) -> int:
    response = client.post(
        "/api/protected-scans",
        headers=_identity_headers(
            settings,
            method="POST",
            path="/api/protected-scans",
            subject=subject,
        ),
        json=_request_payload(**overrides),
    )
    assert response.status_code == 201, response.text
    return int(response.json()["scan_id"])


def _create_enrollment(
    client: TestClient,
    settings: Settings,
    scan_id: int,
    *,
    certificate_fingerprint: str = "a" * 64,
) -> dict[str, object]:
    path = f"/api/protected-scans/{scan_id}/agent-enrollments"
    response = client.post(
        path,
        headers=_identity_headers(settings, method="POST", path=path),
        json={"certificate_fingerprint": certificate_fingerprint},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_protected_scan_routes_fail_closed_when_disabled(
    seeded_db: tuple[Path, Path, int], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A route mounted in a public app must not silently accept a draft."""
    from audit.web import server

    db_path, blob_dir, _ = seeded_db
    settings = Settings(
        db_path=db_path,
        blob_dir=blob_dir,
        protected_scans_enabled=False,
        protected_proxy_hmac_secret=_IDENTITY_SECRET,
    )
    monkeypatch.setattr(server, "get_settings", lambda: settings)
    vault = ProtectedVault(DeterministicLocalKms(b"disabled-protected-test-kms"))
    app = server.create_app(db_path=db_path, blob_dir=blob_dir, protected_vault=vault)
    with TestClient(app) as client:
        capability = client.get("/api/capabilities/protected-scans")
        response = client.post(
            "/api/protected-scans",
            headers=_identity_headers(settings, method="POST", path="/api/protected-scans"),
            json=_request_payload(),
        )

    assert capability.status_code == 200
    assert capability.json()["available"] is False
    assert capability.json()["authentication"] == "manual"
    assert capability.json()["supported_sign_in"] == ["password", "mfa"]
    assert response.status_code == 404
    assert "not enabled" in response.json()["detail"].lower()


def test_protected_scan_capability_reports_ready_without_exposing_secrets(
    protected_client: tuple[TestClient, Settings, Path, int],
) -> None:
    client, settings, _, _ = protected_client
    response = client.get("/api/capabilities/protected-scans")

    assert response.status_code == 200
    assert response.json() == {
        "available": True,
        "reason": None,
        "local_available": False,
        "local_reason": ("Direct login scanning is available only from this Axcess computer."),
        "authentication": "manual",
        "supported_sign_in": ["password", "mfa"],
        "requirements": [
            "U-M-approved identity-aware proxy",
            "scan-bound companion mTLS certificate",
            "managed per-report key revocation",
        ],
    }
    serialized = response.text
    assert settings.protected_proxy_hmac_secret.get_secret_value() not in serialized
    assert settings.protected_agent_proxy_hmac_secret.get_secret_value() not in serialized


def test_shared_access_token_never_grants_protected_scan_access(
    seeded_db: tuple[Path, Path, int], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The public ingress token is not a substitute for proxy identity."""
    from audit.web import server

    db_path, blob_dir, _ = seeded_db
    settings = Settings(
        db_path=db_path,
        blob_dir=blob_dir,
        access_token="public-lan-token",
        protected_scans_enabled=True,
        protected_proxy_hmac_secret=_IDENTITY_SECRET,
    )
    monkeypatch.setattr(server, "get_settings", lambda: settings)
    vault = ProtectedVault(DeterministicLocalKms(b"token-only-protected-test-kms"))
    app = server.create_app(db_path=db_path, blob_dir=blob_dir, protected_vault=vault)
    with TestClient(app) as client:
        response = client.post(
            "/api/protected-scans",
            headers={"x-access-token": "public-lan-token"},
            json=_request_payload(),
        )

    assert response.status_code == 403
    assert "identity" in response.json()["detail"].lower()


def test_protected_identity_context_is_opaque_stable_and_subject_partitioned(
    protected_client: tuple[TestClient, Settings, Path, int],
) -> None:
    """The SPA gets a cache partition, never the proxy identity itself."""

    client, settings, _, _ = protected_client
    path = "/api/protected-scans/identity-context"
    owner = client.get(
        path,
        headers=_identity_headers(settings, method="GET", path=path),
    )
    other_subject = "wolverineid:another-protected-auditor"
    other = client.get(
        path,
        headers=_identity_headers(
            settings,
            method="GET",
            path=path,
            subject=other_subject,
        ),
    )

    assert owner.status_code == 200
    assert other.status_code == 200
    assert owner.headers["cache-control"] == "no-store, private, max-age=0"
    assert owner.json().keys() == {"subject_fingerprint"}
    owner_fingerprint = owner.json()["subject_fingerprint"]
    expected = hmac.new(
        settings.protected_proxy_hmac_secret.get_secret_value().encode("utf-8"),
        b"axcess/protected-browser-identity-context/v1\x00" + _OWNER_SUBJECT.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    assert owner_fingerprint == expected
    assert len(owner_fingerprint) == 64
    assert owner_fingerprint != other.json()["subject_fingerprint"]
    assert _OWNER_SUBJECT not in owner.text
    assert other_subject not in other.text


def test_protected_draft_persists_approval_metadata_without_secrets(
    protected_client: tuple[TestClient, Settings, Path, int],
) -> None:
    client, settings, db_path, _ = protected_client
    scan_id = _create_protected_draft(client, settings)

    detail_path = f"/api/protected-scans/{scan_id}"
    detail = client.get(
        detail_path,
        headers=_identity_headers(settings, method="GET", path=detail_path),
    )
    assert detail.status_code == 200
    body = detail.json()
    assert body["scan_id"] == scan_id
    assert body["protection_status"] == "awaiting_authentication"
    assert body["target_origin_count"] == 1
    assert body["auth_origin_count"] == 1
    assert body["cdn_origin_count"] == 1
    assert body["progress"] == {
        "pages_indexed": 0,
        "issue_occurrences": 0,
        "axe_occurrences": 0,
        "alfa_failed_occurrences": 0,
        "alfa_review_occurrences": 0,
        "probe_occurrences": 0,
    }
    assert isinstance(body["target_scope_fingerprint"], str)
    assert len(body["target_scope_fingerprint"]) == 64
    assert "approved_target_origins" not in body
    assert "wrapped_data_key" not in body
    assert "seed_url" not in body

    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute(
            "SELECT seed_url, status, config_json FROM scans WHERE id = ?", (scan_id,)
        ).fetchone()
        assert row is not None
        assert str(row[0]).startswith("protected://report/")
        assert "app.example.test" not in str(row[0])
        assert row[1] == "interrupted"
        config = json.loads(str(row[2]))
        serialized = json.dumps(config).lower()
        assert "app.example.test" not in serialized
        assert config["seed_url"] == row[0]
        assert config["protected_work_spec"] == "encrypted"
        assert "password" not in serialized
        assert "cookie" not in serialized
        assert "storage_state" not in serialized
        assert "authorization" not in serialized
        assert config["concurrency_per_host"] == 1
        assert config["visual_checks_enabled"] is False
        private = conn.execute(
            """
            SELECT seed_locator, work_spec_nonce, work_spec_ciphertext
              FROM protected_scans WHERE scan_id = ?
            """,
            (scan_id,),
        ).fetchone()
        assert private is not None
        assert len(str(private[0])) == 64
        assert b"/secure/" not in bytes(private[2])
        # Both the seed path and every exact approved origin belong only to
        # the encrypted work spec. The ordinary SQLite rows retain opaque
        # aliases, counts, and keyed scope tags—not hostnames.
        dump = "\n".join(conn.iterdump())
        assert "/secure/" not in dump
        assert "app.example.test" not in dump
        assert "login.example.test" not in dump
        assert "cdn.example.test" not in dump
    finally:
        conn.close()

    unsafe_metadata = _request_payload(target_owner="Authorization: Bearer do-not-store")
    refusal = client.post(
        "/api/protected-scans",
        headers=_identity_headers(settings, method="POST", path="/api/protected-scans"),
        json=unsafe_metadata,
    )
    assert refusal.status_code == 422
    assert refusal.json() == {"detail": "Invalid protected request."}
    assert "do-not-store" not in refusal.text


def test_duplicate_protected_drafts_use_a_keyed_locator_not_plaintext_seed_lookup(
    protected_client: tuple[TestClient, Settings, Path, int],
) -> None:
    client, settings, db_path, _ = protected_client
    first = _create_protected_draft(client, settings)
    response = client.post(
        "/api/protected-scans",
        headers=_identity_headers(settings, method="POST", path="/api/protected-scans"),
        json=_request_payload(),
    )
    assert response.status_code == 409

    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute(
            "SELECT seed_locator FROM protected_scans WHERE scan_id = ?", (first,)
        ).fetchone()
        assert row is not None
        assert str(row[0]) != "https://app.example.test/secure/"
        assert len(str(row[0])) == 64
    finally:
        conn.close()


def test_protected_progress_returns_only_page_anonymous_counts(
    protected_client: tuple[TestClient, Settings, Path, int],
) -> None:
    client, settings, db_path, _ = protected_client
    scan_id = _create_protected_draft(client, settings)
    conn = sqlite3.connect(str(db_path))
    try:
        page = conn.execute(
            """
            INSERT INTO pages
                (scan_id, url_normalized, status_code, title, render_mode, html_hash)
            VALUES (?, ?, 200, NULL, 'js', 'protected-progress-page')
            """,
            (scan_id, f"protected://report/{scan_id}/page/opaque-1"),
        )
        page_id = int(page.lastrowid or 0)
        conn.executemany(
            """
            INSERT INTO page_a11y_findings
                (page_id, scan_id, pipeline, engine_outcome, rule_id,
                 target_hash, help, target_selector, status)
            VALUES (?, ?, ?, ?, ?, ?, 'Protected index evidence', 'opaque', 'new')
            """,
            (
                (page_id, scan_id, "axe", "failed", "image-alt", "progress-axe"),
                (page_id, scan_id, "alfa", "failed", "sia-r2", "progress-alfa-failed"),
                (
                    page_id,
                    scan_id,
                    "alfa",
                    "cant_tell",
                    "sia-r69",
                    "progress-alfa-review",
                ),
                (
                    page_id,
                    scan_id,
                    "keyboard",
                    "failed",
                    "keyboard-trap-stuck",
                    "progress-keyboard",
                ),
            ),
        )
        conn.execute("UPDATE scans SET page_count = 1 WHERE id = ?", (scan_id,))
        conn.commit()
    finally:
        conn.close()

    path = f"/api/protected-scans/{scan_id}"
    response = client.get(
        path,
        headers=_identity_headers(settings, method="GET", path=path),
    )
    assert response.status_code == 200
    progress = response.json()["progress"]
    assert progress == {
        "pages_indexed": 1,
        "issue_occurrences": 4,
        "axe_occurrences": 1,
        "alfa_failed_occurrences": 1,
        "alfa_review_occurrences": 1,
        "probe_occurrences": 1,
    }
    assert "opaque-1" not in response.text
    assert "image-alt" not in response.text


def test_protected_report_access_is_isolated_to_its_creating_identity(
    protected_client: tuple[TestClient, Settings, Path, int],
) -> None:
    """A group member cannot read, export, or pair a companion to another report."""

    client, settings, _, _ = protected_client
    owner = "wolverineid:report-owner"
    outsider = "wolverineid:other-protected-auditor"
    owner_scan_id = _create_protected_draft(
        client,
        settings,
        subject=owner,
        seed_url="https://owner.example.test/secure/",
        approved_target_origins=["https://owner.example.test"],
    )

    protected_path = f"/api/protected-scans/{owner_scan_id}"
    generic_path = f"/api/scans/{owner_scan_id}"
    enroll_path = f"/api/protected-scans/{owner_scan_id}/agent-enrollments"
    for path, method in ((protected_path, "GET"), (generic_path, "GET"), (enroll_path, "POST")):
        headers = _identity_headers(settings, method=method, path=path, subject=outsider)
        response = (
            client.get(path, headers=headers)
            if method == "GET"
            else client.post(path, headers=headers, json={"certificate_fingerprint": "a" * 64})
        )
        assert response.status_code == 403
        assert "permission" in response.json()["detail"].lower()

    # A verified group member must not be able to distinguish a different
    # auditor's report from a nonexistent protected scan by status code.
    missing_path = "/api/protected-scans/999999"
    missing = client.get(
        missing_path,
        headers=_identity_headers(settings, method="GET", path=missing_path, subject=outsider),
    )
    assert missing.status_code == 403
    assert missing.json()["detail"] == "Protected-report permission required."

    # The opaque seed locator is a server-held HMAC, but a second authorized
    # auditor may still know the same target URL. Their draft check is scoped
    # to their verified identity so it cannot reveal or block the owner's
    # in-progress report.
    outsider_scan_id = _create_protected_draft(
        client,
        settings,
        subject=outsider,
        seed_url="https://owner.example.test/secure/",
        approved_target_origins=["https://owner.example.test"],
    )
    assert outsider_scan_id != owner_scan_id

    owner_detail = client.get(
        protected_path,
        headers=_identity_headers(settings, method="GET", path=protected_path, subject=owner),
    )
    assert owner_detail.status_code == 200
    assert owner_detail.json()["scan_id"] == owner_scan_id


def test_pairing_is_one_time_hashed_and_mtls_is_bound_to_the_exact_scan(
    protected_client: tuple[TestClient, Settings, Path, int],
) -> None:
    client, settings, db_path, _ = protected_client
    scan_a = _create_protected_draft(client, settings)
    enrollment_a = _create_enrollment(client, settings, scan_a)
    enrollment_id_a = str(enrollment_a["enrollment_id"])
    pairing_code_a = str(enrollment_a["pairing_code"])
    fingerprint_a = "a" * 64

    conn = sqlite3.connect(str(db_path))
    try:
        pairing_hash = conn.execute(
            "SELECT pairing_code_hash FROM protected_agent_enrollments WHERE id = ?",
            (enrollment_id_a,),
        ).fetchone()
        assert pairing_hash is not None
        assert pairing_code_a not in str(pairing_hash[0])
        assert str(pairing_hash[0]).startswith("scrypt$")
    finally:
        conn.close()

    work_path_a = f"/api/agents/{enrollment_id_a}/work"
    assert client.get(work_path_a).status_code == 403

    # A pairing code is not an mTLS credential and cannot claim a scan before
    # the proxy proves the pre-bound companion certificate.
    missing_enrollment_mtls = client.post(
        "/api/agents/enroll",
        json={
            "enrollment_id": enrollment_id_a,
            "pairing_code": pairing_code_a,
        },
    )
    assert missing_enrollment_mtls.status_code == 403

    # Treat this as a stolen-code regression: another certificate accepted by
    # the mTLS proxy still cannot claim work for this scan, because the owner
    # bound the pairing request to certificate A before the code was issued.
    stolen_code = client.post(
        "/api/agents/enroll",
        headers=_agent_mtls_headers(
            settings,
            method="POST",
            path="/api/agents/enroll",
            fingerprint="b" * 64,
            body={
                "enrollment_id": enrollment_id_a,
                "pairing_code": pairing_code_a,
            },
        ),
        json={
            "enrollment_id": enrollment_id_a,
            "pairing_code": pairing_code_a,
        },
    )
    assert stolen_code.status_code == 403

    rejected_claim = client.post(
        "/api/agents/enroll",
        headers=_agent_mtls_headers(
            settings,
            method="POST",
            path="/api/agents/enroll",
            fingerprint=fingerprint_a,
            body={
                "enrollment_id": enrollment_id_a,
                "pairing_code": "incorrect-pairing-code-that-is-long-enough",
            },
        ),
        json={
            "enrollment_id": enrollment_id_a,
            "pairing_code": "incorrect-pairing-code-that-is-long-enough",
        },
    )
    assert rejected_claim.status_code == 403

    accepted_claim = client.post(
        "/api/agents/enroll",
        headers=_agent_mtls_headers(
            settings,
            method="POST",
            path="/api/agents/enroll",
            fingerprint=fingerprint_a,
            body={
                "enrollment_id": enrollment_id_a,
                "pairing_code": pairing_code_a,
            },
        ),
        json={
            "enrollment_id": enrollment_id_a,
            "pairing_code": pairing_code_a,
        },
    )
    assert accepted_claim.status_code == 201
    assert accepted_claim.json()["scan_id"] == scan_a
    assert accepted_claim.json()["mtls_required"] is True
    assert pairing_code_a not in accepted_claim.text

    companion_path = f"/api/protected-scans/{scan_a}/companion"
    companion = client.get(
        companion_path,
        headers=_identity_headers(settings, method="GET", path=companion_path),
    )
    assert companion.status_code == 200
    companion_body = companion.json()["companion"]
    assert companion_body["enrollment_id"] == enrollment_id_a
    assert "--server https://axcess.example.test" in companion_body["companion_run_command"]
    assert pairing_code_a not in companion.text
    assert fingerprint_a not in companion.text
    assert "app.example.test" not in companion.text

    # A claimed code cannot enroll a second companion, even with another key.
    replayed_claim = client.post(
        "/api/agents/enroll",
        headers=_agent_mtls_headers(
            settings,
            method="POST",
            path="/api/agents/enroll",
            fingerprint="c" * 64,
            body={
                "enrollment_id": enrollment_id_a,
                "pairing_code": pairing_code_a,
            },
        ),
        json={
            "enrollment_id": enrollment_id_a,
            "pairing_code": pairing_code_a,
        },
    )
    assert replayed_claim.status_code == 403

    wrong_cert = client.get(
        work_path_a,
        headers=_agent_mtls_headers(
            settings,
            method="GET",
            path=work_path_a,
            fingerprint="b" * 64,
        ),
    )
    assert wrong_cert.status_code == 403
    granted_work = client.get(
        work_path_a,
        headers=_agent_mtls_headers(
            settings,
            method="GET",
            path=work_path_a,
            fingerprint=fingerprint_a,
        ),
    )
    assert granted_work.status_code == 200
    assert granted_work.json()["scan_id"] == scan_a
    assert granted_work.json()["seed_url"] == "https://app.example.test/secure/"
    assert "seed_url" not in granted_work.json()["config"]
    assert pairing_code_a not in granted_work.text

    # A separate report can enroll a separate companion, but its work endpoint
    # must reject certificate A. This is the important per-scan isolation test.
    scan_b = _create_protected_draft(
        client,
        settings,
        seed_url="https://other.example.test/secure/",
        approved_target_origins=["https://other.example.test"],
    )
    enrollment_b = _create_enrollment(client, settings, scan_b, certificate_fingerprint="b" * 64)
    enrollment_id_b = str(enrollment_b["enrollment_id"])
    claim_b = client.post(
        "/api/agents/enroll",
        headers=_agent_mtls_headers(
            settings,
            method="POST",
            path="/api/agents/enroll",
            fingerprint="b" * 64,
            body={
                "enrollment_id": enrollment_id_b,
                "pairing_code": str(enrollment_b["pairing_code"]),
            },
        ),
        json={
            "enrollment_id": enrollment_id_b,
            "pairing_code": str(enrollment_b["pairing_code"]),
        },
    )
    assert claim_b.status_code == 201
    work_path_b = f"/api/agents/{enrollment_id_b}/work"
    cross_scan = client.get(
        work_path_b,
        headers=_agent_mtls_headers(
            settings,
            method="GET",
            path=work_path_b,
            fingerprint=fingerprint_a,
        ),
    )
    assert cross_scan.status_code == 403


def test_agent_mtls_headers_require_a_signed_proxy_attestation(
    protected_client: tuple[TestClient, Settings, Path, int],
) -> None:
    """A direct client cannot impersonate the TLS terminator with headers."""

    client, settings, _, _ = protected_client
    scan_id = _create_protected_draft(client, settings)
    enrollment = _create_enrollment(client, settings, scan_id, certificate_fingerprint="e" * 64)
    enrollment_id = str(enrollment["enrollment_id"])
    pairing_code = str(enrollment["pairing_code"])
    fingerprint = "e" * 64

    # These used to be enough to impersonate a proxy on a mistakenly exposed
    # application listener. They now lack the separately signed proxy proof.
    unsigned = client.post(
        "/api/agents/enroll",
        headers={
            settings.protected_agent_verify_header: "SUCCESS",
            settings.protected_agent_cert_header: fingerprint,
        },
        json={
            "enrollment_id": enrollment_id,
            "pairing_code": pairing_code,
        },
    )
    assert unsigned.status_code == 403
    assert "signed" in unsigned.json()["detail"].lower()

    expired = client.post(
        "/api/agents/enroll",
        headers=_agent_mtls_headers(
            settings,
            method="POST",
            path="/api/agents/enroll",
            fingerprint=fingerprint,
            timestamp=int(time.time()) - settings.protected_agent_proxy_max_age_s - 1,
            body={
                "enrollment_id": enrollment_id,
                "pairing_code": pairing_code,
            },
        ),
        json={
            "enrollment_id": enrollment_id,
            "pairing_code": pairing_code,
        },
    )
    assert expired.status_code == 403
    assert "expired" in expired.json()["detail"].lower()

    claimed = client.post(
        "/api/agents/enroll",
        headers=_agent_mtls_headers(
            settings,
            method="POST",
            path="/api/agents/enroll",
            fingerprint=fingerprint,
            body={
                "enrollment_id": enrollment_id,
                "pairing_code": pairing_code,
            },
        ),
        json={
            "enrollment_id": enrollment_id,
            "pairing_code": pairing_code,
        },
    )
    assert claimed.status_code == 201, claimed.text

    work_path = f"/api/agents/{enrollment_id}/work"
    wrong_path = client.get(
        work_path,
        headers=_agent_mtls_headers(
            settings,
            method="GET",
            path="/api/agents/enroll",
            fingerprint=fingerprint,
        ),
    )
    assert wrong_path.status_code == 403
    assert "invalid companion proxy" in wrong_path.json()["detail"].lower()


def test_agent_proxy_attestation_is_single_use_and_binds_exact_body(
    protected_client: tuple[TestClient, Settings, Path, int],
) -> None:
    """A signed mTLS request cannot be replayed or retargeted to new JSON."""

    client, settings, _, _ = protected_client
    scan_id = _create_protected_draft(client, settings)
    enrollment = _create_enrollment(client, settings, scan_id, certificate_fingerprint="9" * 64)
    fingerprint = "9" * 64
    claim_body = {
        "enrollment_id": str(enrollment["enrollment_id"]),
        "pairing_code": str(enrollment["pairing_code"]),
    }
    replay_headers = _agent_mtls_headers(
        settings,
        method="POST",
        path="/api/agents/enroll",
        fingerprint=fingerprint,
        body=claim_body,
        nonce="proxy-issued-single-use-nonce",
    )
    claimed = client.post("/api/agents/enroll", headers=replay_headers, json=claim_body)
    assert claimed.status_code == 201, claimed.text

    work_path = f"/api/agents/{enrollment['enrollment_id']}/work"
    work = client.get(
        work_path,
        headers=_agent_mtls_headers(
            settings,
            method="GET",
            path=work_path,
            fingerprint=fingerprint,
        ),
    )
    assert work.status_code == 200, work.text
    heartbeat_path = f"/api/agents/{enrollment['enrollment_id']}/heartbeat"
    heartbeat_body = {"run_lease_id": work.json()["run_lease_id"]}
    replay_headers = _agent_mtls_headers(
        settings,
        method="POST",
        path=heartbeat_path,
        fingerprint=fingerprint,
        body=heartbeat_body,
        nonce="proxy-issued-heartbeat-nonce",
    )
    first_heartbeat = client.post(heartbeat_path, headers=replay_headers, json=heartbeat_body)
    assert first_heartbeat.status_code == 200, first_heartbeat.text

    replayed = client.post(heartbeat_path, headers=replay_headers, json=heartbeat_body)
    assert replayed.status_code == 403
    assert "already used" in replayed.json()["detail"].lower()

    tampered_body = {"run_lease_id": "a" * 24}
    tampered = client.post(heartbeat_path, headers=replay_headers, json=tampered_body)
    assert tampered.status_code == 403
    assert "body did not match" in tampered.json()["detail"].lower()


def test_protected_draft_rejects_nonrevocable_local_development_kms(
    seeded_db: tuple[Path, Path, int], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every protected environment rejects a non-revocable development KEK."""

    from audit.protected.egress import ProtectedEgressPolicy as RealPolicy
    from audit.web import protected_api, server

    db_path, blob_dir, _ = seeded_db

    class TestProtectedEgressPolicy(RealPolicy):
        def __init__(self, allowed_origins: Iterable[str]) -> None:
            super().__init__(allowed_origins, resolver=_public_resolver)

    settings = Settings(
        db_path=db_path,
        blob_dir=blob_dir,
        protected_scans_enabled=True,
        protected_proxy_hmac_secret=_IDENTITY_SECRET,
        protected_agent_proxy_hmac_secret=_AGENT_PROXY_SECRET,
        protected_public_origin="https://axcess.example.test",
    )
    monkeypatch.setattr(server, "get_settings", lambda: settings)
    monkeypatch.setattr(protected_api, "ProtectedEgressPolicy", TestProtectedEgressPolicy)
    vault = ProtectedVault(DeterministicLocalKms(b"local-nonrevocable-test-kms"))

    with TestClient(
        server.create_app(db_path=db_path, blob_dir=blob_dir, protected_vault=vault),
        base_url=settings.protected_public_origin,
    ) as client:
        response = client.post(
            "/api/protected-scans",
            headers=_identity_headers(settings, method="POST", path="/api/protected-scans"),
            json=_request_payload(environment="staging"),
        )
        assert response.status_code == 503
        assert "irreversibly revoke" in response.json()["detail"].lower()


def test_generic_delete_revokes_protected_key_before_database_cascade(
    seeded_db: tuple[Path, Path, int], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Deleting a stopped protected report never leaves a usable backup key path."""

    from audit.protected.egress import ProtectedEgressPolicy as RealPolicy
    from audit.web import protected_api, server

    db_path, blob_dir, _ = seeded_db

    class InspectingKms(DeterministicLocalKms):
        def __init__(self) -> None:
            super().__init__(b"protected-delete-production-kms", key_id="test-production-kms")
            self.destroyed_contexts: list[bytes] = []
            self.scan_rows_at_destroy: list[int] = []

        @property
        def supports_irreversible_scan_key_destruction(self) -> bool:
            return True

        def destroy_scan_key(self, *, context: bytes) -> None:
            conn = sqlite3.connect(str(db_path))
            try:
                self.scan_rows_at_destroy.append(
                    int(conn.execute("SELECT COUNT(*) FROM scans").fetchone()[0])
                )
            finally:
                conn.close()
            self.destroyed_contexts.append(context)

    class TestProtectedEgressPolicy(RealPolicy):
        def __init__(self, allowed_origins: Iterable[str]) -> None:
            super().__init__(allowed_origins, resolver=_public_resolver)

    settings = Settings(
        db_path=db_path,
        blob_dir=blob_dir,
        protected_scans_enabled=True,
        protected_proxy_hmac_secret=_IDENTITY_SECRET,
        protected_agent_proxy_hmac_secret=_AGENT_PROXY_SECRET,
        protected_public_origin="https://axcess.example.test",
    )
    monkeypatch.setattr(server, "get_settings", lambda: settings)
    monkeypatch.setattr(protected_api, "ProtectedEgressPolicy", TestProtectedEgressPolicy)
    kms = InspectingKms()
    with TestClient(
        server.create_app(
            db_path=db_path,
            blob_dir=blob_dir,
            protected_vault=ProtectedVault(kms),
        ),
        base_url=settings.protected_public_origin,
    ) as client:
        scan_id = _create_protected_draft(client, settings)
        conn = sqlite3.connect(str(db_path))
        try:
            conn.execute(
                "UPDATE protected_scans SET protection_status = 'interrupted' WHERE scan_id = ?",
                (scan_id,),
            )
            conn.commit()
        finally:
            conn.close()
        path = f"/api/scans/{scan_id}"
        deleted = client.delete(
            path,
            headers=_identity_headers(settings, method="DELETE", path=path),
        )

    assert deleted.status_code == 200, deleted.text
    assert kms.destroyed_contexts == [f"scan:{scan_id}".encode("ascii")]
    assert kms.scan_rows_at_destroy and kms.scan_rows_at_destroy[0] > 0
    conn = sqlite3.connect(str(db_path))
    try:
        assert conn.execute("SELECT 1 FROM scans WHERE id = ?", (scan_id,)).fetchone() is None
    finally:
        conn.close()


def test_generic_delete_refuses_a_reconfigured_protected_kms(
    protected_client: tuple[TestClient, Settings, Path, int],
) -> None:
    """A KMS-B restart cannot delete KMS-A ciphertext without revocation."""

    from audit.web import server

    client, settings, db_path, _ = protected_client
    scan_id = _create_protected_draft(client, settings)
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "UPDATE protected_scans SET protection_status = 'interrupted' WHERE scan_id = ?",
            (scan_id,),
        )
        conn.commit()
    finally:
        conn.close()

    class WrongKms(_RevocableTestKms):
        def __init__(self) -> None:
            super().__init__(b"protected-delete-wrong-kms", key_id="um-kms-b")
            self.destroyed_contexts: list[bytes] = []

        def destroy_scan_key(self, *, context: bytes) -> None:
            self.destroyed_contexts.append(context)

    wrong_kms = WrongKms()
    with TestClient(
        server.create_app(
            db_path=db_path,
            blob_dir=settings.blob_dir,
            protected_vault=ProtectedVault(wrong_kms),
        ),
        base_url=settings.protected_public_origin,
    ) as reconfigured_client:
        path = f"/api/scans/{scan_id}"
        deleted = reconfigured_client.delete(
            path,
            headers=_identity_headers(settings, method="DELETE", path=path),
        )

    assert deleted.status_code == 503
    assert "could not revoke" in deleted.json()["detail"].lower()
    assert "kms" not in deleted.json()["detail"].lower()
    assert wrong_kms.destroyed_contexts == []
    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute(
            "SELECT wrapped_data_key, evidence_purged_at FROM protected_scans WHERE scan_id = ?",
            (scan_id,),
        ).fetchone()
        assert row is not None
        assert row[0] is not None
        assert row[1] is None
        assert conn.execute("SELECT 1 FROM scans WHERE id = ?", (scan_id,)).fetchone() is not None
    finally:
        conn.close()


def test_startup_keeps_public_workbench_available_when_due_kms_is_mismatched(
    protected_client: tuple[TestClient, Settings, Path, int],
) -> None:
    """A protected retention fault is fail-closed for evidence, not the app."""

    from audit.web import server

    client, settings, db_path, _ = protected_client
    scan_id = _create_protected_draft(client, settings)
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "UPDATE protected_scans SET cleanup_at = '2000-01-01 00:00:00' WHERE scan_id = ?",
            (scan_id,),
        )
        conn.commit()
    finally:
        conn.close()

    wrong_vault = ProtectedVault(
        _RevocableTestKms(b"protected-retention-wrong-kms", key_id="um-kms-b")
    )
    with TestClient(
        server.create_app(
            db_path=db_path,
            blob_dir=settings.blob_dir,
            protected_vault=wrong_vault,
        ),
        base_url=settings.protected_public_origin,
    ) as reconfigured_client:
        assert reconfigured_client.get("/health").status_code == 200

    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute(
            "SELECT wrapped_data_key, evidence_purged_at FROM protected_scans WHERE scan_id = ?",
            (scan_id,),
        ).fetchone()
        assert row is not None
        assert row[0] is not None
        assert row[1] is None
    finally:
        conn.close()


def test_agent_routes_fail_closed_without_a_proxy_signing_secret(
    protected_client: tuple[TestClient, Settings, Path, int],
) -> None:
    """mTLS headers are never accepted when proxy HMAC setup is absent."""

    client, settings, _, _ = protected_client
    scan_id = _create_protected_draft(client, settings)
    enrollment = _create_enrollment(client, settings, scan_id, certificate_fingerprint="d" * 64)
    settings.protected_agent_proxy_hmac_secret = SecretStr("")
    fingerprint = "f" * 64

    response = client.post(
        "/api/agents/enroll",
        headers={
            settings.protected_agent_verify_header: "SUCCESS",
            settings.protected_agent_cert_header: fingerprint,
        },
        json={
            "enrollment_id": str(enrollment["enrollment_id"]),
            "pairing_code": str(enrollment["pairing_code"]),
        },
    )
    assert response.status_code == 503
    assert "signed mtls proxy" in response.json()["detail"].lower()


def test_protected_draft_requires_a_configured_https_companion_origin(
    seeded_db: tuple[Path, Path, int], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Host/forwarded headers must never supply a pairing command origin."""
    from audit.protected.egress import ProtectedEgressPolicy as RealPolicy
    from audit.web import protected_api, server

    db_path, blob_dir, _ = seeded_db
    settings = Settings(
        db_path=db_path,
        blob_dir=blob_dir,
        protected_scans_enabled=True,
        protected_proxy_hmac_secret=_IDENTITY_SECRET,
    )

    class TestProtectedEgressPolicy(RealPolicy):
        def __init__(self, allowed_origins: Iterable[str]) -> None:
            super().__init__(allowed_origins, resolver=_public_resolver)

    monkeypatch.setattr(server, "get_settings", lambda: settings)
    monkeypatch.setattr(protected_api, "ProtectedEgressPolicy", TestProtectedEgressPolicy)
    vault = ProtectedVault(DeterministicLocalKms(b"missing-public-origin-test-kms"))
    app = server.create_app(db_path=db_path, blob_dir=blob_dir, protected_vault=vault)
    with TestClient(app) as client:
        response = client.post(
            "/api/protected-scans",
            headers={
                **_identity_headers(settings, method="POST", path="/api/protected-scans"),
                "host": "attacker.example",
            },
            json=_request_payload(),
        )

    assert response.status_code == 503
    assert "public https companion origin" in response.json()["detail"].lower()


def test_protected_reports_are_hidden_from_public_legacy_routes_and_exports(
    protected_client: tuple[TestClient, Settings, Path, int],
) -> None:
    """Legacy routes cannot become a token-only export or comparison bypass."""
    client, settings, _, public_scan_id = protected_client
    protected_scan_id = _create_protected_draft(client, settings)

    public_list = client.get("/api/scans")
    assert public_list.status_code == 200
    assert protected_scan_id not in {row["id"] for row in public_list.json()}

    detail_path = f"/api/scans/{protected_scan_id}"
    denied_detail = client.get(detail_path)
    assert denied_detail.status_code == 403

    # A valid proxy identity can inspect the protection summary, but ordinary
    # public-report export and comparison contracts still must fail closed.
    allowed_detail = client.get(
        detail_path,
        headers=_identity_headers(settings, method="GET", path=detail_path),
    )
    assert allowed_detail.status_code == 200
    assert allowed_detail.json()["protection"]["mode"] == "protected"

    export_path = f"/api/scans/{protected_scan_id}/export/markdown"
    export = client.get(
        export_path,
        headers=_identity_headers(settings, method="GET", path=export_path),
    )
    assert export.status_code == 403

    diff_path = f"/api/scans/{protected_scan_id}/diff"
    diff = client.get(
        diff_path,
        params={"compare_to": public_scan_id},
        headers=_identity_headers(settings, method="GET", path=diff_path),
    )
    assert diff.status_code == 403


def test_noncanonical_legacy_ids_cannot_bypass_protected_read_or_write_guards(
    protected_client: tuple[TestClient, Settings, Path, int],
) -> None:
    """Reject every permissive integer spelling before a legacy route runs."""

    from audit.web import server

    client, settings, db_path, _ = protected_client
    scan_id = _create_protected_draft(client, settings)
    conn = sqlite3.connect(str(db_path))
    try:
        # An interrupted record is otherwise eligible for generic DELETE, so
        # this proves a signed path cannot reach a destructive handler.
        conn.execute("UPDATE scans SET status = 'completed' WHERE id = ?", (scan_id,))
        conn.execute(
            "UPDATE protected_scans SET protection_status = 'interrupted' WHERE scan_id = ?",
            (scan_id,),
        )
        page = conn.execute(
            """
            INSERT INTO pages (scan_id, url_normalized, status_code, title, render_mode, html_hash)
            VALUES (?, ?, 200, 'Protected page', 'js', 'canonical-id-test')
            """,
            (scan_id, f"protected://report/{scan_id}/page"),
        )
        page_id = int(page.lastrowid or 0)
        finding = conn.execute(
            """
            INSERT INTO page_a11y_findings (
                page_id, scan_id, rule_id, wcag_sc, wcag_scs, wcag_level,
                impact, help, help_url, target_selector, failure_summary,
                html_snippet, target_hash, pipeline, engine_outcome
            ) VALUES (?, ?, 'image-alt', '1.1.1', '1.1.1', 'A',
                      'serious', 'Missing alternative', '', '',
                      'Missing alternative', '', 'canonical-id-test', 'axe', 'failed')
            """,
            (page_id, scan_id),
        )
        finding_id = int(finding.lastrowid or 0)
        conn.commit()
    finally:
        conn.close()

    # ``:int`` converters and the earlier middleware must agree on a single
    # decimal spelling. The percent-encoded paths are decoded by Starlette
    # before middleware/route matching, which is why they are explicit here.
    malformed_scan_paths = (
        f"/api/scans/+{scan_id}",
        f"/api/scans/%2B{scan_id}",
        # Percent decoding occurs once at the ASGI boundary. A double-encoded
        # plus remains non-canonical rather than becoming a second route form.
        f"/api/scans/%252B{scan_id}",
        f"/api/scans/-{scan_id}",
        f"/api/scans/0{scan_id}",
        f"/api/scans/%20{scan_id}",
        f"/api/scans/{scan_id}%20",
        f"/api/scans/{scan_id}_0",
        f"/api/scans/{scan_id}.0",
        f"/api/scans/+{scan_id}/",
    )
    for path in malformed_scan_paths:
        response = client.get(path, follow_redirects=False)
        assert response.status_code == 404, (path, response.text)
        assert response.headers["cache-control"] == "no-store, private, max-age=0"
        assert "location" not in response.headers

    # httpx/TestClient normalizes percent-encoded C0 whitespace away before
    # it builds an ASGI scope, so exercise the decoded ASGI values directly.
    # Uvicorn/Starlette delivers those values to the same middleware helper.
    assert server._has_noncanonical_legacy_identifier(f"/api/scans/\t{scan_id}")
    assert server._has_noncanonical_legacy_identifier(f"/api/scans/{scan_id}\n")

    # A valid-looking sign must not turn generic read/status/delete routes
    # into unguarded protected-report access or mutation.
    for path in (
        f"/api/a11y-findings/+{finding_id}/status",
        f"/api/a11y-findings/%2B{finding_id}/status",
        f"/api/a11y-findings/0{finding_id}/status",
    ):
        response = client.post(path, json={"status": "remediated"}, follow_redirects=False)
        assert response.status_code == 404, (path, response.text)
        assert response.headers["cache-control"] == "no-store, private, max-age=0"

    delete = client.delete(f"/api/scans/+{scan_id}", follow_redirects=False)
    assert delete.status_code == 404
    conn = sqlite3.connect(str(db_path))
    try:
        assert conn.execute("SELECT 1 FROM scans WHERE id = ?", (scan_id,)).fetchone() is not None
        status = conn.execute(
            "SELECT status FROM page_a11y_findings WHERE id = ?", (finding_id,)
        ).fetchone()
        assert status == ("new",)
    finally:
        conn.close()

    # The canonical form is still classified as protected and requires a
    # proxy identity rather than being hidden by the malformed-path guard.
    canonical = client.get(f"/api/scans/{scan_id}")
    assert canonical.status_code == 403
    assert canonical.json()["detail"] == "Verified protected-scan identity required."


def test_redacted_protected_export_is_explicit_bounded_and_never_uses_raw_evidence(
    protected_client: tuple[TestClient, Settings, Path, int],
) -> None:
    """Only the protected route can hand off a completed report summary.

    Seed deliberately unsafe evidence fields directly to prove the redacted
    renderer never reads them, even if a database is contaminated outside the
    companion's normal minimal-index contract.
    """

    client, settings, db_path, _ = protected_client
    scan_id = _create_protected_draft(client, settings)
    raw_url = "https://app.example.test/secure/patient?token=super-secret"
    raw_selector = "#patient-8675309 [data-token='super-secret']"
    raw_html = "<input value='super-secret-medical-detail'>"
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("UPDATE scans SET status = 'completed' WHERE id = ?", (scan_id,))
        conn.execute(
            "UPDATE protected_scans SET protection_status = 'completed' WHERE scan_id = ?",
            (scan_id,),
        )
        page = conn.execute(
            """
            INSERT INTO pages (scan_id, url_normalized, status_code, title, render_mode, html_hash)
            VALUES (?, ?, 200, 'Patient record super-secret', 'js', 'a')
            """,
            (scan_id, raw_url),
        )
        page_id = int(page.lastrowid or 0)
        conn.execute(
            """
            INSERT INTO page_a11y_findings (
                page_id, scan_id, rule_id, wcag_sc, wcag_scs, wcag_level,
                impact, help, help_url, target_selector, failure_summary,
                html_snippet, target_hash, pipeline, engine_outcome
            ) VALUES (?, ?, 'image-alt', '1.1.1', '1.1.1', 'A',
                      'critical', 'super-secret help', 'https://secret.example.test', ?,
                      'super-secret failure', ?, 'aabbccddeeff00112233445566778899',
                      'axe', 'failed')
            """,
            (page_id, scan_id, raw_selector, raw_html),
        )
        conn.commit()
    finally:
        conn.close()

    path = f"/api/protected-scans/{scan_id}/exports/redacted"
    denied = client.post(path)
    assert denied.status_code == 403

    exported = client.post(
        path,
        headers=_identity_headers(settings, method="POST", path=path),
    )
    assert exported.status_code == 200, exported.text
    assert exported.headers["content-type"].startswith("text/markdown")
    assert f"protected_scan_{scan_id}_redacted.md" in exported.headers["content-disposition"]
    assert exported.headers["cache-control"] == "no-store, private, max-age=0"
    assert exported.headers["x-content-type-options"] == "nosniff"
    assert "image-alt" in exported.text
    assert "axe-core" in exported.text
    for prohibited in (raw_url, raw_selector, raw_html, "super-secret", "Patient record"):
        assert prohibited not in exported.text

    conn = sqlite3.connect(str(db_path))
    try:
        events = conn.execute(
            "SELECT event_type, details_json FROM protected_audit_events "
            "WHERE scan_id = ? ORDER BY id DESC LIMIT 1",
            (scan_id,),
        ).fetchone()
        artifacts = conn.execute(
            "SELECT COUNT(*) FROM protected_artifacts WHERE scan_id = ?", (scan_id,)
        ).fetchone()
    finally:
        conn.close()
    assert events is not None
    assert events[0] == "protected_export.redacted_downloaded"
    assert "super-secret" not in str(events[1])
    assert artifacts is not None and int(artifacts[0]) == 0


def test_redacted_protected_export_requires_completed_unpurged_report(
    protected_client: tuple[TestClient, Settings, Path, int],
) -> None:
    client, settings, db_path, _ = protected_client
    scan_id = _create_protected_draft(client, settings)
    path = f"/api/protected-scans/{scan_id}/exports/redacted"

    not_complete = client.post(
        path,
        headers=_identity_headers(settings, method="POST", path=path),
    )
    assert not_complete.status_code == 409

    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            """
                UPDATE protected_scans
                   SET protection_status = 'completed', wrapped_data_key = NULL,
                       work_spec_nonce = NULL, work_spec_ciphertext = NULL, seed_locator = NULL,
                       evidence_purged_at = CURRENT_TIMESTAMP, key_destroyed_at = CURRENT_TIMESTAMP
                 WHERE scan_id = ?
            """,
            (scan_id,),
        )
        conn.commit()
    finally:
        conn.close()
    purged = client.post(
        path,
        headers=_identity_headers(settings, method="POST", path=path),
    )
    assert purged.status_code == 410


def test_companion_cannot_reopen_terminal_work_or_create_protected_exports(
    protected_client: tuple[TestClient, Settings, Path, int],
) -> None:
    """A paired agent gets one paused-work scope, never an export backdoor."""

    client, settings, db_path, _ = protected_client
    scan_id = _create_protected_draft(client, settings)
    enrollment = _create_enrollment(client, settings, scan_id, certificate_fingerprint="d" * 64)
    enrollment_id = str(enrollment["enrollment_id"])
    fingerprint = "d" * 64
    claim_body = {
        "enrollment_id": enrollment_id,
        "pairing_code": str(enrollment["pairing_code"]),
    }
    agent_headers = _agent_mtls_headers(
        settings,
        method="POST",
        path="/api/agents/enroll",
        fingerprint=fingerprint,
        body=claim_body,
    )
    claim = client.post(
        "/api/agents/enroll",
        headers=agent_headers,
        json=claim_body,
    )
    assert claim.status_code == 201, claim.text

    # An authenticated companion cannot skip the actual crawl and mark a
    # draft completed. The repository state graph rejects this transition.
    events_path = f"/api/agents/{enrollment_id}/events"
    premature_completion = client.post(
        events_path,
        headers=_agent_mtls_headers(
            settings,
            method="POST",
            path=events_path,
            fingerprint=fingerprint,
            body={
                "event_type": "companion.completed",
                "run_lease_id": "a" * 24,
                "status": "completed",
            },
        ),
        json={
            "event_type": "companion.completed",
            "run_lease_id": "a" * 24,
            "status": "completed",
        },
    )
    assert premature_completion.status_code == 409

    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "UPDATE protected_scans SET protection_status = 'completed' WHERE scan_id = ?",
            (scan_id,),
        )
        conn.commit()
    finally:
        conn.close()

    work_path = f"/api/agents/{enrollment_id}/work"
    work = client.get(
        work_path,
        headers=_agent_mtls_headers(
            settings,
            method="GET",
            path=work_path,
            fingerprint=fingerprint,
        ),
    )
    assert work.status_code == 409
    assert "secure" not in work.text

    artifact = client.post(
        f"/api/agents/{enrollment_id}/artifacts",
        headers=_agent_mtls_headers(
            settings,
            method="POST",
            path=f"/api/agents/{enrollment_id}/artifacts",
            fingerprint=fingerprint,
            body={
                "artifact_type": "protected_export",
                "content_type": "text/markdown",
                "reviewed_and_redacted": True,
                "content_base64": "cmVkYWN0ZWQ=",
            },
        ),
        json={
            "artifact_type": "protected_export",
            "content_type": "text/markdown",
            "reviewed_and_redacted": True,
            "content_base64": "cmVkYWN0ZWQ=",
        },
    )
    assert artifact.status_code == 403

    handoff_path = f"/api/protected-scans/{scan_id}/companion-start"
    handoff = client.post(
        handoff_path,
        headers=_identity_headers(settings, method="POST", path=handoff_path),
    )
    assert handoff.status_code == 409


def test_protected_manual_checks_are_identity_guarded_and_outcome_only(
    protected_client: tuple[TestClient, Settings, Path, int],
) -> None:
    """Protected review records a WCAG result, never free-text evidence.

    In particular, a post-MFA crawl must not become an implicit result for
    WCAG 2.2 SC 3.3.8. The outcome-only endpoint stays separate from the
    legacy public-report evaluation routes, which contain plaintext notes.
    """

    client, settings, db_path, _ = protected_client
    scan_id = _create_protected_draft(client, settings)
    checks_path = f"/api/protected-scans/{scan_id}/manual-checks"

    assert client.get(checks_path).status_code == 403
    listed = client.get(
        checks_path,
        headers=_identity_headers(settings, method="GET", path=checks_path),
    )
    assert listed.status_code == 200, listed.text
    body = listed.json()
    assert body["scan_id"] == scan_id
    authentication = next(check for check in body["checks"] if check["criterion"]["sc"] == "3.3.8")
    assert authentication["criterion"]["name"] == "Accessible Authentication (Minimum)"
    assert "Manually test" in authentication["criterion"]["manual_check"]
    assert "temporary browser session" in authentication["criterion"]["manual_check"]
    assert authentication["outcome"] == "not_started"
    for check in body["checks"]:
        assert set(check) == {"criterion", "outcome", "tested_at", "updated_at"}
        assert set(check["criterion"]) == {"sc", "name", "level", "method", "manual_check"}

    criterion_path = f"{checks_path}/3.3.8"
    rejected_note = client.patch(
        criterion_path,
        headers=_identity_headers(settings, method="PATCH", path=criterion_path),
        json={"outcome": "pass", "rationale": "OTP was 123456"},
    )
    assert rejected_note.status_code == 422

    saved = client.patch(
        criterion_path,
        headers=_identity_headers(settings, method="PATCH", path=criterion_path),
        json={"outcome": "needs_follow_up"},
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["outcome"] == "needs_follow_up"
    assert set(saved.json()) == {"criterion", "outcome", "tested_at", "updated_at"}

    # The generic free-text endpoints cannot be used as a protected-data
    # bypass, even with an otherwise valid protected-report proxy identity.
    legacy_list = f"/api/scans/{scan_id}/manual-checks"
    assert (
        client.get(
            legacy_list,
            headers=_identity_headers(settings, method="GET", path=legacy_list),
        ).status_code
        == 403
    )
    legacy_update = client.patch(
        f"{legacy_list}/3.3.8",
        headers=_identity_headers(
            settings,
            method="PATCH",
            path=f"{legacy_list}/3.3.8",
        ),
        json={"outcome": "fail", "rationale": "do not persist me"},
    )
    assert legacy_update.status_code == 403

    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute(
            """
            SELECT r.outcome, r.rationale
              FROM manual_check_results r
              JOIN evaluation_reports e ON e.id = r.evaluation_report_id
             WHERE e.scan_id = ? AND r.criterion_sc = '3.3.8'
            """,
            (scan_id,),
        ).fetchone()
        evidence_count = conn.execute(
            """
            SELECT COUNT(*)
              FROM manual_check_evidence me
              JOIN manual_check_results r ON r.id = me.manual_check_result_id
              JOIN evaluation_reports e ON e.id = r.evaluation_report_id
             WHERE e.scan_id = ?
            """,
            (scan_id,),
        ).fetchone()
        event = conn.execute(
            """
            SELECT event_type, details_json
              FROM protected_audit_events
             WHERE scan_id = ? AND event_type = 'protected_manual_check.updated'
             ORDER BY id DESC LIMIT 1
            """,
            (scan_id,),
        ).fetchone()
    finally:
        conn.close()
    assert row == ("needs_follow_up", "")
    assert evidence_count == (0,)
    assert event is not None
    assert event[0] == "protected_manual_check.updated"
    assert "3.3.8" in str(event[1])
    assert "needs_follow_up" in str(event[1])
    assert "123456" not in str(event[1])


def test_protected_validation_errors_never_reflect_scope_or_pairing_secrets(
    protected_client: tuple[TestClient, Settings, Path, int],
) -> None:
    """Framework 422 payloads must not become a protected-data side channel."""

    client, settings, _, _ = protected_client
    private_seed = "https://app.example.test/secure?token=validation-secret"
    draft = client.post(
        "/api/protected-scans",
        headers=_identity_headers(settings, method="POST", path="/api/protected-scans"),
        json=_request_payload(seed_url=private_seed),
    )
    assert draft.status_code == 422
    assert draft.json() == {"detail": "Invalid protected request."}
    assert private_seed not in draft.text
    assert "validation-secret" not in draft.text
    assert draft.headers["cache-control"] == "no-store, private, max-age=0"

    invalid_pairing_value = "OTP-123456"
    enrollment = client.post(
        "/api/agents/enroll",
        json={
            "enrollment_id": "12345678",
            "pairing_code": invalid_pairing_value,
            "certificate_fingerprint": "a" * 64,
        },
    )
    assert enrollment.status_code == 422
    assert enrollment.json() == {"detail": "Invalid protected request."}
    assert invalid_pairing_value not in enrollment.text

    # Legacy route validation runs before its handler can deny the public
    # manual-evidence workflow. The sanitizer must still recognize that this
    # scan ID belongs to a protected report.
    scan_id = _create_protected_draft(client, settings)
    legacy_path = f"/api/scans/{scan_id}/manual-checks/3.3.8"
    legacy_value = "legacy-validation-secret-" + ("x" * 12_000)
    legacy = client.patch(
        legacy_path,
        headers=_identity_headers(settings, method="PATCH", path=legacy_path),
        json={"outcome": "pass", "rationale": legacy_value},
    )
    assert legacy.status_code == 422
    assert legacy.json() == {"detail": "Invalid protected request."}
    assert "legacy-validation-secret" not in legacy.text


def test_protected_body_limit_runs_before_fastapi_body_parsing(
    protected_client: tuple[TestClient, Settings, Path, int],
) -> None:
    """A known oversized agent payload is rejected before auth or JSON parsing."""

    client, _, _, _ = protected_client
    response = client.post("/api/agents/enroll", content=b"x" * 1_000_001)
    assert response.status_code == 413
    assert response.json() == {"detail": "Protected request body is too large."}
    assert response.headers["cache-control"] == "no-store, private, max-age=0"


def test_protected_body_limit_counts_chunked_input_before_the_framework(
    tmp_path: Path,
) -> None:
    """The ASGI guard also catches a chunked body with no Content-Length."""

    from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
    from starlette.requests import Request
    from starlette.responses import Response
    from starlette.types import Message, Receive, Scope, Send

    from audit.web.server import _ProtectedRequestBodyLimitMiddleware

    async def exercise() -> tuple[list[Message], int]:
        messages = iter(
            (
                {"type": "http.request", "body": b"x" * 600, "more_body": True},
                {"type": "http.request", "body": b"y" * 600, "more_body": False},
            )
        )
        sent: list[Message] = []
        chunks_seen = 0

        async def receive() -> Message:
            return next(messages)

        async def send(message: Message) -> None:
            sent.append(message)

        async def downstream(scope: Scope, receive_fn: Receive, send_fn: Send) -> None:
            nonlocal chunks_seen
            _ = scope, send_fn
            await receive_fn()
            chunks_seen += 1
            await receive_fn()
            chunks_seen += 1

        async def passthrough(request: Request, call_next: RequestResponseEndpoint) -> Response:
            return await call_next(request)

        # The production app has several decorator-based
        # ``BaseHTTPMiddleware`` layers inside this guard. Keep one here so
        # the test exercises exception propagation across that boundary, not
        # merely the guard in isolation.
        middleware = _ProtectedRequestBodyLimitMiddleware(
            BaseHTTPMiddleware(downstream, dispatch=passthrough),
            db_path=tmp_path / "unused.db",
            max_body_bytes=1024,
        )
        await middleware(
            {
                "type": "http",
                "path": "/api/agents/enroll",
                "method": "POST",
                "headers": [],
            },
            receive,
            send,
        )
        return sent, chunks_seen

    sent, chunks_seen = asyncio.run(exercise())
    assert chunks_seen == 1
    assert sent[0]["type"] == "http.response.start"
    assert sent[0]["status"] == 413
    response_body = b"".join(
        bytes(message.get("body", b""))
        for message in sent
        if message["type"] == "http.response.body"
    )
    assert b"Protected request body is too large." in response_body
    assert b"x" * 20 not in response_body
