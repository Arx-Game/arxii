"""Type definitions for the journal system."""


class JournalError(Exception):
    """User-safe validation error from journal operations.

    The message is always safe to return in API responses —
    it contains no stack traces or internal state.
    All user-facing messages are defined here as class constants.
    """

    PRIVATE_PARENT = "Cannot respond to a private journal entry."
    SELF_RESPONSE = "Cannot respond to your own journal entry."
    EDIT_RESPONSE = "Cannot edit a response entry."
