"""GM prompt queue exceptions (#4101). ``user_message`` is safe to show the GM."""


class GMPromptError(Exception):
    """A prompt cannot be narrated, dismissed or confirmed as asked."""

    def __init__(self, msg: str) -> None:
        super().__init__(msg)
        self.user_message = msg
