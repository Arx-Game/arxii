"""Utility class coordinating multiple running flows.

The FlowStack records each FlowExecution that is spawned and maintains a
history of executed steps for debugging. Flows may originate from triggers,
commands or other service functions - whenever one flow spawns another, the
new execution is registered here.
"""

from collections import defaultdict
from collections.abc import Iterator
import contextlib
from typing import TYPE_CHECKING, Any

from flows.flow_execution import FlowExecution
from flows.scene_data_manager import SceneDataManager
from flows.trigger_registry import TriggerRegistry

if TYPE_CHECKING:
    from flows.models.flows import FlowDefinition


class FlowStackCapExceeded(Exception):
    """Raised when a flow stack exceeds its recursion depth cap."""


class FlowStack:
    """Container for running flows.

    The stack maps a ``(flow_definition, origin)`` pair to a list of
    ``FlowExecution`` instances. Each executed step is recorded in
    ``step_history`` for later inspection. A record of all created executions is
    kept in ``execution_mapping`` keyed by their execution key.

    The ``depth`` attribute tracks nested reactive dispatch calls. Callers use
    ``nested()`` to enter a deeper level; ``FlowStackCapExceeded`` is raised if
    ``depth`` would exceed ``cap``, preventing infinite trigger loops.
    """

    def __init__(
        self,
        trigger_registry: TriggerRegistry | None = None,
        *,
        owner: Any = None,
        originating_event: str | None = None,
        cap: int = 8,
    ) -> None:
        """Initialize the FlowStack.

        Args:
            trigger_registry: Registry used when propagating flow events.
            owner: The object (character, room, etc.) that owns this stack.
            originating_event: Name of the event that initiated this stack.
            cap: Maximum nesting depth before FlowStackCapExceeded is raised.
        """
        self.step_history: list[object] = []  # List of executed flow steps.
        # Mapping from execution_key to a list of FlowExecution instances.
        self.execution_mapping: defaultdict[str, list[FlowExecution]] = defaultdict(
            list,
        )
        self.trigger_registry = trigger_registry
        self.owner = owner
        self.originating_event = originating_event
        self.cap = cap
        self.depth = 1
        self._cancelled = False

    @contextlib.contextmanager
    def nested(self) -> Iterator[None]:
        """Context manager that increments depth for a nested dispatch call.

        Raises:
            FlowStackCapExceeded: If entering would push depth beyond ``cap``.
        """
        if self.depth >= self.cap:
            msg = (
                f"FlowStack depth {self.depth} would exceed cap {self.cap} "
                f"(originating: {self.originating_event})"
            )
            raise FlowStackCapExceeded(msg)
        self.depth += 1
        try:
            yield
        finally:
            self.depth -= 1

    def mark_cancelled(self) -> None:
        """Mark this stack as cancelled. Called by the ``CANCEL_EVENT`` flow step."""
        self._cancelled = True

    def was_cancelled(self) -> bool:
        """True if any dispatch on this stack set the cancel flag.

        Emission sites check this after ``emit_event`` returns to decide
        whether to suppress the default behaviour (e.g., skip damage apply,
        abort movement).
        """
        return self._cancelled

    def create_and_execute_flow(
        self,
        flow_definition: "FlowDefinition",
        context: SceneDataManager,
        origin: object,
        variable_mapping: dict[str, object] | None = None,
    ) -> FlowExecution:
        """Create and execute a flow definition.

        Args:
            flow_definition: The FlowDefinition to execute.
            context: Shared SceneDataManager instance.
            origin: Object that initiated the flow.
            variable_mapping: Optional initial variable mapping.

        Returns:
            The newly created FlowExecution.
        """
        flow_execution = FlowExecution(
            flow_definition,
            context,
            self,
            origin,
            variable_mapping=variable_mapping,
            trigger_registry=self.trigger_registry,
        )
        execution_key = flow_execution.execution_key()

        self.execution_mapping[execution_key].append(flow_execution)
        self.execute_flow(flow_execution)
        return flow_execution

    def execute_flow(self, flow_execution: FlowExecution) -> None:
        """Execute a FlowExecution until completion.

        Each executed step is recorded in `step_history`.
        """
        while flow_execution.current_step:
            self.record_step_execution(flow_execution.current_step)
            flow_execution.execute_current_step()

    def record_step_execution(self, execution_step: object) -> None:
        """Record that a flow step has executed."""
        self.step_history.append(execution_step)
