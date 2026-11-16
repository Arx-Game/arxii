"""Typed exceptions for the checks system.

Each carries a ``user_message`` safe to surface to a player; never pass ``str(exc)`` or
internal detail into an API response.
"""

from __future__ import annotations


class ChecksError(Exception):
    """Base for checks errors. Carries a player-safe message."""

    user_message = "That check could not be completed."

    def __init__(self, user_message: str | None = None) -> None:
        if user_message is not None:
            self.user_message = user_message
        super().__init__(self.user_message)


class ModifierConfigError(ChecksError):
    """A level the checks core needs has no authored row to read (#5093).

    Raised by the baseline readers when a lane has no ``ModifierLevelBaseline`` row at or
    below the requested level. Staff author the missing row; the required-content probe
    names it.
    """

    user_message = "The check scale is not fully configured."
