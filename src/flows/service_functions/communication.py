"""Communication-related service functions."""

from flows.flow_execution import FlowExecution


def _resolve_text(flow_execution: FlowExecution, text: str) -> str:
    """Resolve ``@`` references in ``text`` if present."""

    if text.startswith("@"):  # simple variable reference
        return str(flow_execution.resolve_flow_reference(text))
    return text


def send_message(
    flow_execution: FlowExecution,
    recipient: str,
    text: str,
    **kwargs: object,
) -> None:
    """Send text to ``recipient``.

    Args:
        flow_execution: Current FlowExecution.
        recipient: Name of the variable holding the target object.
        text: Message text. If it begins with ``@`` the corresponding
            variable value is sent instead.
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
    message = _resolve_text(flow_execution, text)

    if target_state is None:
        target = flow_execution.resolve_flow_reference(recipient)
        try:
            target.msg(message)
        except AttributeError:
            pass
        return

    target_state.msg(message)


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

    text = _resolve_text(flow_execution, text)

    location.msg_contents(
        text,
        from_obj=caller_state.obj,
        mapping=resolved_mapping,
        **kwargs,
    )
