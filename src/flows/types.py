"""Type declarations for flows system."""

from dataclasses import dataclass
from typing import NotRequired, TypedDict


@dataclass(frozen=True)
class RoomStateSendResult:
    """Result metadata for a viewer-bound room-state send."""

    sent: bool
    code: str | None = None
    room_dbref: str | None = None
    room_id: int | None = None
    scene_id: int | None = None
    state_epoch: str | None = None
    state_sequence: int | None = None


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
    state_epoch: NotRequired[str]
    state_sequence: NotRequired[int]
    resync_request_id: NotRequired[str]
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
