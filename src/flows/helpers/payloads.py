"""Helpers for serializing flow state objects."""

from __future__ import annotations

from typing import Any, Dict, List

from flows.object_states.base_state import BaseState


def serialize_state(
    state: BaseState, looker: BaseState | None = None
) -> Dict[str, Any]:
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


def _collect_command_keys(caller: BaseState | None) -> List[str]:
    """Return command keys available to ``caller``.

    Args:
        caller: State whose commandset should be inspected.

    Returns:
        List of available command keys or an empty list if unavailable.
    """
    if caller is None:
        return []
    try:
        cmdset = caller.obj.cmdset.current  # type: ignore[attr-defined]
    except AttributeError:
        return []
    if not cmdset:
        return []
    return [cmd.key for cmd in cmdset.commands]


def build_room_state_payload(caller: BaseState, room: BaseState) -> Dict[str, Any]:
    """Serialize room and object state for ``caller``.

    Args:
        caller: State of the requesting character.
        room: Room state to describe.

    Returns:
        Structured payload describing the room and present objects.
    """
    room_data = serialize_state(room, looker=caller)

    objects: List[Dict[str, Any]] = []
    for obj in room.contents:
        if obj is caller:
            continue
        objects.append(serialize_state(obj, looker=caller))

    active_scene = room.active_scene
    scene_data: Dict[str, Any] | None = None
    if active_scene:
        is_owner = active_scene.is_owner(caller.account)
        scene_data = {
            "id": active_scene.id,
            "name": active_scene.name,
            "description": active_scene.description,
            "is_owner": is_owner,
        }

    return {"room": room_data, "objects": objects, "scene": scene_data}
