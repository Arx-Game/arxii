"""Type definitions for the game clock system."""


class ClockError(Exception):
    """User-safe error from clock operations."""

    NOT_CONFIGURED = "Game clock is not configured."
    ALREADY_PAUSED = "Game clock is already paused."
    NOT_PAUSED = "Game clock is not paused."
    INVALID_RATIO = "Time ratio must be positive."
    CONVERSION_UNAVAILABLE = "Cannot convert IC-to-real while clock is paused or has zero ratio."
