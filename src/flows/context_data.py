from evennia.objects.models import ObjectDB


class ContextData:
    """
    A simple in-memory store for object states and flow events.

    This class acts as a redux store for our flow system. It holds ephemeral state
    objects for Evennia objects and stores FlowEvent objects emitted by flows. These
    states and events can later be referenced by flow variables during execution.
    """

    def __init__(self):
        # Dictionary to store object states keyed by object pk.
        self.states = {}
        # Dictionary to store FlowEvent objects, keyed by a string.
        self.flow_events = {}

    def set_context_value(self, key, attribute, value):
        """
        Set an attribute on a state in the store.

        :param key: The key (object pk) for the state.
        :param attribute: The attribute name to update.
        :param value: The new value for the attribute.
        :return: The updated state.
        """
        state = self.get_state_by_pk(key)
        if state is not None:
            setattr(state, attribute, value)
            self.states[key] = state
        return state

    def modify_context_value(self, key, attribute, modifier):
        """
        Modify an attribute on a state using a modifier callable.

        The modifier is a callable that takes the old value and returns a new value.

        :param key: The key (object pk) for the state.
        :param attribute: The attribute name to modify.
        :param modifier: A callable that takes the old value and returns a new value.
        :return: The updated state.
        """
        state = self.get_state_by_pk(key)
        if state is not None:
            old_value = getattr(state, attribute, None)
            new_value = modifier(old_value)
            setattr(state, attribute, new_value)
            self.states[key] = state
        return state

    def store_flow_event(self, key, flow_event):
        """
        Store a FlowEvent in the context data under the specified key.

        :param key: The key under which to store the event.
        :param flow_event: The FlowEvent instance to store.
        """
        self.flow_events[key] = flow_event

    def get_state_by_pk(self, pk):
        """
        Retrieve a state by its primary key. If the state is not already cached in the
        context, fetch the Evennia object (using its pk), instantiate its state via
        get_object_state(), cache it, and return it.

        :param pk: The primary key of an Evennia object.
        :return: The corresponding object state, or None if no such object exists.
        """
        if pk in self.states:
            return self.states[pk]

        try:
            obj = ObjectDB.objects.get(pk=pk)
        except ObjectDB.DoesNotExist:
            return None

        # Instantiate the object's state via its typeclass mixin,
        # passing self as the context.
        state = obj.get_object_state(self)
        self.states[pk] = state
        return state
