"""
The object_states package provides ephemeral, mutable state wrappers for
Evennia objects during flow execution. Each state object encapsulates
default traits (such as name, description, and type-specific attributes)
derived from the underlying Evennia typeclass, while allowing these values
to be modified on the fly by triggers and service functions within a
flow_stack.

Modules in this package include:
  - base_state.py: Defines the BaseState class, which computes default
    attribute values using Django's cached_property and exposes a mutable
    interface for state changes.
  - room_state.py: Contains RoomState, a subclass of BaseState tailored for
    room objects. It adds room-specific features like weather data, zone
    information, and dynamic content listing by emitting glance events to
    contained objects.
  - character_state.py: Contains CharacterState, a subclass of BaseState
    designed for characters. It integrates character-specific details such as
    health status and appearance modifiers.
  - exit_state.py: Contains ExitState, used for exits and exposing traversal
    permissions.

This structure enables a clean separation of description logic for various
object types and ensures that default values can be overridden or modified
during the flow's execution.
"""
