"""Communication-related service functions."""

from flows.flow_execution import FlowExecution


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
        text: Message text or variable reference.
        **kwargs: Additional keyword arguments.

    Example:
        ````python
        FlowStepDefinition(
            action=FlowActionChoices.CALL_SERVICE_FUNCTION,
            variable_name="send_message",
            parameters={"recipient": "$viewer", "text": "$desc"},
        )
        ````
    """
    target_state = flow_execution.get_object_state(recipient)
    message = flow_execution.resolve_flow_reference(text)

    if target_state is None:
        target = flow_execution.resolve_flow_reference(recipient)
        try:
            target.msg(message)
        except AttributeError:
            pass
        return

    target_state.msg(message)
