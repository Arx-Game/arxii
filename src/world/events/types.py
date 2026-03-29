"""Type definitions for the events system."""

# User-safe error messages for event operations. These are the only strings
# that should ever be returned in API error responses.
_EVENT_ERROR_MESSAGES: dict[str, str] = {
    "LOCATION_GAP": "Another event is scheduled within 6 hours at this location.",
    "CANCEL_TERMINAL": "Cannot cancel a completed or already-cancelled event.",
    "CANCEL_ACTIVE": "Cannot cancel an active event. Use complete to end it.",
    "SCHEDULE_INVALID": "This event cannot be scheduled from its current status.",
    "START_INVALID": "This event cannot be started from its current status.",
    "COMPLETE_INVALID": "This event cannot be completed from its current status.",
    "UPDATE_LOCKED": "Cannot update an event that is active, completed, or cancelled.",
    "NO_PERSONA": "You must have an active character with a persona to create events.",
}


class EventError(Exception):
    """User-safe error from event operations.

    Always raised with one of the class-level message constants. Use
    ``exc.user_message`` in API responses instead of ``str(exc)`` to
    avoid CodeQL "information exposure through exception" warnings.
    """

    LOCATION_GAP = _EVENT_ERROR_MESSAGES["LOCATION_GAP"]
    CANCEL_TERMINAL = _EVENT_ERROR_MESSAGES["CANCEL_TERMINAL"]
    CANCEL_ACTIVE = _EVENT_ERROR_MESSAGES["CANCEL_ACTIVE"]
    SCHEDULE_INVALID = _EVENT_ERROR_MESSAGES["SCHEDULE_INVALID"]
    START_INVALID = _EVENT_ERROR_MESSAGES["START_INVALID"]
    COMPLETE_INVALID = _EVENT_ERROR_MESSAGES["COMPLETE_INVALID"]
    UPDATE_LOCKED = _EVENT_ERROR_MESSAGES["UPDATE_LOCKED"]
    NO_PERSONA = _EVENT_ERROR_MESSAGES["NO_PERSONA"]

    @property
    def user_message(self) -> str:
        """Return the user-safe error message.

        Only returns messages from the known allowlist. Falls back to a
        generic message if the exception was somehow raised with an
        unknown string, preventing internal details from leaking.
        """
        msg = self.args[0] if self.args else ""
        if msg in _EVENT_ERROR_MESSAGES.values():
            return msg
        return "An unexpected event error occurred."
