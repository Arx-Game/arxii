"""Type definitions for the game clock system."""

from dataclasses import dataclass
from datetime import datetime

from world.game_clock.constants import JumpDirection

# User-safe error messages for clock operations. These are the only strings
# that should ever be returned in API error responses.
_CLOCK_ERROR_MESSAGES: dict[str, str] = {
    "NOT_CONFIGURED": "Game clock is not configured.",
    "ALREADY_PAUSED": "Game clock is already paused.",
    "NOT_PAUSED": "Game clock is not paused.",
    "INVALID_RATIO": "Time ratio must be positive.",
    "CONVERSION_UNAVAILABLE": (
        "Cannot convert IC-to-real while clock is paused or has zero ratio."
    ),
    "EARLIER_KEEPS_AGES": "A change to an earlier date keeps characters' ages.",
    "JUMP_TOO_FAR": ("That date is too far away: something already dated cannot follow the jump."),
}


class ClockError(Exception):
    """User-safe error from clock operations.

    Always raised with one of the class-level message constants. Use
    ``exc.user_message`` in API responses instead of ``str(exc)`` to
    avoid CodeQL "information exposure through exception" warnings.
    """

    NOT_CONFIGURED = _CLOCK_ERROR_MESSAGES["NOT_CONFIGURED"]
    ALREADY_PAUSED = _CLOCK_ERROR_MESSAGES["ALREADY_PAUSED"]
    NOT_PAUSED = _CLOCK_ERROR_MESSAGES["NOT_PAUSED"]
    INVALID_RATIO = _CLOCK_ERROR_MESSAGES["INVALID_RATIO"]
    CONVERSION_UNAVAILABLE = _CLOCK_ERROR_MESSAGES["CONVERSION_UNAVAILABLE"]
    EARLIER_KEEPS_AGES = _CLOCK_ERROR_MESSAGES["EARLIER_KEEPS_AGES"]
    JUMP_TOO_FAR = _CLOCK_ERROR_MESSAGES["JUMP_TOO_FAR"]

    @property
    def user_message(self) -> str:
        """Return the user-safe error message.

        Only returns messages from the known allowlist. Falls back to a
        generic message if the exception was somehow raised with an
        unknown string, preventing internal details from leaking.
        """
        msg = self.args[0] if self.args else ""
        if msg in _CLOCK_ERROR_MESSAGES.values():
            return msg
        return "An unexpected clock error occurred."


@dataclass(frozen=True)
class ClockJumpPreview:
    """What setting the clock to ``new_ic_time`` would do, read before anything is
    written (#5248). The staff clock page builds its sentence and its counts from this."""

    current_ic_time: datetime
    new_ic_time: datetime
    direction: JumpDirection
    #: Calendar years between the two dates (new year minus current year). This is the
    #: number every birth year moves by when ages are kept.
    year_shift: int
    characters_with_birth_year: int
    upcoming_events: int
    #: Names of heritages whose first appearance is later than the new date. Character
    #: creation's age ceiling for such a heritage falls to its floor.
    heritages_not_yet_appeared: list[str]
