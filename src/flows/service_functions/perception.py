"""Service functions related to perceiving objects."""

from __future__ import annotations

from typing import Any


def get_formatted_description(
    flow_execution: Any, obj: Any | None = None, **kwargs: Any
) -> str:
    """Return a placeholder formatted description for ``obj``.

    Parameters
    ----------
    flow_execution:
        The current :class:`~flows.flow_execution.FlowExecution`.
    obj:
        The object to describe.
    **kwargs:
        Additional keyword arguments ignored for now.
    """
    return f"Formatted description for {obj}"
