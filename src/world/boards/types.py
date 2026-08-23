"""Type definitions for the boards system (#3286)."""

_BOARD_ERROR_MESSAGES: dict[str, str] = {
    "NOT_PRESENT": "You must be at the board to do that.",
    "NOT_AUTHORIZED_TO_POST": "You don't have posting rights on this board.",
    "NOT_AUTHORIZED_TO_REMOVE": "You can't remove that post.",
    "NOT_AUTHOR": "You can only edit your own notices.",
    "ALREADY_REMOVED": "That post has already been removed.",
    "NO_BOARD": "There is no board here.",
}


class BoardError(Exception):
    """User-safe validation error from board operations.

    Always raised with one of the class-level message constants. Use
    ``exc.user_message`` in API/Action responses instead of ``str(exc)`` to
    avoid CodeQL "information exposure through exception" warnings.
    """

    NOT_PRESENT = _BOARD_ERROR_MESSAGES["NOT_PRESENT"]
    NOT_AUTHORIZED_TO_POST = _BOARD_ERROR_MESSAGES["NOT_AUTHORIZED_TO_POST"]
    NOT_AUTHORIZED_TO_REMOVE = _BOARD_ERROR_MESSAGES["NOT_AUTHORIZED_TO_REMOVE"]
    NOT_AUTHOR = _BOARD_ERROR_MESSAGES["NOT_AUTHOR"]
    ALREADY_REMOVED = _BOARD_ERROR_MESSAGES["ALREADY_REMOVED"]
    NO_BOARD = _BOARD_ERROR_MESSAGES["NO_BOARD"]

    @property
    def user_message(self) -> str:
        msg = self.args[0] if self.args else ""
        if msg in _BOARD_ERROR_MESSAGES.values():
            return msg
        return "An unexpected board error occurred."
