from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class WebsocketMessageType(str, Enum):
    """Supported websocket message types."""

    TEXT = "text"
    LOGGED_IN = "logged_in"
    VN_MESSAGE = "vn_message"
    MESSAGE_REACTION = "message_reaction"
    COMMANDS = "commands"
    ROOM_STATE = "room_state"
    SCENE = "scene"
    COMMAND_ERROR = "command_error"


@dataclass
class WebsocketMessage:
    """Message transmitted over the websocket.

    Attributes:
        type: Message type identifier.
        args: Positional message arguments.
        kwargs: Keyword payload.
    """

    type: WebsocketMessageType
    args: list[Any] = field(default_factory=list)
    kwargs: dict[str, Any] = field(default_factory=dict)


@dataclass
class VnMessagePayload:
    """Payload for ``vn_message`` messages.

    Attributes:
        text: Message content.
        speaker: Speaker metadata.
        presentation: Visual presentation options.
        interaction: Interaction metadata for the message.
        timing: Timing information for display.
    """

    text: str
    speaker: dict[str, Any]
    presentation: dict[str, Any]
    interaction: dict[str, Any]
    timing: dict[str, Any]


@dataclass
class MessageReactionPayload:
    """Payload for ``message_reaction`` messages.

    Attributes:
        message_id: Identifier of the message receiving the reaction.
        reaction: Reaction value, such as an emoji.
        actor: Metadata about the actor reacting.
        counts: Updated reaction counts.
    """

    message_id: str
    reaction: str
    actor: dict[str, Any]
    counts: dict[str, int] | None = None


@dataclass
class RoomStateObject:
    """Object within a ``room_state`` message."""

    dbref: str
    name: str
    thumbnail_url: str | None
    commands: list[str] = field(default_factory=list)
    description: str = ""


@dataclass
class RoomStatePayload:
    """Payload for ``room_state`` messages."""

    room: RoomStateObject
    characters: list[RoomStateObject] = field(default_factory=list)
    objects: list[RoomStateObject] = field(default_factory=list)
    exits: list[RoomStateObject] = field(default_factory=list)
    scene: Optional["SceneSummary"] = None


@dataclass
class SceneSummary:
    """Minimal scene information for websocket messages."""

    id: int
    name: str
    description: str
    is_owner: bool


@dataclass
class ScenePayload:
    """Payload for ``scene`` messages."""

    action: str
    scene: SceneSummary


@dataclass
class CommandErrorPayload:
    """Payload for ``command_error`` messages."""

    command: str
    error: str
