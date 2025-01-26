"""
The event stack is responsible for resolving a series of flows, each of which is an
event handler object, in flows/handlers/. Any event handler object will
emit a notification, and listeners for that event can spawn many more flows.
Those are all added to an event stack to make them all aware of other flows and
to prevent any sort of infinite recursion.
"""


class EventStack:
    """
    A container for a sequence of flows, keeping track of which flows have been
    added to the stack and in which order.
    """

    def __init__(self, root_event):
        self.root_event = root_event
        self.events = [root_event]

    def add_event(self, event):
        if event not in self.events:
            self.events.append(event)
