"""Tests for custom_exception_handler log-level behavior."""

from unittest.mock import patch

from django.test import TestCase
from rest_framework.exceptions import NotAuthenticated, PermissionDenied, ValidationError

from web.api.exceptions import custom_exception_handler


class CustomExceptionHandlerLogLevelTests(TestCase):
    """4xx exceptions are not server errors — should not log at ERROR level."""

    def _context(self):
        return {"view": None, "request": None}

    def test_not_authenticated_logs_at_debug_not_error(self):
        with patch("web.api.exceptions.logger") as mock_logger:
            response = custom_exception_handler(NotAuthenticated(), self._context())
        self.assertEqual(response.status_code, 401)
        mock_logger.exception.assert_not_called()
        mock_logger.error.assert_not_called()
        mock_logger.debug.assert_called()

    def test_permission_denied_logs_at_debug(self):
        with patch("web.api.exceptions.logger") as mock_logger:
            response = custom_exception_handler(PermissionDenied(), self._context())
        self.assertEqual(response.status_code, 403)
        mock_logger.exception.assert_not_called()
        mock_logger.debug.assert_called()

    def test_validation_error_logs_at_debug(self):
        with patch("web.api.exceptions.logger") as mock_logger:
            response = custom_exception_handler(
                ValidationError({"field": ["bad"]}), self._context()
            )
        self.assertEqual(response.status_code, 400)
        mock_logger.exception.assert_not_called()
        mock_logger.debug.assert_called()

    def test_unhandled_exception_logs_at_error_with_traceback(self):
        with patch("web.api.exceptions.logger") as mock_logger:
            response = custom_exception_handler(RuntimeError("boom"), self._context())
        self.assertEqual(response.status_code, 500)
        mock_logger.exception.assert_called_once()
