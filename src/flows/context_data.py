from evennia.objects.models import ObjectDB


class ContextData:
    """Shared state container used while executing flows.

    ContextData maps object IDs to `BaseState` instances. These states store
    attributes that service functions and flow steps may change. The container
    also keeps `FlowEvent` objects emitted during execution so that later
    steps or triggered flows can reference them.

    Attributes:
        states: Mapping of object ID to state.
        flow_events: Mapping of event key to `FlowEvent`.
    """

    def __init__(self):
        # Dictionary to store object states keyed by object pk.
        self.states = {}
        # Dictionary to store FlowEvent objects, keyed by a string.
        self.flow_events = {}

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

    def store_flow_event(self, key, flow_event):
        """Store a FlowEvent under a specific key.

        Args:
            key: Identifier for the event.
            flow_event: The event instance to store.
        """
        self.flow_events[key] = flow_event

    def get_state_by_pk(self, pk):
        """Retrieve a state by its primary key.

        If the state is not already cached, the Evennia object is fetched and
        a new state is created and stored.

        Args:
            pk: Primary key of the Evennia object.

        Returns:
            The corresponding state or None if the object does not exist.
        """
        if pk in self.states:
            return self.states[pk]

        try:
            obj = ObjectDB.objects.get(pk=pk)
        except ObjectDB.DoesNotExist:
            return None

        return self.initialize_state_for_object(obj)

    def initialize_state_for_object(self, obj: ObjectDB):
        """Initialize and store a state for an Evennia object.

        Args:
            obj: The Evennia object to create a state for.

        Returns:
            The initialized state.
        """
        state = obj.get_object_state(self)
        self.states[obj.pk] = state
        return state
