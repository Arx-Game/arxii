from typing import Dict


class FlowEvent:
    """
    Represents an in-memory event emitted during flow execution.

    This event is distinct from Django signals or in-game roleplay events.
    It carries metadata and mutable state that can be modified by triggers and
    subflows. Importantly, it holds a reference to the source that spawned it,
    typically the FlowExecution or Command that emitted the event.

    Attributes:
        event_type (str): A string identifying the type of event (e.g. "attack").
        source (object): The entity that spawned the event (typically a FlowExecution).
        data (dict): A dictionary containing metadata for the event.
        stop_propagation (bool): When set to True, further trigger processing should halt.
    """

    def __init__(self, event_type: str, source, data: Dict | None = None):
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
