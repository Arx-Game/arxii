"""Type declarations for flows system."""

from typing import NotRequired, TypedDict


class SerializedObjectState(TypedDict):
    dbref: str
    name: str
    thumbnail_url: str | None
    commands: list[str]
    # Populated by `ObjectStateSerializer.to_representation`; the older,
    # minimal `flows.helpers.payloads.serialize_state` path (test-only) does
    # not set either, so both stay optional here rather than forcing that
    # path to fabricate values it has no batched lookup for.
    is_mission_board: NotRequired[bool]
    place_id: NotRequired[int | None]


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
