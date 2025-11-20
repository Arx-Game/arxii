from commands.exceptions import CommandError


class StopEvent(CommandError):
    pass


class StopBranch(Exception):
    """
    Raised by a step to stop executing any further siblings under the
    same parent, but continue the rest of the flow.
    """


class StopFlow(Exception):
    """
    Raised by a step to end the flow normally (early exit).
    Carries an optional message.
    """

    def __init__(self, message: str | None = None):
        super().__init__(message)
        self.message = message


class CancelFlow(Exception):
    """
    Raised by a step to abort the flow as an error.
    Carries an error message.
    """

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message
