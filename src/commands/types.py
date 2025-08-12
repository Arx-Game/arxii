"""Type declarations for command representations."""

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass
class CommandDescriptor:
    """Serializable descriptor for an actionable command.

    Args:
        label: Human readable label shown to the player.
        action: Command verb to send back to the server.
        params: Additional parameters required to execute the command.
        icon: Optional icon identifier for frontend use.
    """

    label: str
    action: str
    params: Mapping[str, Any]
    icon: str | None = None
