"""AES-GCM envelope encryption for protected evidence.

The KMS protocol is deliberately small: production can adapt an approved U-M
KMS without changing repository code, while tests use an in-memory local
adapter.  Neither implementation writes a data-encryption key to disk.
"""

from __future__ import annotations

import hashlib
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_KEY_BYTES = 32
_NONCE_BYTES = 12
_WRAP_AAD_PREFIX = b"axcess-protected-kms-wrap:v1\x00"
_ARTIFACT_AAD_PREFIX = b"axcess-protected-artifact:v1\x00"
_WORK_SPEC_AAD_PREFIX = b"axcess-protected-work-spec:v1\x00"


class ProtectedDataIntegrityError(ValueError):
    """Raised when encrypted data or its authenticated context was altered."""


class KeyWrappingKms(Protocol):
    """Production KMS seam for protected per-scan evidence keys.

    A production adapter must make ``destroy_scan_key`` irreversible for the
    supplied scan context (for example by destroying a per-scan KMS key or
    revoking a dedicated grant). Deleting an encrypted DEK from SQLite alone
    does not protect a prior database/WAL/backup snapshot encrypted by a
    long-lived shared KEK.
    """

    @property
    def key_id(self) -> str:
        """Return the non-secret identifier of the key-encryption key."""

    def wrap_key(self, data_key: bytes, *, context: bytes) -> bytes:
        """Encrypt one data-encryption key using authenticated context."""

    def unwrap_key(self, wrapped_data_key: bytes, *, context: bytes) -> bytes:
        """Return one data-encryption key or raise on tampering/context mismatch."""

    def destroy_scan_key(self, *, context: bytes) -> None:
        """Irreversibly revoke/deactivate material for one scan context.

        Implementations must be idempotent: retention cleanup can retry after
        a database interruption without making an already-destroyed key an
        operational error.
        """

    @property
    def supports_irreversible_scan_key_destruction(self) -> bool:
        """Whether the adapter can revoke a scan's historical decrypt path.

        Production-labelled scans fail closed unless this is true. A normal
        shared KEK plus SQLite deletion is not sufficient for retention
        crypto-erasure because old database/WAL/backup snapshots could still
        contain a wrapped data key.
        """


@dataclass(frozen=True)
class EncryptedPayload:
    """A ciphertext and its AES-GCM nonce; both are safe to persist together."""

    nonce: bytes
    ciphertext: bytes


class DeterministicLocalKms:
    """In-memory development KMS adapter using real AES-256-GCM.

    ``seed`` deterministically derives the local wrapping key so fixtures can
    reproduce it without an environment variable, file, or cloud call.  AES-
    GCM nonces remain random by default.  A deterministic nonce source exists
    only to make unit tests repeatable and must not be supplied in deployment.
    """

    def __init__(
        self,
        seed: bytes,
        *,
        key_id: str = "local-dev-memory",
        nonce_source: Callable[[int], bytes] | None = None,
    ) -> None:
        if not seed:
            raise ValueError("local development KMS seed must not be empty")
        self._key = hashlib.sha256(b"axcess-local-kms-v1\x00" + seed).digest()
        self._key_id = key_id
        self._nonce_source = nonce_source or secrets.token_bytes

    @property
    def key_id(self) -> str:
        return self._key_id

    @property
    def supports_irreversible_scan_key_destruction(self) -> bool:
        """Local test/dev wrapping cannot revoke a historical shared KEK."""

        return False

    def wrap_key(self, data_key: bytes, *, context: bytes) -> bytes:
        _require_aes256_key(data_key, message="data-encryption key")
        nonce = _nonce(self._nonce_source)
        ciphertext = AESGCM(self._key).encrypt(nonce, data_key, _WRAP_AAD_PREFIX + context)
        return nonce + ciphertext

    def unwrap_key(self, wrapped_data_key: bytes, *, context: bytes) -> bytes:
        if len(wrapped_data_key) <= _NONCE_BYTES:
            raise ProtectedDataIntegrityError("wrapped protected data key is invalid")
        nonce = wrapped_data_key[:_NONCE_BYTES]
        ciphertext = wrapped_data_key[_NONCE_BYTES:]
        try:
            data_key = AESGCM(self._key).decrypt(nonce, ciphertext, _WRAP_AAD_PREFIX + context)
        except InvalidTag as exc:
            raise ProtectedDataIntegrityError(
                "wrapped protected data key could not be verified"
            ) from exc
        _require_aes256_key(data_key, message="unwrapped data-encryption key")
        return data_key

    def destroy_scan_key(self, *, context: bytes) -> None:
        """Development-only no-op; SQLite removal is not backup crypto-erasure.

        This adapter cannot revoke a derived, process-memory KEK per scan. It
        is available only through the explicit local-development setting;
        production protected scans must inject a KMS adapter that implements
        context-scoped key/grant destruction.
        """

        _ = context


