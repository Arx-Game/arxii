"""Typed exceptions for the societies app."""

from typing import ClassVar


class LegendError(Exception):
    """Base for societies legend-related typed exceptions.

    Each subclass carries a ``user_message`` class attribute and a ``SAFE_MESSAGES``
    allowlist so callers can surface the message to end-users safely.
    """

    user_message: str = "An error occurred while awarding legend."
    SAFE_MESSAGES: ClassVar[frozenset[str]] = frozenset(
        {
            "An error occurred while awarding legend.",
        }
    )


class LegendAwardParticipantMissingError(LegendError):
    """Raised when a LEGEND_AWARD effect is applied with no participants in context."""

    user_message = "Cannot award legend without participants."
    SAFE_MESSAGES: ClassVar[frozenset[str]] = frozenset(
        {
            "Cannot award legend without participants.",
        }
    )


class LegendAwardScopeError(LegendError):
    """Raised when a LEGEND_AWARD effect is attached to a GLOBAL-scope beat.

    GLOBAL-scope beats do not map to a concrete set of participants, so legend
    cannot be awarded. Task 13 (beat resolution wiring) raises this during
    pool application when it detects a GLOBAL-scope beat with a LEGEND_AWARD
    effect.
    """

    user_message = "Legend awards from GLOBAL-scope beats are not supported."
    SAFE_MESSAGES: ClassVar[frozenset[str]] = frozenset(
        {
            "Legend awards from GLOBAL-scope beats are not supported.",
        }
    )
