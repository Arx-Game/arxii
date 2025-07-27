"""Service functions related to perceiving objects."""

from flows.flow_execution import FlowExecution


def get_formatted_description(
    flow_execution: FlowExecution,
    obj: str | None = None,
    mode: str = "look",
    **kwargs: object,
) -> str:
    """Return a formatted description for ``obj``.

    Args:
        flow_execution: Current FlowExecution.
        obj: Name of a flow variable containing the target object.
        mode: Display mode passed to :meth:`BaseState.return_appearance`.
        **kwargs: Extra keyword arguments for appearance helpers.

    Returns:
        The formatted description.

    Example:
        ````python
        FlowStepDefinition(
            action=FlowActionChoices.CALL_SERVICE_FUNCTION,
            variable_name="get_formatted_description",
            parameters={
                "obj": "@target",
                "mode": "@mode",
                "result_variable": "desc",
            },
        )
        ````
    """

    # Resolve flow variable references like "@target".
    state = flow_execution.get_object_state(obj)
    if state is None:
        resolved = flow_execution.resolve_flow_reference(obj)
        return str(resolved)

    return state.return_appearance(mode=mode, **kwargs)


def object_has_tag(
    flow_execution: FlowExecution, obj: str, tag: str, **kwargs: object
) -> bool:
    """Return True if `obj` has `tag`.

    Args:
        flow_execution: Current FlowExecution.
        obj: Name of a flow variable referencing the target object.
        tag: Tag name to check for.

    Returns:
        bool: True if the tag exists.

    Example:
        ````python
        FlowStepDefinition(
            action=FlowActionChoices.CALL_SERVICE_FUNCTION,
            variable_name="object_has_tag",
            parameters={"obj": "@target", "tag": "evil", "result_variable": "is_evil"},
        )
        ````
    """

    state = flow_execution.get_object_state(obj)
    target = state.obj if state else flow_execution.resolve_flow_reference(obj)

    try:
        return bool(target.tags.get(tag))
    except AttributeError:
        return False


def append_to_attribute(
    flow_execution: FlowExecution,
    obj: str,
    attribute: str,
    append_text: str,
    **kwargs: object,
) -> None:
    """Append text to an attribute on the state for `obj`.

    Args:
        flow_execution: Current FlowExecution.
        obj: Name of the flow variable referencing the target object.
        attribute: Name of the attribute.
        append_text: Text to append.
        **kwargs: Additional keyword arguments.

    Example:
        ````python
        FlowStepDefinition(
            action=FlowActionChoices.CALL_SERVICE_FUNCTION,
            variable_name="append_to_attribute",
            parameters={
                "obj": "@target",
                "attribute": "name",
                "append_text": " (Evil)",
            },
        )
        ````
    """

    state = flow_execution.get_object_state(obj)

    if state:
        current = getattr(state, attribute, "")
        setattr(state, attribute, f"{current}{append_text}")


def show_inventory(
    flow_execution: FlowExecution, caller: str, **kwargs: object
) -> None:
    """Send the caller a list of carried items."""

    caller_state = flow_execution.get_object_state(caller)
    if caller_state is None:
        return

    items = caller_state.contents
    if not items:
        caller_state.msg("You are not carrying anything.")
        return

    names = [it.get_display_name(looker=caller_state) for it in items]
    text = "You are carrying: " + ", ".join(names)
    caller_state.msg(text)
