from typing import TYPE_CHECKING

from evennia.objects.models import ObjectDB

if TYPE_CHECKING:
    # noinspection PyUnresolvedReferences
    from flows.object_states.base_state import BaseState

    # noinspection PyUnresolvedReferences
    from typeclasses.types import ArxTypeclass


class SceneDataManager:
    """Shared state container cached on a room.

    A SceneDataManager maps object IDs to ``BaseState`` instances. These states
    store attributes that service functions and flow steps may change during a
    command. ``FlowEvent`` objects emitted while executing flows are also kept
    here so that later steps or triggered flows can reference them.

    Attributes:
        states: Mapping of object ID to state. Persists across commands until
            :py:meth:`reset` is called.
        flow_events: Mapping of event key to ``FlowEvent``.
    """

    def __init__(self):
        # Dictionary to store object states keyed by object pk.
        self.states: dict[int, BaseState] = {}
        # Dictionary to store FlowEvent objects, keyed by a string.
        self.flow_events = {}
        # Mapping of (trigger_id, source_pk, target_pk) to number of times fired.
        self.trigger_history = {}

    def reset(self) -> None:
        """Clear stored states and events."""
        self.states.clear()
        self.flow_events.clear()

    def set_context_value(self, key, attribute, value):
        """Set an attribute on a stored state.

        Args:
            key: Object id for the state.
            attribute: Attribute name to update.
            value: New value for the attribute.

        Returns:
            The updated state or None if not found.
        """
        state = self.get_state_by_pk(key)
        if state is not None:
            setattr(state, attribute, value)
            self.states[key] = state
        return state

    def get_context_value(self, key, attribute):
        """Get an attribute from a stored state.

        Args:
            key: Object id for the state.
            attribute: Name of the attribute to retrieve.

        Returns:
            The attribute value or None if missing.
        """
        state = self.get_state_by_pk(key)
        if state is not None:
            return getattr(state, attribute, None)
        return None

    def modify_context_value(self, key, attribute, modifier):
        """Modify an attribute on a stored state using a callable.

        The modifier callable receives the old value and returns a new one.

        Args:
            key: Object id for the state.
            attribute: Name of the attribute to modify.
            modifier: Callable receiving the old value.

        Returns:
            The updated state or None if not found.
        """
        state = self.get_state_by_pk(key)
        if state is not None:
            old_value = getattr(state, attribute, None)
            new_value = modifier(old_value)
            setattr(state, attribute, new_value)
            self.states[key] = state
        return state

    def add_to_context_list(self, key, attribute, value):
        """Append ``value`` to a list attribute on a stored state."""

        state = self.get_state_by_pk(key)
        if state is not None:
            lst = list(getattr(state, attribute, []))
            if value not in lst:
                lst.append(value)
            setattr(state, attribute, lst)
            self.states[key] = state
        return state

    def remove_from_context_list(self, key, attribute, value):
        """Remove ``value`` from a list attribute on a stored state."""

        state = self.get_state_by_pk(key)
        if state is not None:
            lst = list(getattr(state, attribute, []))
            if value in lst:
                lst.remove(value)
            setattr(state, attribute, lst)
            self.states[key] = state
        return state

    def set_context_dict_value(self, key, attribute, dict_key, value):
        """Set ``dict_key`` in a dict attribute on a stored state."""

        state = self.get_state_by_pk(key)
        if state is not None:
            mapping = dict(getattr(state, attribute, {}))
            mapping[dict_key] = value
            setattr(state, attribute, mapping)
            self.states[key] = state
        return state

    def remove_context_dict_value(self, key, attribute, dict_key):
        """Remove ``dict_key`` from a dict attribute on a stored state."""

        state = self.get_state_by_pk(key)
        if state is not None:
            mapping = dict(getattr(state, attribute, {}))
            mapping.pop(dict_key, None)
            setattr(state, attribute, mapping)
            self.states[key] = state
        return state

    def modify_context_dict_value(self, key, attribute, dict_key, modifier):
        """Modify ``dict_key`` in a dict attribute using ``modifier``."""

        state = self.get_state_by_pk(key)
        if state is not None:
            mapping = dict(getattr(state, attribute, {}))
            old_value = mapping.get(dict_key)
            mapping[dict_key] = modifier(old_value)
            setattr(state, attribute, mapping)
            self.states[key] = state
        return state

    def store_flow_event(self, key, flow_event):
        """Store a FlowEvent under a specific key.

        Args:
            key: Identifier for the event.
            flow_event: The event instance to store.
        """
        self.flow_events[key] = flow_event

    def get_state_by_pk(self, pk: int | str) -> "BaseState | None":
        """Retrieve a state by its primary key.

        If the state is not already cached, the Evennia object is fetched and
        a new state is created and stored.

        Args:
            pk: Primary key of the Evennia object.

        Returns:
            The corresponding state or None if the object does not exist.
        """
        try:
            pk = int(pk)
        except (TypeError, ValueError):
            return None
        if pk in self.states:
            return self.states[pk]

        # noinspection PyUnresolvedReferences
        try:
            obj = ObjectDB.objects.get(pk=pk)
        except ObjectDB.DoesNotExist:
            return None

        return self.initialize_state_for_object(obj)

    def initialize_state_for_object(self, obj: "ArxTypeclass") -> "BaseState":
        """Initialize and store a state for an Evennia object.

        Args:
            obj: The Evennia object to create a state for.

        Returns:
            The initialized state.
        """
        from behaviors.models import BehaviorPackageInstance

        state: BaseState = obj.get_object_state(self)
        packages = list(
            BehaviorPackageInstance.objects.select_related("definition").filter(
                obj=obj
            ),
        )
        state.packages = packages
        self.states[obj.pk] = state
        state.initialize_state()
        return state

    # ------------------------------------------------------------------
    # Trigger tracking helpers
    # ------------------------------------------------------------------

    def has_trigger_fired(
        self,
        trigger_id: int,
        event_key: tuple[int | None, int | None],
    ) -> bool:
        """Return True if a trigger fired for ``event_key``."""
        return (trigger_id, event_key) in self.trigger_history

    def mark_trigger_fired(
        self,
        trigger_id: int,
        event_key: tuple[int | None, int | None],
    ) -> None:
        """Record that a trigger fired for ``event_key``."""
        key = (trigger_id, event_key)
        self.trigger_history[key] = self.trigger_history.get(key, 0) + 1

    def get_trigger_fire_count(
        self,
        trigger_id: int,
        event_key: tuple[int | None, int | None],
    ) -> int:
        """Return how many times ``trigger_id`` fired for ``event_key``."""
        return int(self.trigger_history.get((trigger_id, event_key), 0))
