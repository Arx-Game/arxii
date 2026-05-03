"""Custom exception handling for API views."""

import logging

from django.conf import settings
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler

logger = logging.getLogger(__name__)


def custom_exception_handler(exc, context):
    """
    Custom exception handler for DRF.

    Handled DRF exceptions (4xx) are logged at DEBUG: they're correct responses
    to bad input, not server errors. Unhandled exceptions become 5xx and are
    logged at ERROR with full traceback.
    """
    response = exception_handler(exc, context)

    view = context.get("view", "unknown")

    if response is not None:
        logger.debug(
            "API exception in %s: %s (status %s)",
            view,
            exc,
            response.status_code,
        )
        return response

    logger.exception("Unhandled API exception in %s: %s", view, exc)

    if settings.DEBUG:
        err_message = str(exc)
    else:
        err_message = "An unexpected error occurred"
    return Response(
        {
            "error": "Internal server error",
            "detail": err_message,
        },
        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )
