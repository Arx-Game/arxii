"""Type definitions for player channels (#3299)."""

_CHANNEL_ERROR_MESSAGES: dict[str, str] = {
    "NO_ACCESS": "You don't have access to that channel.",
    "NOT_SUBSCRIBED": "Join the channel first.",
    "BANNED": "You are banned from that channel.",
    "NO_IDENTITY": "Choose who you speak as in this channel first.",
    "INELIGIBLE_IDENTITY": "That character can't speak in this channel.",
    "EMPTY": "Say something.",
    "TOO_LONG": "That message is too long.",
    "NOT_STAFF": "Only staff can do that.",
    "NO_SUCH_CHANNEL": "No such channel.",
}


class ChannelError(Exception):
    """User-safe validation error from channel operations.

    Always raised with one of the class-level message constants. Use
    ``exc.user_message`` in API/Action responses instead of ``str(exc)``.
    """

    NO_ACCESS = _CHANNEL_ERROR_MESSAGES["NO_ACCESS"]
    NOT_SUBSCRIBED = _CHANNEL_ERROR_MESSAGES["NOT_SUBSCRIBED"]
    BANNED = _CHANNEL_ERROR_MESSAGES["BANNED"]
    NO_IDENTITY = _CHANNEL_ERROR_MESSAGES["NO_IDENTITY"]
    INELIGIBLE_IDENTITY = _CHANNEL_ERROR_MESSAGES["INELIGIBLE_IDENTITY"]
    EMPTY = _CHANNEL_ERROR_MESSAGES["EMPTY"]
    TOO_LONG = _CHANNEL_ERROR_MESSAGES["TOO_LONG"]
    NOT_STAFF = _CHANNEL_ERROR_MESSAGES["NOT_STAFF"]
    NO_SUCH_CHANNEL = _CHANNEL_ERROR_MESSAGES["NO_SUCH_CHANNEL"]

    @property
    def user_message(self) -> str:
        msg = self.args[0] if self.args else ""
        if msg in _CHANNEL_ERROR_MESSAGES.values():
            return msg
        return "An unexpected channel error occurred."
