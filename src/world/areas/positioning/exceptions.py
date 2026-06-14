class PositionError(Exception):
    """Base error for positioning operations, carrying a user-facing message."""

    def __init__(self, user_message: str) -> None:
        self.user_message = user_message
        super().__init__(user_message)


class PositionTransitionError(PositionError):
    """Raised when a voluntary move between positions is not permitted."""
