"""Type declarations for flows system."""

from typing import TypedDict


class SerializedObjectState(TypedDict):
    dbref: str
    name: str
    thumbnail_url: str | None
    commands: list[str]


class SceneInfo(TypedDict):
    id: int
    name: str
    description: str
    is_owner: bool


class SimpleRoomPayload(TypedDict):
    room: SerializedObjectState
    objects: list[SerializedObjectState]
    exits: list[SerializedObjectState]
    scene: SceneInfo | None


class RealmInfo(TypedDict):
    id: int
    name: str
    theme: str


class MessageParticipant(TypedDict):
    name: str
    dbref: str


class MessageContent(TypedDict):
    template: str
    variables: dict[str, str]
    rendered: str
