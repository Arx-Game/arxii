"""Type declarations for flows system."""

from typing import Any, Mapping, Protocol, runtime_checkable


@runtime_checkable
class MsgCapable(Protocol):
    """Protocol for objects that can receive messages via .msg() method."""

    def msg(self, text: str | tuple[str, Mapping[str, Any]], **kwargs: Any) -> None:
        """Send a message to this object.
        
        Args:
            text: Message text or tuple of (text, mapping).
            **kwargs: Additional keyword arguments.
        """
        ...


@runtime_checkable
class LocationCapable(Protocol):
    """Protocol for objects that have a location attribute."""

    location: "LocationCapable | None"


@runtime_checkable
class MsgContentsCapable(Protocol):
    """Protocol for objects that can broadcast messages to their contents."""

    def msg_contents(
        self,
        text: str,
        *,
        from_obj: Any = None,
        mapping: Mapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        """Broadcast a message to all objects in this location.
        
        Args:
            text: Message text to broadcast.
            from_obj: Object sending the message.
            mapping: Variable mapping for message formatting.
            **kwargs: Additional keyword arguments.
        """
        ...


@runtime_checkable
class DisplayNameCapable(Protocol):
    """Protocol for objects that can provide a display name."""

    def get_display_name(self, looker: Any = None) -> str:
        """Get the display name for this object.
        
        Args:
            looker: Object viewing this object.
            
        Returns:
            Display name string.
        """
        ...


@runtime_checkable
class AccountCapable(Protocol):
    """Protocol for objects that have an associated account."""

    account: Any  # Would be Account type but avoiding circular imports


@runtime_checkable
class PKCapable(Protocol):
    """Protocol for objects that have a primary key."""

    pk: int | str


@runtime_checkable
class ActiveSceneCapable(Protocol):
    """Protocol for locations that may have an active scene."""

    active_scene: Any  # Would be Scene type but avoiding circular imports


@runtime_checkable
class TraversalCapable(Protocol):
    """Protocol for exit objects that can be traversed."""

    def can_traverse(self, caller: Any) -> bool:
        """Check if the caller can traverse this exit.
        
        Args:
            caller: Object attempting to traverse.
            
        Returns:
            True if traversal is permitted.
        """
        ...


@runtime_checkable
class MovementCapable(Protocol):
    """Protocol for objects that can be moved or can move."""

    def can_move(self, obj: Any, destination: Any) -> bool:
        """Check if object can move to destination.
        
        Args:
            obj: Object being moved.
            destination: Target destination.
            
        Returns:
            True if movement is permitted.
        """
        ...