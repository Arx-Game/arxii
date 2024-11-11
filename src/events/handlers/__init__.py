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
