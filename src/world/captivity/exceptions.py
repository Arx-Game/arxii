"""Typed exceptions for the captivity system (#931).

Each carries a ``user_message`` safe to surface to a player — never pass
``str(exc)`` or internal detail into an API response.
"""

from __future__ import annotations


class CaptivityError(Exception):
    """Base for captivity errors. Carries a player-safe message."""

    user_message = "That captivity action could not be completed."

    def __init__(self, user_message: str | None = None) -> None:
        if user_message is not None:
            self.user_message = user_message
        super().__init__(self.user_message)


class AlreadyCapturedError(CaptivityError):
    """The character is already held — they cannot be captured twice."""

    user_message = "That character is already a captive."


class NotHeldError(CaptivityError):
    """The captivity is already resolved — it cannot be resolved again."""

    user_message = "That captivity has already ended."


class NoCaptorError(CaptivityError):
    """A ransom needs a captor org to demand it; this captivity has none."""

    user_message = "No captor is holding this character to ransom."


class NoRansomError(CaptivityError):
    """There is no ransom demand to pay on this captivity."""

    user_message = "There is no ransom demand to pay."


class InsufficientTreasuryError(CaptivityError):
    """The paying organization's treasury cannot cover the ransom."""

    user_message = "The treasury cannot cover that ransom."
