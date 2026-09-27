"""Helpers for serializing flow state objects."""

from __future__ import annotations

from flows.object_states.base_state import BaseState
from flows.object_states.exit_state import ExitState
from flows.types import SceneInfo, SerializedObjectState, SimpleRoomPayload


def serialize_state(
    state: BaseState,
    looker: BaseState | None = None,
) -> SerializedObjectState:
    """Return a minimal serialization of ``state``.

    Args:
        state: State to serialize.
        looker: Optional state used to resolve display names.

    Returns:
        Dict with dbref, name, thumbnail URL.
    """
    return {
        "dbref": state.obj.dbref,
        "name": state.get_display_name(looker=looker),
        "thumbnail_url": state.thumbnail_url,
    }


def build_room_state_payload(caller: BaseState, room: BaseState) -> SimpleRoomPayload:
    """Serialize room and object state for ``caller``.

    Args:
        caller: State of the requesting character.
        room: Room state to describe.

    Returns:
        Structured payload describing the room, present objects, exits, and active
        scene.
    """
    room_data = serialize_state(room, looker=caller)

    objects: list[SerializedObjectState] = []
    exits: list[SerializedObjectState] = []
    for obj in room.contents:
        if obj is None or obj is caller:
            continue
        serialized = serialize_state(obj, looker=caller)
        if isinstance(obj, ExitState):
            exits.append(serialized)
        else:
            objects.append(serialized)

    active_scene = room.active_scene
    scene_data: SceneInfo | None = None
    if active_scene:
        is_owner = active_scene.is_owner(caller.account)
        scene_data = SceneInfo(
            id=active_scene.id,
            name=active_scene.name,
            description=active_scene.description,
            is_owner=is_owner,
        )

    return {"room": room_data, "objects": objects, "exits": exits, "scene": scene_data}
