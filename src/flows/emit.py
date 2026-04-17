"""Event emission entry point for the reactive layer.

Creates fresh FlowStacks for each PERSONAL dispatch (AE topology),
a single FlowStack for ROOM dispatch. When a parent_stack is given
(nested emission from within a flow), reuse it so recursion cap is
enforced on the originating chain.
"""

from typing import Any

from flows.flow_stack import FlowStack


def emit_event(
    event_name: str,
    payload: Any,
    *,
    personal_target: Any = None,
    room: Any = None,
    parent_stack: FlowStack | None = None,
) -> FlowStack | None:
    """Dispatch event to PERSONAL and/or ROOM handlers.

    Returns the stack used for the last dispatch (ROOM if both supplied,
    else PERSONAL). If both scopes are requested, PERSONAL dispatches
    first, then ROOM. Callers check the returned stack's ``was_cancelled``
    to decide whether to suppress default behavior.
    """
    result_stack: FlowStack | None = None

    if personal_target is not None:
        if parent_stack is not None:
            with parent_stack.nested():
                personal_target.trigger_handler.dispatch(
                    event_name,
                    payload,
                    flow_stack=parent_stack,
                )
            result_stack = parent_stack
        else:
            stack = FlowStack(owner=personal_target, originating_event=event_name)
            personal_target.trigger_handler.dispatch(
                event_name,
                payload,
                flow_stack=stack,
            )
            result_stack = stack

    if room is not None:
        stack = parent_stack or FlowStack(owner=room, originating_event=event_name)
        room.trigger_handler.dispatch(event_name, payload, flow_stack=stack)
        result_stack = stack

    return result_stack