class ProtectedVault:
    """Envelope encryption facade for a single protected-scan vault.

    A random AES-256 data key is generated per scan, wrapped by the supplied
    KMS, and never returned in a response model. Retention invokes the KMS's
    explicit context-scoped destruction hook before deleting the wrapped
    record, so a production implementation can make prior database backups
    unreadable.
    """

    def __init__(
        self,
        kms: KeyWrappingKms,
        *,
        nonce_source: Callable[[int], bytes] | None = None,
    ) -> None:
        self._kms = kms
        self._nonce_source = nonce_source or secrets.token_bytes

    @property
    def kms_key_id(self) -> str:
        return self._kms.key_id

    @property
    def supports_irreversible_scan_key_destruction(self) -> bool:
        """Expose the KMS retention capability without leaking key material."""

        return bool(getattr(self._kms, "supports_irreversible_scan_key_destruction", False))

    def create_wrapped_scan_key(self, scan_id: int) -> bytes:
        """Generate and wrap a fresh AES-256 data key for ``scan_id``."""

        _validate_scan_id(scan_id)
        data_key = secrets.token_bytes(_KEY_BYTES)
        return self._kms.wrap_key(data_key, context=_scan_key_context(scan_id))

    def encrypt(
        self,
        *,
        scan_id: int,
        artifact_id: str,
        data: bytes,
        wrapped_data_key: bytes,
    ) -> EncryptedPayload:
        """Encrypt one artifact using the scan's unwrapped in-memory data key."""

        data_key = self._unwrap_scan_key(scan_id, wrapped_data_key)
        nonce = _nonce(self._nonce_source)
        ciphertext = AESGCM(data_key).encrypt(nonce, data, _artifact_context(scan_id, artifact_id))
        return EncryptedPayload(nonce=nonce, ciphertext=ciphertext)

    def decrypt(
        self,
        *,
        scan_id: int,
        artifact_id: str,
        nonce: bytes,
        ciphertext: bytes,
        wrapped_data_key: bytes,
    ) -> bytes:
        """Decrypt and authenticate one artifact while it is needed in memory."""

        if len(nonce) != _NONCE_BYTES:
            raise ProtectedDataIntegrityError("protected artifact nonce is invalid")
        data_key = self._unwrap_scan_key(scan_id, wrapped_data_key)
        try:
            return AESGCM(data_key).decrypt(
                nonce, ciphertext, _artifact_context(scan_id, artifact_id)
            )
        except InvalidTag as exc:
            raise ProtectedDataIntegrityError("protected artifact could not be verified") from exc

    def encrypt_work_spec(
        self,
        *,
        scan_id: int,
        data: bytes,
        wrapped_data_key: bytes,
    ) -> EncryptedPayload:
        """Encrypt the one scan-bound companion work specification.

        This is deliberately separate from ``encrypt``: a work specification
        is not reviewer evidence and must not share an artifact identifier or
        authenticated-data namespace with a retained artifact.
        """

        data_key = self._unwrap_scan_key(scan_id, wrapped_data_key)
        nonce = _nonce(self._nonce_source)
        ciphertext = AESGCM(data_key).encrypt(nonce, data, _work_spec_context(scan_id))
        return EncryptedPayload(nonce=nonce, ciphertext=ciphertext)

    def decrypt_work_spec(
        self,
        *,
        scan_id: int,
        nonce: bytes,
        ciphertext: bytes,
        wrapped_data_key: bytes,
    ) -> bytes:
        """Decrypt a transient companion work specification in memory."""

        if len(nonce) != _NONCE_BYTES:
            raise ProtectedDataIntegrityError("protected work-spec nonce is invalid")
        data_key = self._unwrap_scan_key(scan_id, wrapped_data_key)
        try:
            return AESGCM(data_key).decrypt(nonce, ciphertext, _work_spec_context(scan_id))
        except InvalidTag as exc:
            raise ProtectedDataIntegrityError(
                "protected work specification could not be verified"
            ) from exc

    def destroy_scan_key(self, scan_id: int) -> None:
        """Ask the configured KMS to revoke one scan's encryption path."""

        _validate_scan_id(scan_id)
        self._kms.destroy_scan_key(context=_scan_key_context(scan_id))

    def _unwrap_scan_key(self, scan_id: int, wrapped_data_key: bytes) -> bytes:
        _validate_scan_id(scan_id)
        return self._kms.unwrap_key(wrapped_data_key, context=_scan_key_context(scan_id))


def _scan_key_context(scan_id: int) -> bytes:
    _validate_scan_id(scan_id)
    return f"scan:{scan_id}".encode("ascii")


def _artifact_context(scan_id: int, artifact_id: str) -> bytes:
    _validate_scan_id(scan_id)
    if not artifact_id:
        raise ValueError("protected artifact id must not be empty")
    return _ARTIFACT_AAD_PREFIX + f"scan:{scan_id}:artifact:{artifact_id}".encode()


def _work_spec_context(scan_id: int) -> bytes:
    _validate_scan_id(scan_id)
    return _WORK_SPEC_AAD_PREFIX + f"scan:{scan_id}".encode("ascii")


def _validate_scan_id(scan_id: int) -> None:
    if scan_id <= 0:
        raise ValueError("protected scan id must be positive")


def _require_aes256_key(key: bytes, *, message: str) -> None:
    if len(key) != _KEY_BYTES:
        raise ProtectedDataIntegrityError(f"{message} must be AES-256 length")


def _nonce(source: Callable[[int], bytes]) -> bytes:
    nonce = source(_NONCE_BYTES)
    if len(nonce) != _NONCE_BYTES:
        raise ValueError("AES-GCM nonce source returned an invalid length")
    return nonce
