from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class WebsocketMessageType(str, Enum):
    """Supported websocket message types."""

    TEXT = "text"
    LOGGED_IN = "logged_in"
    VN_MESSAGE = "vn_message"
    MESSAGE_REACTION = "message_reaction"
    COMMANDS = "commands"
    ROOM_STATE = "room_state"


@dataclass
class WebsocketMessage:
    """Message transmitted over the websocket.

    Attributes:
        type: Message type identifier.
        args: Positional message arguments.
        kwargs: Keyword payload.
    """

    type: WebsocketMessageType
    args: List[Any] = field(default_factory=list)
    kwargs: Dict[str, Any] = field(default_factory=dict)


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
    speaker: Dict[str, Any]
    presentation: Dict[str, Any]
    interaction: Dict[str, Any]
    timing: Dict[str, Any]


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
    actor: Dict[str, Any]
    counts: Optional[Dict[str, int]] = None


@dataclass
class RoomStateObject:
    """Object within a ``room_state`` message."""

    dbref: str
    name: str
    thumbnail_url: Optional[str]
    commands: List[str] = field(default_factory=list)


@dataclass
class RoomStatePayload:
    """Payload for ``room_state`` messages."""

    room: RoomStateObject
    objects: List[RoomStateObject]
