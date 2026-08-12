"""Identity checks for protected authenticated scans.

The normal ``AUDIT_ACCESS_TOKEN`` is intentionally not accepted here: it is
an ingress gate, not evidence of a person, role, or target authorization.
Protected routes instead expect a short-lived identity assertion produced by
an identity-aware reverse proxy.  The proxy and Axcess share an HMAC secret;
clients cannot manufacture the signed headers.

This module does not implement a university IdP.  It is a deliberately small
adapter boundary for the proxy deployment documented in ``docs/hosting.md``.
"""

from __future__ import annotations

import hashlib
import hmac
import time
from dataclasses import dataclass
from urllib.parse import urlsplit

from fastapi import HTTPException, Request

from audit.config import Settings
from audit.protected.models import normalize_exact_https_origin


@dataclass(frozen=True, slots=True)
class ProtectedIdentity:
    """Verified actor identity supplied by the trusted proxy."""

    subject: str
    groups: frozenset[str]


def protected_identity_context_fingerprint(identity: ProtectedIdentity, settings: Settings) -> str:
    """Return an opaque, domain-separated stable browser identity handle.

    The React client needs a stable cache partition that changes when the
    identity-aware proxy changes users in an existing browser tab.  It must
    not receive the proxy subject itself (or a reversible encoding of it), so
    derive the handle with the deployment's proxy HMAC key and a purpose
    string distinct from request-assertion signing.

    Rotating the proxy HMAC key intentionally changes this value.  That
    clears protected browser caches, which is safer than carrying a cache
    partition across a trust-key rotation.
    """

    secret = settings.protected_proxy_hmac_secret.get_secret_value()
    if not secret:
        # ``require_protected_identity`` is always called before this helper.
        # Keep a defensive configuration failure here rather than accidentally
        # deriving a predictable handle if a future call site changes order.
        raise HTTPException(
            status_code=503,
            detail="Protected scans require an identity-aware proxy configuration.",
        )
    message = b"axcess/protected-browser-identity-context/v1\x00" + identity.subject.encode("utf-8")
    return hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()


_seen_signatures: dict[str, float] = {}
_seen_agent_assertions: dict[str, float] = {}


def require_protected_identity(request: Request, settings: Settings) -> ProtectedIdentity:
    """Return a verified protected-scan actor or raise a safe HTTP error.

    A disabled or incomplete configuration intentionally looks unavailable,
    rather than silently falling back to the shared access token.  The
    assertion is method/path-bound, nonce-bound, and short-lived.  A bounded
    in-process replay cache closes the practical replay window for this
    single-host application; the proxy's TLS/mTLS boundary remains the
    production trust boundary.
    """
    if not settings.protected_scans_enabled:
        raise HTTPException(status_code=404, detail="Protected scans are not enabled.")

    secret = settings.protected_proxy_hmac_secret.get_secret_value()
    if not secret:
        raise HTTPException(
            status_code=503,
            detail="Protected scans require an identity-aware proxy configuration.",
        )

    subject = request.headers.get(settings.protected_identity_header, "").strip()
    groups_raw = request.headers.get(settings.protected_groups_header, "")
    timestamp_raw = request.headers.get(settings.protected_timestamp_header, "").strip()
    nonce = request.headers.get(settings.protected_identity_nonce_header, "").strip()
    supplied = request.headers.get(settings.protected_signature_header, "").strip()
    groups = frozenset(g.strip() for g in groups_raw.split(",") if g.strip())
    if (
        not subject
        or len(subject) > 200
        or not timestamp_raw
        or not nonce
        or len(nonce) > 200
        or not supplied
    ):
        raise HTTPException(status_code=403, detail="Verified protected-scan identity required.")
    # A protected-scan deployment has no safe "any authenticated user"
    # mode.  The configured permission group is part of the authorization
    # contract; an empty value is a deployment error, not an invitation to
    # bypass group-based access control.
    if not settings.protected_required_group:
        raise HTTPException(
            status_code=503,
            detail="Protected scans require a configured permission group.",
        )
    if settings.protected_required_group not in groups:
        raise HTTPException(status_code=403, detail="Protected-scan permission required.")
    try:
        timestamp = int(timestamp_raw)
    except ValueError as exc:
        raise HTTPException(
            status_code=403, detail="Invalid protected identity assertion."
        ) from exc
    now = time.time()
    if abs(now - timestamp) > settings.protected_identity_max_age_s:
        raise HTTPException(status_code=403, detail="Protected identity assertion expired.")

    message = "\n".join(
        (
            request.method.upper(),
            request.url.path,
            timestamp_raw,
            nonce,
            subject,
            ",".join(sorted(groups)),
        )
    ).encode("utf-8")
    expected = hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(supplied, expected):
        raise HTTPException(status_code=403, detail="Invalid protected identity assertion.")

    # Read-only navigation may legitimately reuse a proxy assertion while the
    # SPA polls scan status.  State-changing browser requests are single-use.
    if request.method.upper() not in {"GET", "HEAD", "OPTIONS"}:
        _discard_expired_replays(now)
        replay_key = hashlib.sha256(message + supplied.encode("ascii", errors="ignore")).hexdigest()
        if replay_key in _seen_signatures:
            raise HTTPException(
                status_code=403, detail="Protected identity assertion was already used."
            )
        # The nonce comes from the trusted proxy.  Bound this cache anyway so
        # a misconfigured proxy cannot turn legitimate traffic into process
        # memory growth.  Evict the earliest-expiring assertion first.
        while len(_seen_signatures) >= settings.protected_identity_replay_max_entries:
            oldest = min(_seen_signatures, key=_seen_signatures.__getitem__)
            del _seen_signatures[oldest]
        _seen_signatures[replay_key] = now + settings.protected_identity_max_age_s
    return ProtectedIdentity(subject=subject, groups=groups)


