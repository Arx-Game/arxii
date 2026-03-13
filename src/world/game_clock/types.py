"""Type definitions for the game clock system."""

# User-safe error messages for clock operations. These are the only strings
# that should ever be returned in API error responses.
_CLOCK_ERROR_MESSAGES: dict[str, str] = {
    "NOT_CONFIGURED": "Game clock is not configured.",
    "ALREADY_PAUSED": "Game clock is already paused.",
    "NOT_PAUSED": "Game clock is not paused.",
    "INVALID_RATIO": "Time ratio must be positive.",
    "CONVERSION_UNAVAILABLE": (
        "Cannot convert IC-to-real while clock is paused or has zero ratio."
    ),
}


class ClockError(Exception):
    """User-safe error from clock operations.

    Always raised with one of the class-level message constants. Use
    ``exc.user_message`` in API responses instead of ``str(exc)`` to
    avoid CodeQL "information exposure through exception" warnings.
    """

    NOT_CONFIGURED = _CLOCK_ERROR_MESSAGES["NOT_CONFIGURED"]
    ALREADY_PAUSED = _CLOCK_ERROR_MESSAGES["ALREADY_PAUSED"]
    NOT_PAUSED = _CLOCK_ERROR_MESSAGES["NOT_PAUSED"]
    INVALID_RATIO = _CLOCK_ERROR_MESSAGES["INVALID_RATIO"]
    CONVERSION_UNAVAILABLE = _CLOCK_ERROR_MESSAGES["CONVERSION_UNAVAILABLE"]

    @property
    def user_message(self) -> str:
        """Return the user-safe error message.

        Only returns messages from the known allowlist. Falls back to a
        generic message if the exception was somehow raised with an
        unknown string, preventing internal details from leaking.
        """
        msg = self.args[0] if self.args else ""
        if msg in _CLOCK_ERROR_MESSAGES.values():
            return msg
        return "An unexpected clock error occurred."
