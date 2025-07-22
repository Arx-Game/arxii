"""Service functions related to perceiving objects."""

from __future__ import annotations

from typing import Union

from flows.flow_execution import FlowExecution
from flows.object_states.base_state import BaseState
from typeclasses.objects import Object

ObjRef = Union[BaseState, Object, int, str, None]


def get_formatted_description(
    flow_execution: FlowExecution,
    obj: ObjRef = None,
    **kwargs: object,
) -> str:
    """Return a formatted description for `obj` using ContextData.

    Args:
        flow_execution: Current FlowExecution.
        obj: Target to describe. May be a flow variable, Evennia object,
            primary key or BaseState.
        **kwargs: Extra keyword arguments for appearance helpers.

    Returns:
        The formatted description.
    """

    # Resolve flow variable references like "$target".
    resolved = flow_execution.resolve_flow_reference(obj)

    state: BaseState | None = None
    if isinstance(resolved, BaseState):
        state = resolved
    elif hasattr(resolved, "pk"):
        state = flow_execution.context.get_state_by_pk(resolved.pk)
    elif resolved is not None:
        # Attempt to treat `resolved` as a primary key.
        state = flow_execution.context.get_state_by_pk(resolved)

    if state is None:
        return str(resolved)

    return state.return_appearance(**kwargs)


def send_formatted_description(
    flow_execution: FlowExecution,
    looker: ObjRef,
    text: str,
    **kwargs: object,
) -> None:
    """Send formatted text to `looker`.

    Args:
        flow_execution: Current FlowExecution.
        looker: Recipient of the text. May be a variable reference.
        text: Preformatted text to send.
        **kwargs: Additional keyword arguments.
    """

    target = flow_execution.resolve_flow_reference(looker)
    message = flow_execution.resolve_flow_reference(text)
    if hasattr(target, "msg"):
        target.msg(message)


def object_has_tag(
    flow_execution: FlowExecution, obj: ObjRef, tag: str, **kwargs: object
) -> bool:
    """Return True if `obj` has `tag`.

    Args:
        flow_execution: Current FlowExecution.
        obj: Flow variable, state object, Evennia object or primary key.
        tag: Tag name to check for.

    Returns:
        bool: True if the tag exists.
    """

    resolved = flow_execution.resolve_flow_reference(obj)

    state: BaseState | None = None
    if isinstance(resolved, BaseState):
        state = resolved
    elif hasattr(resolved, "pk"):
        state = flow_execution.context.get_state_by_pk(resolved.pk)
    elif resolved is not None:
        state = flow_execution.context.get_state_by_pk(resolved)

    if state and hasattr(state.obj, "tags"):
        return bool(state.obj.tags.get(tag))

    if hasattr(resolved, "tags"):
        return bool(resolved.tags.get(tag))

    return False


def append_to_attribute(
    flow_execution: FlowExecution,
    obj: ObjRef,
    attribute: str,
    append_text: str,
    **kwargs: object,
) -> None:
    """Append text to an attribute on the state for `obj`.

    Args:
        flow_execution: Current FlowExecution.
        obj: Target object or reference.
        attribute: Name of the attribute.
        append_text: Text to append.
        **kwargs: Additional keyword arguments.
    """

    resolved = flow_execution.resolve_flow_reference(obj)

    state: BaseState | None = None
    if isinstance(resolved, BaseState):
        state = resolved
    elif hasattr(resolved, "pk"):
        state = flow_execution.context.get_state_by_pk(resolved.pk)
    elif resolved is not None:
        state = flow_execution.context.get_state_by_pk(resolved)

    if state:
        current = getattr(state, attribute, "")
        setattr(state, attribute, f"{current}{append_text}")
