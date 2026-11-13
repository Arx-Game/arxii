"""Player-facing missive failures (#3289). ``user_message`` is safe to display."""

from __future__ import annotations


class MissiveError(Exception):
    """Base: a missive could not be written, sent or resolved.

    ``user_message`` is player-safe copy in plain play words; callers show it
    as-is and never ``str(exc)``.
    """

    user_message: str = "That letter cannot be sent."

    def __init__(self, user_message: str | None = None) -> None:
        if user_message is not None:
            self.user_message = user_message
        super().__init__(self.user_message)
