"""Exception hierarchy for the ships system (#1832)."""

from __future__ import annotations


class ShipError(Exception):
    """Base exception for all ship-system errors.

    Attributes:
        user_message: A human-readable message safe to surface to players.
    """

    def __init__(self, user_message: str = "") -> None:
        super().__init__(user_message)
        self.user_message = user_message


class ShipNeedsRepairError(ShipError):
    """Raised when an action requires an undamaged ship but the ship needs repair."""

    def __init__(
        self, user_message: str = "This ship needs repair before it can be upgraded."
    ) -> None:
        super().__init__(user_message)


class ShipConstructionError(ShipError):
    """Raised when a ship construction attempt is invalid."""

    def __init__(self, user_message: str = "This ship cannot be constructed.") -> None:
        super().__init__(user_message)


class ShipOwnershipError(ShipError):
    """Raised when an actor attempts an action on a ship they don't own/command."""

    def __init__(self, user_message: str = "You do not own or command this ship.") -> None:
        super().__init__(user_message)


class ShipUpgradeError(ShipError):
    """Raised when a ship-upgrade request names an invalid stat or a
    non-increasing ``target_level``."""

    def __init__(self, user_message: str = "That upgrade is not valid.") -> None:
        super().__init__(user_message)
