"""Configuration seam for an approved protected-evidence KMS vault.

The application deliberately does not implement a cloud KMS adapter itself:
that adapter must be supplied and reviewed by the deployment owner.  This
module loads one explicit administrator-configured factory for the web host
and scheduled retention command without accepting credentials or arbitrary
provider options from a browser or command line.
"""

from __future__ import annotations

import importlib
import re
from collections.abc import Callable
from typing import Any, cast

from audit.config import Settings
from audit.protected.crypto import ProtectedVault

_VAULT_FACTORY_PATH = re.compile(
    r"^(?P<module>[A-Za-z_][A-Za-z0-9_.]*):(?P<attribute>[A-Za-z_][A-Za-z0-9_]*)$"
)


def resolve_configured_protected_vault(settings: Settings) -> ProtectedVault | None:
    """Build the deployment-owned production vault, or return ``None`` safely.

    ``AUDIT_PROTECTED_KMS_VAULT_FACTORY`` is an administrator-controlled,
    import-safe ``package.module:factory`` reference.  The factory receives
    the resolved ``Settings`` and must return a ``ProtectedVault`` around a
    deployment-approved, per-scan-revocable KMS adapter.  Its credentials
    remain wholly within that adapter's own approved configuration channel.

    Configuration/import errors intentionally collapse to ``None``.  Browser
    APIs and maintenance callers report a generic unavailable-KMS state rather
    than exposing a provider module, filesystem path, endpoint, or exception
    text in an HTTP response, command output, or process log.
    """

    configured = settings.protected_kms_vault_factory.strip()
    match = _VAULT_FACTORY_PATH.fullmatch(configured)
    if match is None:
        return None
    try:
        module = importlib.import_module(match.group("module"))
        factory = getattr(module, match.group("attribute"))
        if not callable(factory):
            return None
        result = cast(Callable[[Settings], Any], factory)(settings)
    except Exception:
        return None
    return result if isinstance(result, ProtectedVault) else None


def has_irreversible_protected_vault(vault: ProtectedVault | None) -> bool:
    """Return whether a configured vault can enforce backup-safe erasure."""

    if vault is None:
        return False
    try:
        return vault.supports_irreversible_scan_key_destruction
    except Exception:
        return False
