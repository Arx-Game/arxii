"""Exception hierarchy for the battles system."""

from __future__ import annotations


class BattleError(Exception):
    """Base exception for all battle-system errors.

    Attributes:
        user_message: A human-readable message safe to surface to players.
    """

    def __init__(self, user_message: str = "") -> None:
        super().__init__(user_message)
        self.user_message = user_message


class BattleConcludedError(BattleError):
    """Raised when an operation is attempted on an already-concluded battle."""

    def __init__(self, user_message: str = "This battle has already concluded.") -> None:
        super().__init__(user_message)


class RoundNotOpenError(BattleError):
    """Raised when a declaration is attempted outside a DECLARING round."""

    def __init__(self, user_message: str = "There is no open round for declarations.") -> None:
        super().__init__(user_message)


class NotAParticipantError(BattleError):
    """Raised when a character is not enlisted in the battle."""

    def __init__(self, user_message: str = "You are not a participant in this battle.") -> None:
        super().__init__(user_message)
