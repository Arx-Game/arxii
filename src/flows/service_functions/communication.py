"""Communication-related service functions."""

from evennia.utils import funcparser

from flows.flow_execution import FlowExecution
from flows.helpers.payloads import build_room_state_payload
from flows.object_states.base_state import BaseState

_PARSER = funcparser.FuncParser(funcparser.ACTOR_STANCE_CALLABLES)


def send_message(
    flow_execution: FlowExecution,
    recipient: str,
    text: str,
    mapping: dict[str, object] | None = None,
    **kwargs: object,
) -> None:
    """Send text to ``recipient``.

    Args:
        flow_execution: Current FlowExecution.
        recipient: Name of the variable holding the target object.
        text: Message text. If it begins with ``@`` the corresponding
            variable value is sent instead.
        mapping: Optional mapping of additional variables to include in the
            payload.
        **kwargs: Additional keyword arguments.

    Example:
        ````python
        FlowStepDefinition(
            action=FlowActionChoices.CALL_SERVICE_FUNCTION,
            variable_name="send_message",
            parameters={"recipient": "@viewer", "text": "@desc"},
        )
        ````
    """
    target_state = flow_execution.get_object_state(recipient)
    message = str(flow_execution.resolve_flow_reference(text))

    resolved_mapping: dict[str, object] = {}
    if mapping:
        for key, ref in mapping.items():
            state = flow_execution.get_object_state(ref)
            if state is not None:
                resolved_mapping[key] = state
            else:
                resolved_mapping[key] = flow_execution.resolve_flow_reference(ref)

    caller_state = None
    if "caller" in flow_execution.variable_mapping:
        caller_state = flow_execution.get_object_state("@caller")
        if caller_state is not None:
            resolved_mapping.setdefault("caller", caller_state)

    target_state_obj = None
    if "target" in flow_execution.variable_mapping:
        target_state_obj = flow_execution.get_object_state("@target")
        if target_state_obj is not None:
            resolved_mapping.setdefault("target", target_state_obj)

    receiver = target_state or flow_execution.resolve_flow_reference(recipient)
    caller_state = resolved_mapping.get("caller")
    parsed = _PARSER.parse(
        message,
        caller=caller_state,
        receiver=receiver,
        mapping=resolved_mapping,
        return_string=True,
    )
    parsed = parsed.format_map(
        {
            key: (
                obj.get_display_name(looker=receiver)
                if isinstance(obj, BaseState)
                else str(obj)
            )
            for key, obj in resolved_mapping.items()
        }
    )
    if target_state is None:
        from web import message_dispatcher

        message_dispatcher.send(receiver, parsed, **kwargs)
    else:
        target_state.msg(parsed, **kwargs)


def message_location(
    flow_execution: FlowExecution,
    caller: str,
    text: str,
    target: str | None = None,
    mapping: dict[str, object] | None = None,
    **kwargs: object,
) -> None:
    """Broadcast ``text`` in the caller's location using ``msg_contents``.

    Args:
        flow_execution: Current execution context.
        caller: Flow variable for the caller.
        text: Message template with optional ``{key}`` markers.
        target: Optional secondary actor variable.
        mapping: Additional mapping keys for formatting.
        **kwargs: Extra options passed to ``msg_contents``.

    The caller's current location receives the message. ``mapping`` values may
    include flow references or objects; those matching the recipient resolve to
    "you" when displayed.

    Example:
        ````python
        FlowStepDefinition(
            action=FlowActionChoices.CALL_SERVICE_FUNCTION,
            variable_name="message_location",
            parameters={
                "caller": "@caller",
                "target": "@target",
                "text": "$You() $conj(greet) $you(target).",
                "mapping": {"weapon": "@weapon", "spell": "@spell"},
            },
        )
        ````
    """

    caller_state = flow_execution.get_object_state(caller)
    if caller_state is None or caller_state.obj.location is None:
        return

    location = caller_state.obj.location
    location_state = flow_execution.context.get_state_by_pk(location.pk)

    target_state = flow_execution.get_object_state(target) if target else None

    mapping = mapping or {}

    resolved_mapping: dict[str, object] = {
        "caller": caller_state,
        "location": location_state,
    }
    if target_state:
        resolved_mapping["target"] = target_state

    for key, ref in mapping.items():
        state = flow_execution.get_object_state(ref)
        if state is not None:
            resolved_mapping[key] = state
        else:
            resolved_mapping[key] = flow_execution.resolve_flow_reference(ref)

    text = str(flow_execution.resolve_flow_reference(text))
    location.msg_contents(
        text,
        from_obj=caller_state.obj,
        mapping=resolved_mapping,
        **kwargs,
    )


def send_room_state(
    flow_execution: FlowExecution,
    caller: str,
    room: str,
    **kwargs: object,
) -> None:
    """Send serialized ``room`` state to ``caller``.

    Args:
        flow_execution: Current FlowExecution.
        caller: Flow variable referencing the recipient.
        room: Flow variable referencing the room to describe.
        **kwargs: Additional keyword arguments.
    """
    caller_state = flow_execution.get_object_state(caller)
    room_state = flow_execution.get_object_state(room)
    if caller_state is None or room_state is None:
        return
    payload = build_room_state_payload(caller_state, room_state)
    from web import message_dispatcher

    message_dispatcher.send(
        caller_state.obj,
        payload=payload,
        payload_key="room_state",
    )


hooks = {
    "send_message": send_message,
    "message_location": message_location,
    "send_room_state": send_room_state,
}
