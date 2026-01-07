"""Utility functions for API views."""

from __future__ import annotations

from collections.abc import Callable
import logging

from django.db import ProgrammingError

logger = logging.getLogger(__name__)

# Log message for missing tables (kept short to avoid line length issues)
_MISSING_TABLE_LOG = "Table for %s not found (dev mode) - returning default"


def safe_queryset_or_empty[T](
    queryset_fn: Callable[[], T],
    default: T,
    feature_name: str = "feature",
) -> T:
    """
    Execute a queryset function and return a default if the table doesn't exist.

    Use this when querying models whose tables may not exist yet during development.

    Usage:
        recent_players = safe_queryset_or_empty(
            lambda: list(RosterEntry.objects.filter(...)[:4]),
            default=[],
            feature_name="roster entries",
        )

    Args:
        queryset_fn: A callable that returns the queryset result
        default: The value to return if the table is missing
        feature_name: Name of the feature for logging purposes

    Returns:
        The queryset result, or the default if the table doesn't exist
    """
    try:
        return queryset_fn()
    except ProgrammingError as e:
        if "does not exist" in str(e):
            logger.debug(_MISSING_TABLE_LOG, feature_name)
            return default
        raise
