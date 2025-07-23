from typing import TYPE_CHECKING, List

if TYPE_CHECKING:
    from flows.flow_event import FlowEvent
    from flows.flow_stack import FlowStack
    from flows.models import Trigger
    from flows.scene_data_manager import SceneDataManager


class TriggerRegistry:
    """
    A registry maintained on a room that tracks active triggers.
    Triggers register when a character enters a room and unregister on exit.
    When an event is emitted to the room, the registry evaluates each trigger
    (in order of priority) and spawns subflows for those that fire.
    If any trigger sets event.stop_propagation to True, processing stops.
    """

    def __init__(self):
        self.triggers: List[Trigger] = []  # List of active Trigger instances

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

    def process_event(
        self, event: "FlowEvent", flow_stack: "FlowStack", context: "SceneDataManager"
    ) -> None:
        """Process an event by evaluating registered triggers in priority order.

        For each trigger:
        1. Check if the trigger matches the event type and conditions
        2. If it matches, execute the associated flow with the trigger's data
        3. Stop processing if the event's stop_propagation flag is set

        Args:
            event: The event to process
            flow_stack: The flow stack for executing flows
            context: The context for flow execution
        """
        for trigger in self.triggers:
            if not trigger.should_trigger_for_event(event):
                continue

            # Combine event and trigger data for the flow
            variable_mapping = {"event": event, **trigger.data_map}  # cached property

            # Execute the trigger's flow
            flow_stack.create_and_execute_flow(
                flow_definition=trigger.trigger_definition.flow_definition,
                context=context,
                origin=trigger,
                limit=1,
                variable_mapping=variable_mapping,
            )

            # Check if we should stop processing triggers
            if event.stop_propagation:
                break
