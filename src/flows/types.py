"""Type declarations for flow system protocols."""

from typing import Any, Protocol

from flows.object_states.base_state import BaseState


class MsgCapable(Protocol):
    """Protocol for objects that can receive messages."""

    def msg(self, text: str, **kwargs: Any) -> None:
        """Send a message to this object."""
        ...


class LocationCapable(Protocol):
    """Protocol for objects that have a location attribute."""

    location: Any | None


class MsgContentsCapable(Protocol):
    """Protocol for objects that can message their contents."""

    def msg_contents(
        self,
        text: str,
        from_obj: Any = None,
        mapping: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        """Send a message to all contents."""
        ...


class DisplayNameCapable(Protocol):
    """Protocol for objects that can provide display names."""

    def get_display_name(self, looker: Any = None) -> str:
        """Get the display name for this object."""
        ...


class AccountCapable(Protocol):
    """Protocol for objects that have an account attribute."""

    account: Any | None


class PKCapable(Protocol):
    """Protocol for objects that have a primary key."""

    pk: int


class ActiveSceneCapable(Protocol):
    """Protocol for objects that may have an active scene."""

    active_scene: Any | None


class TraversalCapable(Protocol):
    """Protocol for objects that support traversal checks."""

    def can_traverse(self, caller: BaseState) -> bool:
        """Check if caller can traverse this object."""
        ...


class MovementCapable(Protocol):
    """Protocol for objects that support movement."""

    def move_to(self, destination: Any, quiet: bool = True, **kwargs: Any) -> bool:
        """Move this object to a destination."""
        ...

    def can_move(self, obj: BaseState, destination: BaseState) -> bool:
        """Check if movement is allowed."""
        ...