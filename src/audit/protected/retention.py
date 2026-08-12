"""Retention schedule for protected evidence."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

PROTECTED_DATA_RETENTION = timedelta(days=7)


def protected_cleanup_deadline(created_at: datetime) -> datetime:
    """Return the mandatory seven-day crypto-erasure deadline in UTC."""

    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=UTC)
    return created_at.astimezone(UTC) + PROTECTED_DATA_RETENTION
