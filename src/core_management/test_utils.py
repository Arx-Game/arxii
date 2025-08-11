from functools import wraps
import logging


def suppress_permission_errors(func):
    """Decorator to suppress logging for expected permission errors in tests."""

    @wraps(func)
    def wrapper(*args, **kwargs):
        # Suppress logging for web.api.exceptions and django.request during test
        loggers_to_suppress = [
            "web.api.exceptions",
            "django.request",
        ]
        original_levels = {}

        for logger_name in loggers_to_suppress:
            logger = logging.getLogger(logger_name)
            original_levels[logger_name] = logger.level
            logger.setLevel(logging.CRITICAL)

        try:
            return func(*args, **kwargs)
        finally:
            # Restore original log levels
            for logger_name, original_level in original_levels.items():
                logging.getLogger(logger_name).setLevel(original_level)

    return wrapper
