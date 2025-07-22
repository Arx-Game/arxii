"""Communication-related service functions."""

from typing import Any


def send_message(flow_execution: Any, recipient: Any, text: Any, **kwargs: Any) -> None:
    """Send ``text`` to ``recipient`` if it has a ``msg`` method."""
    target = flow_execution.resolve_flow_reference(recipient)
    message = flow_execution.resolve_flow_reference(text)
    if hasattr(target, "msg"):
        target.msg(message)
