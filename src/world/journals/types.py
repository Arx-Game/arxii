"""Type definitions for the journal system."""

_JOURNAL_ERROR_MESSAGES: dict[str, str] = {
    "PRIVATE_PARENT": "Cannot respond to a private journal entry.",
    "SELF_RESPONSE": "Cannot respond to your own journal entry.",
    "EDIT_RESPONSE": "Cannot edit a response entry.",
    # Neutral, shared, and constant on purpose (#2996 Decision 2) — a rejection here can't
    # leak that a block is involved: "this entry isn't available to respond to right now" has
    # many innocent causes (deleted, locked, moderation, ...). Never says "blocked."
    "UNAVAILABLE": "This entry is not available to respond to right now.",
}


class JournalError(Exception):
    """User-safe validation error from journal operations.

    Always raised with one of the class-level message constants. Use
    ``exc.user_message`` in API responses instead of ``str(exc)`` to
    avoid CodeQL "information exposure through exception" warnings.
    """

    PRIVATE_PARENT = _JOURNAL_ERROR_MESSAGES["PRIVATE_PARENT"]
    SELF_RESPONSE = _JOURNAL_ERROR_MESSAGES["SELF_RESPONSE"]
    EDIT_RESPONSE = _JOURNAL_ERROR_MESSAGES["EDIT_RESPONSE"]
    UNAVAILABLE = _JOURNAL_ERROR_MESSAGES["UNAVAILABLE"]

    @property
    def user_message(self) -> str:
        msg = self.args[0] if self.args else ""
        if msg in _JOURNAL_ERROR_MESSAGES.values():
            return msg
        return "An unexpected journal error occurred."
