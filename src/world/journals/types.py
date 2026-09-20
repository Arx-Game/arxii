"""Type definitions for the journal system."""

from dataclasses import dataclass

_JOURNAL_ERROR_MESSAGES: dict[str, str] = {
    "PRIVATE_PARENT": "Cannot respond to a private journal entry.",
    "SELF_RESPONSE": "Cannot respond to your own journal entry.",
    "EDIT_RESPONSE": "Cannot edit a response entry.",
    # Neutral, shared, and constant on purpose (#2996 Decision 2) — a rejection here can't
    # leak that a block is involved: "this entry isn't available to respond to right now" has
    # many innocent causes (deleted, locked, moderation, ...). Never says "blocked."
    "UNAVAILABLE": "This entry is not available to respond to right now.",
    "INVALID_DISPOSITION": "That is not a valid posthumous disposition.",
    "INVALID_CONSENT": "That is not a valid retort consent.",
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
    INVALID_DISPOSITION = _JOURNAL_ERROR_MESSAGES["INVALID_DISPOSITION"]
    INVALID_CONSENT = _JOURNAL_ERROR_MESSAGES["INVALID_CONSENT"]

    @property
    def user_message(self) -> str:
        msg = self.args[0] if self.args else ""
        if msg in _JOURNAL_ERROR_MESSAGES.values():
            return msg
        return "An unexpected journal error occurred."


@dataclass(frozen=True)
class JournalSettings:
    """The owner's journal preferences plus the weekly writing count (#3941)."""

    posthumous_journal_disposition: str
    retort_consent: str
    posts_this_week: int
    rewarded_posts_per_week: int
