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


class CovenantFormationError(CovenantError):
    """Base for covenant formation failures."""

    user_message = "Covenant formation failed."
    SAFE_MESSAGES: ClassVar[frozenset[str]] = frozenset(
        {
            "Covenant formation failed.",
        }
    )


class InsufficientFoundersError(CovenantFormationError):
    """Raised when covenant formation is attempted with fewer than two founders.

    Covenants are inherently group structures; collaborative play is the
    point. See `feedback_covenants_are_group_only.md`.
    """

    user_message = "A covenant must be founded by at least two characters."
    SAFE_MESSAGES: ClassVar[frozenset[str]] = frozenset(
        {
            "A covenant must be founded by at least two characters.",
        }
    )


class DuplicateFounderError(CovenantFormationError):
    """Raised when the founder list names the same character more than once."""

    user_message = "Each founder must be a distinct character."
    SAFE_MESSAGES: ClassVar[frozenset[str]] = frozenset(
        {
            "Each founder must be a distinct character.",
        }
    )
