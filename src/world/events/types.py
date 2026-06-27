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
    "INVITE_ACTIVE": "Cannot invite to an event that is active or finished.",
    "INVITE_MODIFY_ACTIVE": "Cannot modify invitations on an active or finished event.",
    "INVITE_DUPLICATE": "This target is already invited.",
    "PRIVATE_IN_PUBLIC_ROOM": "A private event cannot be held in a publicly-listed room.",
    "RSVP_NOT_PERSONA": "Only persona invitations can be RSVP'd.",
    "RSVP_NOT_YOURS": "That invitation is not yours to respond to.",
    "RSVP_CLOSED": "Cannot RSVP to an invitation for an active or finished event.",
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
    INVITE_ACTIVE = _EVENT_ERROR_MESSAGES["INVITE_ACTIVE"]
    INVITE_MODIFY_ACTIVE = _EVENT_ERROR_MESSAGES["INVITE_MODIFY_ACTIVE"]
    INVITE_DUPLICATE = _EVENT_ERROR_MESSAGES["INVITE_DUPLICATE"]
    PRIVATE_IN_PUBLIC_ROOM = _EVENT_ERROR_MESSAGES["PRIVATE_IN_PUBLIC_ROOM"]
    RSVP_NOT_PERSONA = _EVENT_ERROR_MESSAGES["RSVP_NOT_PERSONA"]
    RSVP_NOT_YOURS = _EVENT_ERROR_MESSAGES["RSVP_NOT_YOURS"]
    RSVP_CLOSED = _EVENT_ERROR_MESSAGES["RSVP_CLOSED"]

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
