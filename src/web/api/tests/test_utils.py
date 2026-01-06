"""Tests for API utility functions."""

import unittest

from django.db import ProgrammingError

from web.api.utils import graceful_missing_table, safe_queryset_or_empty

# Error messages used in tests
MISSING_TABLE_ERROR = 'relation "test_table" does not exist'
OTHER_PROGRAMMING_ERROR = "some other programming error"
VALUE_ERROR_MSG = "something went wrong"


class SafeQuerysetOrEmptyTestCase(unittest.TestCase):
    """Tests for the safe_queryset_or_empty utility function."""

    def test_returns_result_when_query_succeeds(self):
        """Should return the actual result when query succeeds."""
        result = safe_queryset_or_empty(
            lambda: [1, 2, 3],
            default=[],
            feature_name="test feature",
        )
        self.assertEqual(result, [1, 2, 3])

    def test_returns_default_when_table_missing(self):
        """Should return default value when table doesn't exist."""

        def raise_missing_table():
            raise ProgrammingError(MISSING_TABLE_ERROR)

        result = safe_queryset_or_empty(
            raise_missing_table,
            default=["fallback"],
            feature_name="test feature",
        )
        self.assertEqual(result, ["fallback"])

    def test_reraises_other_programming_errors(self):
        """Should re-raise ProgrammingError for other issues."""

        def raise_other_error():
            raise ProgrammingError(OTHER_PROGRAMMING_ERROR)

        with self.assertRaises(ProgrammingError):
            safe_queryset_or_empty(
                raise_other_error,
                default=[],
                feature_name="test feature",
            )

    def test_reraises_non_programming_errors(self):
        """Should re-raise non-ProgrammingError exceptions."""

        def raise_value_error():
            raise ValueError(VALUE_ERROR_MSG)

        with self.assertRaises(ValueError):
            safe_queryset_or_empty(
                raise_value_error,
                default=[],
                feature_name="test feature",
            )


class GracefulMissingTableContextManagerTestCase(unittest.TestCase):
    """Tests for the graceful_missing_table context manager."""

    def test_captures_result_when_query_succeeds(self):
        """Should capture the actual result when query succeeds."""
        with graceful_missing_table([], "test feature") as container:
            container["value"] = [1, 2, 3]

        self.assertEqual(container["value"], [1, 2, 3])

    def test_returns_default_when_table_missing(self):
        """Should return default value when table doesn't exist."""
        with graceful_missing_table(["default"], "test feature") as container:
            raise ProgrammingError(MISSING_TABLE_ERROR)

        # Note: This assertion IS reachable because the context manager catches the exception
        self.assertEqual(container["value"], ["default"])

    def test_reraises_other_programming_errors(self):
        """Should re-raise ProgrammingError for other issues."""
        with self.assertRaises(ProgrammingError):
            with graceful_missing_table([], "test feature"):
                raise ProgrammingError(OTHER_PROGRAMMING_ERROR)
