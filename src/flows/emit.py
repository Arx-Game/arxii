"""Event emission entry point for the reactive layer.

Creates fresh FlowStacks for each PERSONAL dispatch (AE topology),
a single FlowStack for ROOM dispatch. When a parent_stack is given
(nested emission from within a flow), reuse it so recursion cap is
enforced on the originating chain.

Dispatch order (Task 24): ROOM first, then PERSONAL.
Room-scoped triggers (wards, environmental effects) get first shot at
cancellation; if the shared stack is marked cancelled after ROOM
dispatch, PERSONAL dispatch is skipped entirely.
"""

from typing import Any

from flows.flow_stack import FlowStack


def _dispatch(
    target: Any,
    event_name: str,
    payload: Any,
    *,
    parent_stack: FlowStack | None,
) -> FlowStack:
    """Dispatch *event_name* to *target*'s trigger_handler.

    If *parent_stack* is provided the dispatch runs inside a nested()
    context on that stack (enforcing the recursion cap). Otherwise a
    fresh FlowStack is created for *target*.

    Returns the stack that was used.
    """
    if parent_stack is not None:
        with parent_stack.nested():
            target.trigger_handler.dispatch(event_name, payload, flow_stack=parent_stack)
        return parent_stack
    stack = FlowStack(owner=target, originating_event=event_name)
    target.trigger_handler.dispatch(event_name, payload, flow_stack=stack)
    return stack


def emit_event(
    event_name: str,
    payload: Any,
    *,
    personal_target: Any = None,
    room: Any = None,
    parent_stack: FlowStack | None = None,
) -> FlowStack | None:
    """Dispatch event to ROOM and/or PERSONAL handlers.

    ROOM dispatches first so that environmental/ward triggers can veto
    the event before personal handlers run. If the ROOM stack is
    cancelled after dispatch, PERSONAL dispatch is skipped.

    Returns the stack used for the last dispatch that actually ran
    (PERSONAL if it ran, ROOM if PERSONAL was skipped, None if neither
    scope was supplied).

    When *parent_stack* is given (nested emission from within a flow)
    both scopes reuse it so the recursion cap is enforced on the
    originating chain.
    """
    result_stack: FlowStack | None = None

    # --- ROOM FIRST ---
    if room is not None:
        stack = _dispatch(room, event_name, payload, parent_stack=parent_stack)
        result_stack = stack
        if stack.was_cancelled():
            return stack

    # --- PERSONAL SECOND (skipped if ROOM cancelled) ---
    if personal_target is not None:
        stack = _dispatch(personal_target, event_name, payload, parent_stack=parent_stack)
        result_stack = stack

    return result_stack