def require_protected_report_owner(identity: ProtectedIdentity, *, authorized_by: str) -> None:
    """Require the report's owning protected-scan identity.

    A global proxy group only says that a person may use protected scans. It
    is not permission to read, export, or pair a companion for every report
    created by every other member. Axcess is single-expert software, so the
    durable creator identity is the intentionally narrow per-report ACL for
    this release. A future sharing model needs an explicit audited ACL table,
    not a relaxed group check.
    """

    if not authorized_by or not hmac.compare_digest(identity.subject, authorized_by):
        raise HTTPException(status_code=403, detail="Protected-report permission required.")


def require_same_origin(request: Request, settings: Settings) -> None:
    """Reject cross-origin browser mutations on protected routes.

    This function is used only by browser routes; companion traffic has its
    own mTLS-only endpoints. Require an Origin rather than accepting an
    absent one so a cross-site form/request cannot rely on a proxy-issued
    identity assertion without passing an explicit same-origin check.
    """
    origin = request.headers.get("origin", "").strip()
    if not origin:
        raise HTTPException(status_code=403, detail="Protected browser action requires Origin.")
    parts = urlsplit(origin)
    if not parts.scheme or not parts.netloc:
        raise HTTPException(status_code=403, detail="Invalid request origin.")
    try:
        supplied_origin = normalize_exact_https_origin(origin)
        expected = normalize_exact_https_origin(settings.protected_public_origin)
    except ValueError as exc:
        # Protected browser traffic must use the configured external TLS
        # origin.  Never infer this from Host or forwarded headers, which may
        # be client-controlled unless an upstream server is configured with a
        # separate trusted-proxy policy.
        raise HTTPException(
            status_code=503,
            detail="Protected scans require a configured HTTPS public origin.",
        ) from exc
    if not hmac.compare_digest(supplied_origin, expected):
        raise HTTPException(status_code=403, detail="Cross-origin protected action blocked.")


