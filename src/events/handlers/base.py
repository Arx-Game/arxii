"""
See __init__.py for overview.
"""

from events.consts import EventType, NotificationTiming
from events.event_stack import EventStack
from events.exceptions import StopEvent


class BaseEventHandler:
    """
    Base class for all event handlers.
    """

    event_type: EventType = None

    def __init__(
        self, caller=None, target=None, parent_event=None, context=None, reraise=False
    ):
        self.caller = caller
        self.parent_event = parent_event
        if self.parent_event:
            self.event_stack = self.parent_event.event_stack
            self.event_stack.add_event(self)
        else:
            self.event_stack = EventStack(self)
        self.context = context
        self.reraise = reraise
        self.target = target

    def execute(self):
        try:
            self.check_prerequisites()
            self.emit_notification(
                self.event_type, NotificationTiming.PRE_PROCESS.value
            )
            self.process_event()
            self.emit_notification(
                self.event_type, NotificationTiming.POST_PROCESS.value
            )
        except StopEvent:
            if self.reraise:
                raise

    def process_event(self):
        """
        The real meat of the event handler. This assumes that we haven't been stopped
        by an event listener or a prerequisite, so we're calling the methods to make
        this event happen. Generally these should be methods within the caller and/or
        the target, allowing them to customize the expected behavior.
        """
        raise NotImplementedError

    def check_prerequisites(self):
        """
        Can be overridden in individual event handlers. If a prerequisite fails and
        the event cannot be attempted, StopEvent should be raised. In general, any
        prerequisite check should be about the caller being able to attempt the action
        at all: this should usually be about necessary pre-conditions that must be
        met before it can be attempted and should fail if they're not present. Resource
        costs, components, tools, etc.
        """
        pass

    def emit_notification(self, event_type: EventType, timing: NotificationTiming):
        """
        Emits a notification for our event type to any listeners. They can do virtually
        anything - raise StopEvent to stop the event in its tracks, kick off another
        event chain, etc.
        :param event_type:
        :param timing:
        :return:
        """
        # TODO: Add later with event listeners for notifications
        pass
