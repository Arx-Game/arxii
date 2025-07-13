from typing import TYPE_CHECKING, Dict

if TYPE_CHECKING:
    from flows.context_data import ContextData
    from flows.flow_execution import FlowExecution
    from flows.flow_stack import FlowStack


class FlowEvent:
    """
    Represents an in-memory event emitted during flow execution.

    This event is distinct from Django signals or in-game roleplay events.
    It carries metadata and mutable state that can be modified by triggers and
    subflows. Importantly, it holds a reference to the source that spawned it,
    typically the FlowExecution or Command that emitted the event.

    Attributes:
        event_type (str): A string identifying the type of event (e.g. "attack").
        source (FlowExecution): The flow execution that spawned the event.
        data (dict): A dictionary containing metadata for the event.
        stop_propagation (bool): When set to True, further trigger processing should halt.
    """

    def __init__(
        self, event_type: str, source: "FlowExecution", data: Dict | None = None
    ):
        self.event_type = event_type
        self.source = source  # Reference to the FlowExecution that spawned this event.
        self.data = data or {}
        self.stop_propagation = False

    def mark_stop(self):
        """Marks the event so that no further triggers will process it."""
        self.stop_propagation = True

    def update_data(self, key, value):
        """Updates the event's metadata."""
        self.data[key] = value

    def __str__(self):
        return (
            f"<FlowEvent type={self.event_type} source={self.source} "
            f"data={self.data} stop_propagation={self.stop_propagation}>"
        )

    @property
    def context(self) -> "ContextData":
        return self.source.context

    @property
    def flow_stack(self) -> "FlowStack":
        return self.source.flow_stack

    def matches_conditions(self, conditions: dict) -> bool:
        """Check if this event's data matches the given conditions.

        Args:
            conditions: Dictionary of {variable_path: expected_value} pairs

        Returns:
            bool: True if all conditions pass, False otherwise or if any error occurs
        """
        if not conditions:
            return True

        for var_path, expected in conditions.items():
            try:
                value = self.data.get(var_path, None)
                if value != expected:
                    return False
            except (KeyError, AttributeError):
                return False

        return True