async def require_agent_mtls(
    request: Request,
    settings: Settings,
    *,
    expected_fingerprint: str,
) -> None:
    """Verify a signed mTLS assertion emitted by the trusted TLS proxy.

    Axcess itself is intentionally TLS-termination agnostic.  Production
    deployments configure the reverse proxy to require a client certificate,
    strip any client-supplied assertion headers, and add the verified
    fingerprint/status *plus* a short-lived HMAC assertion.  The HMAC is
    required because the two mTLS headers alone would otherwise be forgeable
    by a client that can accidentally reach the application listener.

    The fingerprint is additionally bound to one enrolled companion and scan
    in the database by the caller.  The signed assertion binds method, path,
    a proxy-issued single-use nonce, and the exact request-body SHA-256. That
    makes it unusable for a different endpoint, a changed event payload, or a
    second delivery during its short validity window.
    """
    secret = settings.protected_agent_proxy_hmac_secret.get_secret_value()
    if not secret:
        raise HTTPException(
            status_code=503,
            detail="Companion routes require a signed mTLS proxy configuration.",
        )

    verified = request.headers.get(settings.protected_agent_verify_header, "").strip().lower()
    fingerprint = request.headers.get(settings.protected_agent_cert_header, "").strip().lower()
    timestamp_raw = request.headers.get(settings.protected_agent_proxy_timestamp_header, "").strip()
    nonce = request.headers.get(settings.protected_agent_proxy_nonce_header, "").strip()
    body_digest = (
        request.headers.get(settings.protected_agent_proxy_body_sha256_header, "").strip().lower()
    )
    supplied = request.headers.get(settings.protected_agent_proxy_signature_header, "").strip()
    if verified not in {"success", "verified", "1", "true"}:
        raise HTTPException(status_code=403, detail="Companion mTLS verification required.")
    if not fingerprint or not hmac.compare_digest(fingerprint, expected_fingerprint.lower()):
        raise HTTPException(
            status_code=403, detail="Companion certificate does not match this scan."
        )
    if (
        not timestamp_raw
        or not nonce
        or len(nonce) > 200
        or len(body_digest) != 64
        or any(char not in "0123456789abcdef" for char in body_digest)
        or not supplied
        or request.url.query
    ):
        raise HTTPException(status_code=403, detail="Signed companion proxy assertion required.")
    try:
        timestamp = int(timestamp_raw)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail="Invalid companion proxy assertion.") from exc
    if abs(time.time() - timestamp) > settings.protected_agent_proxy_max_age_s:
        raise HTTPException(status_code=403, detail="Companion proxy assertion expired.")

    content_length = request.headers.get("content-length")
    if content_length:
        try:
            declared_length = int(content_length)
        except ValueError as exc:
            raise HTTPException(
                status_code=403, detail="Invalid companion request length."
            ) from exc
        if declared_length < 0 or declared_length > settings.protected_request_body_max_bytes:
            raise HTTPException(status_code=413, detail="Companion request body is too large.")
    body = await request.body()
    if len(body) > settings.protected_request_body_max_bytes:
        raise HTTPException(status_code=413, detail="Companion request body is too large.")
    actual_body_digest = hashlib.sha256(body).hexdigest()
    if not hmac.compare_digest(body_digest, actual_body_digest):
        raise HTTPException(
            status_code=403,
            detail="Companion request body did not match its proxy assertion.",
        )

    # Canonicalize values before signing/verifying. The proxy may use a
    # product-specific successful verification token (for example SUCCESS),
    # but Axcess signs its lower-cased form to make the boundary unambiguous.
    message = "\n".join(
        (
            request.method.upper(),
            request.url.path,
            timestamp_raw,
            nonce,
            verified,
            fingerprint,
            body_digest,
        )
    ).encode("utf-8")
    expected = hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(supplied, expected):
        raise HTTPException(status_code=403, detail="Invalid companion proxy assertion.")

    now = time.time()
    _discard_expired_agent_replays(now)
    # Store a digest rather than proxy input itself. This process-local cache
    # is intentionally bounded; production relies on the proxy's certificate
    # boundary in addition to this application-level replay guard.
    replay_key = hashlib.sha256(message + supplied.encode("ascii", errors="ignore")).hexdigest()
    if replay_key in _seen_agent_assertions:
        raise HTTPException(status_code=403, detail="Companion proxy assertion was already used.")
    while len(_seen_agent_assertions) >= settings.protected_agent_proxy_replay_max_entries:
        oldest = min(_seen_agent_assertions, key=_seen_agent_assertions.__getitem__)
        del _seen_agent_assertions[oldest]
    _seen_agent_assertions[replay_key] = now + settings.protected_agent_proxy_max_age_s


def _discard_expired_replays(now: float) -> None:
    for key, expires_at in list(_seen_signatures.items()):
        if expires_at <= now:
            del _seen_signatures[key]


def _discard_expired_agent_replays(now: float) -> None:
    for key, expires_at in list(_seen_agent_assertions.items()):
        if expires_at <= now:
            del _seen_agent_assertions[key]
