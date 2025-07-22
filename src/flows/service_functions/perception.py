"""Service functions related to perceiving objects."""

from __future__ import annotations

from typing import Any

from flows.object_states.base_state import BaseState


def get_formatted_description(
    flow_execution: Any,
    obj: Any | None = None,
    **kwargs: Any,
) -> str:
    """Return a formatted description for ``obj`` using ContextData.

    This helper resolves ``obj`` from flow variables and then looks up the
    appropriate state object from ``flow_execution.context``. The state's
    template and categories determine how the final string is produced.
    Contained objects are summarized by name according to their own states.

    Parameters
    ----------
    flow_execution:
        The current :class:`~flows.flow_execution.FlowExecution`.
    obj:
        The target to describe. May be a flow variable reference, an Evennia
        object, a primary key, or an existing state object.
    **kwargs:
        Additional keyword arguments passed to the state's appearance helpers.
    """

    # Resolve flow variable references like "$target".
    resolved = flow_execution.resolve_flow_reference(obj)

    state: BaseState | None = None
    if isinstance(resolved, BaseState):
        state = resolved
    elif hasattr(resolved, "pk"):
        state = flow_execution.context.get_state_by_pk(resolved.pk)
    elif resolved is not None:
        # Attempt to treat ``resolved`` as a primary key.
        state = flow_execution.context.get_state_by_pk(resolved)

    if state is None:
        return str(resolved)

    return state.return_appearance(**kwargs)
