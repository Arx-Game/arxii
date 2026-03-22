"""Communication-related service functions."""

from evennia.utils import funcparser

from flows.object_states.base_state import BaseState
from flows.scene_data_manager import SceneDataManager
from flows.service_functions.serializers.room_state import build_room_state_payload

_PARSER = funcparser.FuncParser(funcparser.ACTOR_STANCE_CALLABLES)


def send_message(
    recipient: BaseState,
    text: str,
    caller: BaseState | None = None,
    target: BaseState | None = None,
    mapping: dict[str, object] | None = None,
) -> None:
    """Send text to ``recipient``.

    Args:
        recipient: The target state to receive the message.
        text: Message text.
        caller: Optional caller state for pronoun resolution.
        target: Optional target state for pronoun resolution.
        mapping: Optional mapping of additional variables to include in the
            payload. Values should be BaseState instances or plain values.
    """
    resolved_mapping: dict[str, object] = {}
    if mapping:
        resolved_mapping.update(mapping)

    if caller is not None:
        resolved_mapping.setdefault("caller", caller)
    if target is not None:
        resolved_mapping.setdefault("target", target)

    parsed = _PARSER.parse(
        text,
        caller=caller,
        receiver=recipient,
        mapping=resolved_mapping,
        return_string=True,
    )
    parsed = parsed.format_map(
        {
            key: (
                obj.get_display_name(looker=recipient) if isinstance(obj, BaseState) else str(obj)
            )
            for key, obj in resolved_mapping.items()
        },
    )
    recipient.msg(parsed)


def message_location(
    caller: BaseState,
    text: str,
    target: BaseState | None = None,
    mapping: dict[str, object] | None = None,
    location_state: BaseState | None = None,
) -> None:
    """Broadcast text in the caller's location. Pure real-time delivery.

    Does NOT persist anything to the database. Call record_interaction()
    separately for persistence.

    Args:
        caller: The message sender state.
        text: Message template with optional ``{key}`` markers.
        target: Optional secondary actor state for pronoun resolution.
        mapping: Additional mapping keys for formatting. Values should be
            BaseState instances or plain values.
        location_state: Optional pre-resolved location state. If not provided,
            the caller's location is looked up via SceneDataManager.
    """
    if caller.obj.location is None:
        return

    location = caller.obj.location

    if location_state is None:
        sdm = SceneDataManager()
        location_state = sdm.initialize_state_for_object(location)

    resolved_mapping: dict[str, object] = {
        "caller": caller,
        "location": location_state,
    }
    if target:
        resolved_mapping["target"] = target

    if mapping:
        resolved_mapping.update(mapping)

    location.msg_contents(
        text,
        from_obj=caller.obj,
        mapping=resolved_mapping,
    )


def send_room_state(
    caller: BaseState,
    room_state: BaseState | None = None,
) -> None:
    """Send serialized room state to ``caller``.

    Args:
        caller: The recipient state.
        room_state: Optional pre-resolved room state. If not provided,
            the caller's location is looked up via SceneDataManager.
    """
    if caller.obj.location is None:
        return

    if room_state is None:
        room = caller.obj.location
        sdm = SceneDataManager()
        room_state = sdm.initialize_state_for_object(room)

    if room_state is None:
        return

    payload = build_room_state_payload(caller, room_state)
    caller.obj.msg(room_state=((), payload))


hooks = {
    "send_message": send_message,
    "message_location": message_location,
    "send_room_state": send_room_state,
}
