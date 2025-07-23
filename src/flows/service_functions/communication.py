"""Communication-related service functions."""

from flows.flow_execution import FlowExecution
from flows.object_states.base_state import BaseState


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


def message_location(
    flow_execution: FlowExecution,
    caller: str,
    target: str | None = None,
    caller_message: str | None = None,
    target_message: str | None = None,
    bystander_message: str | None = None,
    **kwargs: object,
) -> None:
    """Send formatted messages to caller, target and bystanders.

    Args:
        flow_execution: Current execution context.
        caller: Flow variable for the caller.
        target: Optional flow variable for the target.
        caller_message: Template for the caller.
        target_message: Template for the target.
        bystander_message: Template for others in the room.
        **kwargs: Additional keyword arguments.

    Templates may use ``{caller}``, ``{target}`` and ``{location}`` which are
    resolved per recipient using ``get_display_name``.

    Example:
        ````python
        FlowStepDefinition(
            action=FlowActionChoices.CALL_SERVICE_FUNCTION,
            variable_name="message_location",
            parameters={
                "caller": "$caller",
                "target": "$target",
                "caller_message": "You poke {target}.",
                "target_message": "{caller} pokes you.",
                "bystander_message": "{caller} pokes {target}.",
            },
        )
        ````
    """

    def _resolve(ref: str | None):
        if ref is None:
            return None
        return flow_execution.get_object_state(ref)

    caller_state = _resolve(caller)
    target_state = _resolve(target)

    location_state = None
    if caller_state and caller_state.obj.location:
        location = caller_state.obj.location
        location_state = flow_execution.context.get_state_by_pk(location.pk)

    def format_text(template: str | None, looker: "BaseState") -> str | None:
        if not template:
            return None
        mapping = {
            "caller": caller_state.get_display_name(looker) if caller_state else "",
            "target": target_state.get_display_name(looker) if target_state else "",
            "location": (
                location_state.get_display_name(looker) if location_state else ""
            ),
        }
        return template.format(**mapping)

    recipients = []
    if location_state:
        recipients = [
            st
            for st in location_state.contents
            if st not in (caller_state, target_state)
        ]

    def _send(recipient_state: "BaseState | None", template: str | None) -> None:
        if recipient_state is None:
            return
        text = format_text(template, recipient_state)
        if text is None:
            return
        recipient_state.msg(text)

    _send(caller_state, caller_message)
    _send(target_state, target_message)
    if bystander_message:
        for recipient in recipients:
            _send(recipient, bystander_message)
