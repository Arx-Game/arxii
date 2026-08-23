"""Typed exceptions for tavern games. Views/actions surface user_message, never str(exc)."""

from __future__ import annotations


class TavernGameError(Exception):
    """Base for tavern game service failures."""

    user_message = "That tavern game move could not be made."

    def __init__(self) -> None:
        super().__init__(self.user_message)


class NotAtPlaceError(TavernGameError):
    user_message = "You need to be at that place to do that."


class NotASocialHubError(TavernGameError):
    user_message = "There is no room here for a coin game - this isn't a social hub."


class GameNotActiveError(TavernGameError):
    user_message = "That game isn't offered right now."


class AnteOutOfRangeError(TavernGameError):
    user_message = "That ante is outside the game's allowed range."


class SessionNotOpenError(TavernGameError):
    user_message = "That table isn't open for play."


class AlreadySeatedError(TavernGameError):
    user_message = "You're already seated at that table."


class NotSeatedError(TavernGameError):
    user_message = "You aren't seated at that table."


class AlreadyRolledError(TavernGameError):
    user_message = "You've already rolled this hand."


class NotEnoughSeatsError(TavernGameError):
    user_message = "You need another player at the table before you can roll."


class LossCapExceededError(TavernGameError):
    user_message = "That ante would push you past your weekly loss cap for the week."
