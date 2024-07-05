"""
Event Handlers

This module defines the EventHandler classes responsible for processing various
types of events that occur in the game. Each EventHandler represents a specific type
of event and is capable of handling the complexities involved in processing that
event, including potentially triggering a chain or sequence of events.

Responsibilities of an EventHandler:
1. Emitting Notifications: EventHandlers will emit notifications to event listeners
   in the room or elsewhere that might be listening for this specific event. This
   process happens both before and after the main event action is attempted. Event
   listeners can respond to these notifications with their own custom code, which can
   modify the event or stop it from occurring entirely. Event listeners can also set
   up their own event chains in response. Each notification includes a context object
   containing information such as whether it is emitted before or after the main
   event action, and whether the action was successful if emitted afterwards.

2. Processing the Event Action: The core responsibility of the EventHandler is to
   process the action itself. This involves calling the appropriate method on the
   target object, provided that the event was not stopped during the notification
   phase. The specific logic for the action is encapsulated within the EventHandler.

Example:
For the 'look' command, the dispatchers might instantiate and call an ExamineEvent.
The ExamineEvent would handle emitting notifications to any listeners before and
after the attempt to examine. If the event is not stopped by any listeners, the
ExamineEvent would then call the appropriate method on the target object to complete
the action.

Terminology:
- EventHandler: A class responsible for processing a specific type of event.
- Notification: A message emitted by an EventHandler to notify listeners of an event
  occurring.
- Listener: A piece of code that responds to notifications emitted by EventHandlers.

"""

from events.consts import EventType, NotificationTiming
from events.exceptions import StopEvent


class EventStack:
    """
    A container for a sequence of events, keeping track of which events have been
    added to the stack and in which order.
    """

    def __init__(self, root_event):
        self.root_event = root_event
        self.events = [root_event]

    def add_event(self, event):
        if event not in self.events:
            self.events.append(event)


class BaseEventHandler:
    """
    Base class for all event handlers.
    """

    event_type: EventType = None

    def __init__(self, caller=None, parent_event=None, context=None, reraise=False):
        self.caller = caller
        self.parent_event = parent_event
        if self.parent_event:
            self.event_stack = self.parent_event.event_stack
            self.event_stack.add_event(self)
        else:
            self.event_stack = EventStack(self)
        self.context = context
        self.reraise = reraise

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
