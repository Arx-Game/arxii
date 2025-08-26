"""Type declarations for command representations."""

from dataclasses import dataclass
from typing import Any, Dict, Mapping, Pattern, Protocol

from evennia_extensions.models import CallerType

# Type aliases for common patterns
Kwargs = Dict[str, Any]  # For **kwargs parameters


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


class DispatcherProtocol(Protocol):
    """Protocol for command dispatchers."""

    pattern: Pattern[str]  # compiled regex pattern
    handler: Any  # BaseHandler - using Any to avoid circular import

    def parse(self, caller: CallerType, raw_string: str) -> bool:
        """Parse input string and determine if this dispatcher matches.

        Args:
            caller: Object executing the command (Account, Session, or ObjectDB).
            raw_string: Raw input string to parse.

        Returns:
            True if this dispatcher matches the input.
        """
        ...

    def get_help_string(self) -> str:
        """Get help string for this dispatcher.

        Returns:
            Help text describing proper syntax.
        """
        ...
