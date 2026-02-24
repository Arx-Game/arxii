from typing import TYPE_CHECKING

if TYPE_CHECKING:
    # noinspection PyUnresolvedReferences
    from flows.flow_execution import FlowExecution

    # noinspection PyUnresolvedReferences
    from flows.flow_stack import FlowStack

    # noinspection PyUnresolvedReferences
    from flows.scene_data_manager import SceneDataManager


class FlowEvent:
    """Lightweight signal emitted by a running flow.

    FlowEvent objects are created by flow steps to mark notable moments such as
    when a character glances at another object. Events are stored on the current
    SceneDataManager instance and passed to triggers. Because the ``data`` dictionary is
    mutable, triggered flows can update it so later conditions may react. This
    enables event chains without direct coupling in Python code.

    Attributes:
        event_type: String identifier like "attack" or "glance".
        source: The FlowExecution that emitted the event.
        data: Metadata dictionary shared among triggers.
        stop_propagation: If True, no further triggers will see the event.
    """

    def __init__(
        self,
        event_type: str,
        source: "FlowExecution",
        data: dict[str, object] | None = None,
    ) -> None:
        self.event_type = event_type
        self.source = source  # Reference to the FlowExecution that spawned this event.
        self.data: dict[str, object] = data or {}
        self.stop_propagation = False

    def mark_stop(self) -> None:
        """Marks the event so that no further triggers will process it."""
        self.stop_propagation = True

    def update_data(self, key: str, value: object) -> None:
        """Updates the event's metadata."""
        self.data[key] = value

    def __str__(self) -> str:
        return (
            f"<FlowEvent type={self.event_type} source={self.source} "
            f"data={self.data} stop_propagation={self.stop_propagation}>"
        )

    @staticmethod
    def _pk_or_value(value: object) -> object:
        try:
            return value.pk
        except AttributeError:
            return value

    @property
    def context(self) -> "SceneDataManager":
        return self.source.context

    @property
    def flow_stack(self) -> "FlowStack":
        return self.source.flow_stack

    @property
    def usage_key(self) -> tuple[int | None, int | None]:
        """Return identifiers for usage tracking.

        The key consists of the primary key for the origin of the emitting
        ``FlowExecution`` and, if present, the primary key of the ``target``
        stored in ``data``. Objects are resolved to their ``pk`` values while
        integers are returned unchanged.
        """
        try:
            source_pk: int | None = self.source.origin.pk
        except AttributeError:
            source_pk = None

        target: object = self.data.get("target")
        raw_target_pk = self._pk_or_value(target)
        # Non-int pks (e.g. string refs) are dropped — usage tracking only supports int keys.
        target_pk: int | None = raw_target_pk if isinstance(raw_target_pk, int) else None

        return source_pk, target_pk

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
                value_cmp = self._pk_or_value(value)
                expected_cmp = self._pk_or_value(expected)
                if value_cmp != expected_cmp:
                    return False
            except (KeyError, AttributeError):
                return False

        return True
