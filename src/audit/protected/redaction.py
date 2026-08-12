"""Best-effort redaction before protected metadata or evidence is retained.

Redaction is defence in depth, not a licence to store session material.  The
vault rejects browser state outright; these helpers remove common accidental
secrets and identifiers from otherwise eligible audit notes and text evidence.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any
from urllib.parse import parse_qsl, unquote_plus, urlencode, urlsplit, urlunsplit

_SENSITIVE_KEY = re.compile(
    r"(?:^|[_-])(?:authorization|auth|cookie|csrf|xsrf|password|passwd|pwd|"
    r"secret|token|session|credential|api[_-]?key|private[_-]?key|otp|mfa|"
    r"code|storage[_-]?state)(?:$|[_-])",
    re.IGNORECASE,
)
_URL_PATTERN = re.compile(r"https?://[^\s\"'<>]+", re.IGNORECASE)
_HEADER_PATTERN = re.compile(
    r"(?im)^(\s*(?:authorization|proxy-authorization|cookie|set-cookie|"
    r"x-api-key|x-auth-token|x-csrf-token|access[_-]?token|refresh[_-]?token|"
    r"id[_-]?token|token|session(?:[_-]?id|[_-]?token)?|password|secret|otp)"
    r"\s*[:=]\s*)([^\r\n]+)$"
)
_BEARER_PATTERN = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/-]+=*")
_EMAIL_PATTERN = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
_SSN_PATTERN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
_PHONE_PATTERN = re.compile(r"(?<!\d)(?:\+?1[ .-]?)?(?:\(?\d{3}\)?[ .-]?)\d{3}[ .-]\d{4}(?!\d)")

REDACTED_VALUE = "<redacted>"
_SENSITIVE_COMPACT_KEYS = frozenset(
    {
        "accesstoken",
        "apikey",
        "assertion",
        "authorization",
        "authtoken",
        "clientsecret",
        "code",
        "cookie",
        "credential",
        "csrf",
        "idtoken",
        "jwt",
        "oauthcode",
        "otp",
        "passkey",
        "password",
        "refreshtoken",
        "recoverycode",
        "samlrequest",
        "samlresponse",
        "secret",
        "session",
        "sessionid",
        "sessiontoken",
        "signature",
        "storagestate",
        "token",
        "totp",
        "webauthn",
        "xsrf",
    }
)


def is_sensitive_key(key: str) -> bool:
    """Return whether a structured field name may hold authentication material."""

    normalized = unquote_plus(key).strip().replace(" ", "_")
    compact = re.sub(r"[^a-z0-9]", "", normalized.casefold())
    return bool(_SENSITIVE_KEY.search(normalized)) or compact in _SENSITIVE_COMPACT_KEYS


def redact_url(value: str) -> str:
    """Preserve a useful URL while removing credentials and secret parameters."""

    try:
        parsed = urlsplit(value)
    except ValueError:
        return "<redacted-url>"
    if not parsed.scheme or not parsed.netloc:
        return redact_text(value, redact_urls=False)

    try:
        hostname = parsed.hostname
        port = parsed.port
    except ValueError:
        return "<redacted-url>"
    if hostname is None:
        return "<redacted-url>"
    host = hostname
    if ":" in host:  # Re-bracket an IPv6 literal after urlsplit normalization.
        host = f"[{host}]"
    netloc = f"{host}:{port}" if port is not None else host
    query_parts: list[tuple[str, str]] = []
    for key, item in parse_qsl(parsed.query, keep_blank_values=True):
        safe_item = (
            REDACTED_VALUE if is_sensitive_key(key) else redact_text(item, redact_urls=False)
        )
        query_parts.append((key, safe_item))
    query = urlencode(query_parts, doseq=True)
    # Fragments are client-side and often carry reset or access material; omit
    # them rather than trying to classify individual fragment formats.
    safe_path = redact_text(parsed.path, redact_urls=False)
    return urlunsplit((parsed.scheme.lower(), netloc, safe_path, query, ""))


def redact_text(value: str, *, redact_urls: bool = True) -> str:
    """Redact common auth values, URLs, and direct identifiers from text."""

    result = value
    if redact_urls:
        result = _URL_PATTERN.sub(lambda match: redact_url(match.group(0)), result)
    result = _HEADER_PATTERN.sub(lambda match: f"{match.group(1)}{REDACTED_VALUE}", result)
    result = _BEARER_PATTERN.sub("Bearer <redacted>", result)
    result = _EMAIL_PATTERN.sub("<redacted-email>", result)
    result = _SSN_PATTERN.sub("<redacted-ssn>", result)
    return _PHONE_PATTERN.sub("<redacted-phone>", result)


def contains_auth_material(value: str) -> bool:
    """Return whether a free-text metadata field appears to contain a secret.

    This deliberately does not flag an email address or an ordinary audit
    subject.  It catches values that would otherwise make a plaintext approval
    or identity column a side channel for a bearer credential.
    """

    if _HEADER_PATTERN.search(value) or _BEARER_PATTERN.search(value):
        return True
    try:
        parsed = urlsplit(value)
    except ValueError:
        return False
    if parsed.scheme and parsed.netloc:
        return redact_url(value) != value
    return False


def redact_value(value: Any, *, field_name: str | None = None) -> Any:
    """Return a JSON-safe recursively redacted equivalent of ``value``.

    The function intentionally converts unknown objects to redacted text rather
    than relying on their repr, which could include a secret-bearing URL or
    header object.
    """

    if field_name is not None and is_sensitive_key(field_name):
        return REDACTED_VALUE
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, Mapping):
        return {str(key): redact_value(item, field_name=str(key)) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, memoryview)):
        return [redact_value(item) for item in value]
    if isinstance(value, (bytes, bytearray, memoryview)):
        return "<redacted-binary>"
    return REDACTED_VALUE


def redact_mapping(values: Mapping[str, Any]) -> dict[str, Any]:
    """Convenience wrapper for a JSON object that will be persisted."""

    return {str(key): redact_value(value, field_name=str(key)) for key, value in values.items()}
