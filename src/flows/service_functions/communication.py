"""Communication-related service functions."""

from typing import Union

from flows.flow_execution import FlowExecution
from flows.object_states.base_state import BaseState
from typeclasses.objects import Object

ObjRef = Union[BaseState, Object, int, str]


def send_message(
    flow_execution: FlowExecution, recipient: ObjRef, text: str, **kwargs: object
) -> None:
    """Send text to a recipient if it has a `msg` method.

    Both `recipient` and `text` may reference flow variables (for example
    "$target"). The function resolves them before sending.
    """
    target = flow_execution.resolve_flow_reference(recipient)
    message = flow_execution.resolve_flow_reference(text)
    if hasattr(target, "msg"):
        target.msg(message)
