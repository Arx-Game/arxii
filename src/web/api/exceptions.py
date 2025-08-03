"""Custom exception handling for API views."""

import logging

from rest_framework.views import exception_handler

logger = logging.getLogger(__name__)


def custom_exception_handler(exc, context):
    """
    Custom exception handler that logs errors and returns JSON responses.

    This ensures that API errors are properly logged and never return HTML.
    """
    # Log the exception with full traceback
    logger.exception("API error in %s: %s", context.get("view", "unknown"), exc)

    # Call REST framework's default exception handler first
    # to get the standard error response.
    response = exception_handler(exc, context)

    if response is not None:
        # We have a valid DRF response, return it as-is
        return response

    # For unhandled exceptions, return a generic 500 error as JSON
    from rest_framework import status
    from rest_framework.response import Response

    return Response(
        {
            "error": "Internal server error",
            "detail": (
                str(exc) if hasattr(exc, "__str__") else "An unexpected error occurred"
            ),
        },
        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )
