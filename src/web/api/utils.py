"""Utility functions for API views."""

from collections.abc import Callable
from contextlib import contextmanager
from functools import wraps
import logging
from typing import Any

from django.db import ProgrammingError

logger = logging.getLogger(__name__)

# Log message for missing tables (kept short to avoid line length issues)
_MISSING_TABLE_LOG = "Table for %s not found (dev mode) - returning default"


@contextmanager
def graceful_missing_table[T](default: T, feature_name: str = "feature"):
    """
    Context manager that catches ProgrammingError (missing table) and yields a default value.

    Use this when querying models whose tables may not exist yet during development.

    Usage:
        with graceful_missing_table([], "roster entries"):
            result = list(RosterEntry.objects.all())

    Args:
        default: The value to use if the table is missing
        feature_name: Name of the feature for logging purposes

    Yields:
        A mutable container [value] that will contain the result or default
    """
    container = {"value": default}
    try:
        yield container
    except ProgrammingError as e:
        if "does not exist" in str(e):
            logger.debug(_MISSING_TABLE_LOG, feature_name)
            container["value"] = default
        else:
            raise


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


def graceful_view_queryset(default_factory: Callable[[], Any], feature_name: str = "feature"):
    """
    Decorator for view methods that may query tables that don't exist yet.

    Catches ProgrammingError and returns an empty response with the default value.

    Usage:
        @graceful_view_queryset(lambda: [], "roster entries")
        def get_recent_players(self):
            return list(RosterEntry.objects.all())

    Args:
        default_factory: A callable that returns the default value
        feature_name: Name of the feature for logging purposes
    """

    def decorator(fn: Callable) -> Callable:
        @wraps(fn)
        def wrapper(*args, **kwargs):
            try:
                return fn(*args, **kwargs)
            except ProgrammingError as e:
                if "does not exist" in str(e):
                    logger.debug(_MISSING_TABLE_LOG, feature_name)
                    return default_factory()
                raise

        return wrapper

    return decorator
