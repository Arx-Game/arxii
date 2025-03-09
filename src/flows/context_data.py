class ContextData:
    """
    A simple in-memory store for context values and flow events.

    This class acts as a "redux store" for our flow system. It holds ephemeral state
    for objects (e.g., character descriptions, modifiers, etc.) and stores FlowEvent
    objects emitted by flows. These events and other data can later be referenced by
    flow variables during execution.
    """

    def __init__(self):
        # Dictionary to store generic context values.
        self.values = {}
        # Dictionary to store FlowEvent objects, keyed by a string.
        self.flow_events = {}

    def set_context_value(self, key, value):
        """
        Set a context value in the store.

        :param key: The key under which to store the value.
        :param value: The value to store.
        """
        self.values[key] = value

    def modify_context_value(self, key, modifier):
        """
        Modify an existing context value. Assumes the value is numeric.

        If the key does not exist, it is initialized with the modifier.

        :param key: The key of the context value to modify.
        :param modifier: The numeric value to add.
        """
        if key in self.values:
            self.values[key] += modifier
        else:
            self.values[key] = modifier

    def store_flow_event(self, key, flow_event):
        """
        Store a FlowEvent in the context data under the specified key.

        :param key: The key under which to store the event.
        :param flow_event: The FlowEvent instance to store.
        """
        self.flow_events[key] = flow_event

    def get_context_value(self, key):
        """
        Retrieve a context value by its key.

        :param key: The key to look up.
        :return: The stored value, or None if not present.
        """
        return self.values.get(key)
