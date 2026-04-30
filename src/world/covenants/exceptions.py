"""Typed exceptions for the covenants app."""

from typing import ClassVar


class CovenantError(Exception):
    """Base for covenant typed exceptions."""

    user_message: str = "An unexpected covenant error occurred."
    SAFE_MESSAGES: ClassVar[frozenset[str]] = frozenset(
        {
            "An unexpected covenant error occurred.",
        }
    )


class CovenantRoleNeverHeldError(CovenantError):
    """Raised when weaving a COVENANT_ROLE thread for a role never held."""

    user_message = "You must have held this role before you can weave a thread to it."
    SAFE_MESSAGES: ClassVar[frozenset[str]] = frozenset(
        {
            "You must have held this role before you can weave a thread to it.",
        }
    )
