"""Type declarations for command representations."""

from dataclasses import dataclass
from typing import Any, Mapping, Protocol, runtime_checkable

from evennia_extensions.models import CallerType

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


@runtime_checkable
class HandlerProtocol(Protocol):
    """Protocol for command handlers."""

    def run(self, caller: CallerType, **kwargs: Any) -> None:
        """Execute the handler with the given caller and arguments.
        
        Args:
            caller: Object executing the command (Account, Session, or ObjectDB).
            **kwargs: Additional arguments from dispatcher.
        """
        ...


@runtime_checkable
class DispatcherProtocol(Protocol):
    """Protocol for command dispatchers."""

    pattern: Any  # compiled regex pattern
    handler: HandlerProtocol

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
