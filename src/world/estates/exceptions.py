"""Typed estate exceptions — ``user_message`` is the only player-safe surface."""


class EstateError(Exception):
    """Base for estate failures."""

    user_message = "Something went wrong settling the estate."

    def __init__(self, user_message: str | None = None) -> None:
        if user_message is not None:
            self.user_message = user_message
        super().__init__(self.user_message)


class WillFrozenError(EstateError):
    """The will can no longer be edited — a settlement window is open."""

    user_message = "That will is sealed; its author's estate is being settled."


class NotAnExecutorError(EstateError):
    """Actor's persona is not tagged as an executor of the target's will."""

    user_message = "You are not named as an executor of that will."


class SettlementNotPendingError(EstateError):
    """The estate has already been settled (or is parked for staff)."""

    user_message = "That estate has already been settled."


class NoSettlementError(EstateError):
    """The target has no open estate settlement."""

    user_message = "There is no estate to settle for that character."


class EscheatUnresolvableError(EstateError):
    """No escheat organization could be resolved; settlement parks for staff."""

    user_message = "The estate could not be resolved and awaits staff attention."
