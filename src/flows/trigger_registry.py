class TriggerRegistry:
    """
    A registry maintained on a room that tracks active triggers.
    Triggers register when a character enters a room and unregister on exit.
    When an event is emitted to the room, the registry evaluates each trigger
    (in order of priority) and spawns subflows for those that fire.
    If any trigger sets event.stop_propagation to True, processing stops.
    """

    def __init__(self):
        self.triggers = []  # List of active Trigger instances

    def register_trigger(self, trigger):
        """
        Adds a trigger to the registry and sorts triggers by priority (highest first).
        """
        self.triggers.append(trigger)
        self.sort_triggers()

    def unregister_trigger(self, trigger):
        """
        Removes a trigger from the registry.
        """
        if trigger in self.triggers:
            self.triggers.remove(trigger)

    def sort_triggers(self):
        """
        Sorts the triggers in descending order by their priority.
        """
        self.triggers.sort(key=lambda t: t.priority, reverse=True)

    def process_event(self, event, event_stack, context):
        """
        Processes an event by iterating over all registered triggers.
        Each trigger is evaluated using its is_active(event, context) method.
        If a trigger fires, its associated subflow is spawned via the event stack,
        and the event (stored in context data) is passed as a flow variable.
        If event.stop_propagation is True, no further triggers are processed.

        :param event: The event object carrying metadata.
        :param event_stack: The EventStack instance managing flow execution.
        :param context: The shared ContextData instance.
        """
        for trigger in self.triggers:
            if trigger.is_active(event, context):
                # Collect additional trigger data (from TriggerData)
                trigger_data = {data.key: data.value for data in trigger.data.all()}
                # Build a flow variable mapping that includes the event
                variable_mapping = {"event": event, **trigger_data}
                # Spawn the subflow via the EventStack.
                event_stack.create_and_execute_flow(
                    flow_definition=trigger.trigger_definition.flow_definition,
                    context=context,
                    origin=trigger,
                    limit=1,
                    variable_mapping=variable_mapping,
                )
                # If the event is marked to stop propagation, halt further processing.
                if event.stop_propagation:
                    break
