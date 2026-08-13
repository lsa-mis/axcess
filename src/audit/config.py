"""Runtime configuration. Env vars (prefixed AUDIT_) or .env file."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Global configuration resolved from env + defaults."""

    model_config = SettingsConfigDict(
        env_prefix="AUDIT_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    data_dir: Path = Field(default=Path("data"))
    db_path: Path = Field(default=Path("data/audit.db"))
    blob_dir: Path = Field(default=Path("data/blobs"))
    log_dir: Path = Field(default=Path("data/logs"))

    # Crawler
    default_rps: float = 2.0
    request_timeout_s: float = 30.0
    user_agent: str = "axcess/0.1 (+local accessibility audit)"

    # OCR (Phase 3)
    ocr_language: str = "eng"
    ocr_max_workers: int = 2
    ocr_min_confidence: float = 60.0
    ocr_min_word_count: int = 3

    # VLM (Phase 4)
    ollama_base_url: str = "http://localhost:11434"
    vlm_model: str = "qwen3-vl:2b-instruct"
    vlm_concurrency: int = 1
    vlm_prompt_name: str = "classify_v1.txt"

    # Hosting / access control. Empty by default → the tool stays a
    # zero-auth local app (binds to 127.0.0.1, no token needed). Set
    # ``AUDIT_ACCESS_TOKEN`` before binding to a LAN/Tailscale address
    # so the instance isn't wide open the moment it's reachable beyond
    # localhost. The middleware that enforces this is a no-op when the
    # token is empty, so local dev + the test suite are unaffected.
    access_token: str = ""

    # Protected (manually authenticated) scans deliberately sit behind a
    # stronger boundary than the optional shared LAN token above.  They are
    # disabled unless an identity-aware proxy is explicitly configured.  The
    # proxy signs the short-lived identity headers that the application
    # verifies; this avoids treating a forwarded header as proof of identity.
    protected_scans_enabled: bool = False
    protected_identity_header: str = "x-axcess-identity"
    protected_groups_header: str = "x-axcess-groups"
    protected_timestamp_header: str = "x-axcess-timestamp"
    # A proxy-issued, high-entropy assertion identifier.  It is covered by
    # the identity HMAC and gives state-changing browser requests a real
    # replay key; a second-resolution timestamp alone is not unique enough.
    protected_identity_nonce_header: str = "x-axcess-identity-nonce"
    protected_signature_header: str = "x-axcess-signature"
    protected_proxy_hmac_secret: SecretStr = SecretStr("")
    protected_required_group: str = "axcess-protected-scan"
    protected_identity_max_age_s: int = Field(default=60, ge=10, le=300)
    protected_identity_replay_max_entries: int = Field(default=10_000, ge=100, le=100_000)
    # Exact public HTTPS origin used in companion commands. It is separate
    # from a request Host header so a proxy/client cannot make Axcess issue a
    # command which connects to an attacker-controlled or plaintext origin.
    protected_public_origin: str = ""
    # Companion endpoints sit behind a different reverse-proxy boundary than
    # browser identity assertions.  mTLS verification/fingerprint headers are
    # only meaningful when the proxy signs them with this separate secret;
    # otherwise a client that can reach the application listener could forge
    # both headers.  Keep this credential distinct from the human identity
    # proxy secret so either integration can be rotated independently.
    protected_agent_cert_header: str = "x-ssl-client-fingerprint"
    protected_agent_verify_header: str = "x-ssl-client-verify"
    protected_agent_proxy_timestamp_header: str = "x-axcess-agent-timestamp"
    protected_agent_proxy_nonce_header: str = "x-axcess-agent-nonce"
    protected_agent_proxy_body_sha256_header: str = "x-axcess-agent-body-sha256"
    protected_agent_proxy_signature_header: str = "x-axcess-agent-signature"
    protected_agent_proxy_hmac_secret: SecretStr = SecretStr("")
    protected_agent_proxy_max_age_s: int = Field(default=60, ge=10, le=300)
    protected_agent_proxy_replay_max_entries: int = Field(default=10_000, ge=100, le=100_000)
    # FastAPI otherwise parses a JSON body before a protected endpoint can
    # authenticate it.  Keep the pre-auth attack surface deliberately small;
    # the server applies this cap while streaming both known-length and
    # chunked protected requests, before Pydantic/JSON decoding.
    protected_request_body_max_bytes: int = Field(default=1_000_000, ge=1024, le=10_000_000)
    protected_kms_key_id: str = "axcess-protected-evidence"
    # Deployment-owned factory in ``package.module:callable`` form. It is
    # loaded only inside the trusted Axcess process and must return a
    # ``ProtectedVault`` around the U-M-approved, per-scan-revocable KMS
    # adapter. The value is a module reference, never a credential; provider
    # authentication belongs to its approved workload/secret-manager channel.
    protected_kms_vault_factory: str = ""
    # Local KMS is exclusively a development/test adapter.  A production
    # deployment supplies a KeyWrappingKms implementation to ``create_app``;
    # protected routes stay unavailable if neither is configured.
    protected_local_kms_seed: SecretStr = SecretStr("")
    protected_allow_local_kms: bool = False

    def ensure_dirs(self) -> None:
        """Create runtime directories if missing."""
        for p in (self.data_dir, self.blob_dir, self.log_dir):
            p.mkdir(parents=True, exist_ok=True)


def get_settings() -> Settings:
    """Build a fresh Settings instance (caller may cache)."""
    return Settings()
