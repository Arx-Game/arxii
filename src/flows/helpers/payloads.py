"""Helpers for serializing flow state objects."""

from __future__ import annotations

from typing import Any

from flows.object_states.base_state import BaseState
from flows.object_states.exit_state import ExitState


def serialize_state(
    state: BaseState,
    looker: BaseState | None = None,
) -> dict[str, Any]:
    """Return a minimal serialization of ``state``.

    Args:
        state: State to serialize.
        looker: Optional state used to resolve display names and available
            commands.

    Returns:
        Dict with dbref, name, thumbnail URL, and matching command keys.
    """
    command_keys = _collect_command_keys(looker)
    return {
        "dbref": state.obj.dbref,
        "name": state.get_display_name(looker=looker),
        "thumbnail_url": state.thumbnail_url,
        "commands": [key for key in command_keys if key in state.dispatcher_tags],
    }


def _collect_command_keys(caller: BaseState | None) -> list[str]:
    """Return command keys available to ``caller``.

    Args:
        caller: State whose commandset should be inspected.

    Returns:
        List of available command keys or an empty list if unavailable.
    """
    if caller is None:
        return []
    try:
        cmdset = caller.obj.cmdset.current
    except AttributeError:
        return []
    if not cmdset:
        return []
    return [cmd.key for cmd in cmdset.commands]


def build_room_state_payload(caller: BaseState, room: BaseState) -> dict[str, Any]:
    """Serialize room and object state for ``caller``.

    Args:
        caller: State of the requesting character.
        room: Room state to describe.

    Returns:
        Structured payload describing the room, present objects, exits, and active
        scene.
    """
    room_data = serialize_state(room, looker=caller)

    objects: list[dict[str, Any]] = []
    exits: list[dict[str, Any]] = []
    for obj in room.contents:
        if obj is None or obj is caller:
            continue
        serialized = serialize_state(obj, looker=caller)
        if isinstance(obj, ExitState):
            exits.append(serialized)
        else:
            objects.append(serialized)

    active_scene = room.active_scene
    scene_data: dict[str, Any] | None = None
    if active_scene:
        is_owner = active_scene.is_owner(caller.account)
        scene_data = {
            "id": active_scene.id,
            "name": active_scene.name,
            "description": active_scene.description,
            "is_owner": is_owner,
        }

    return {"room": room_data, "objects": objects, "exits": exits, "scene": scene_data}
