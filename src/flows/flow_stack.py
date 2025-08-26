"""Utility class coordinating multiple running flows.

The FlowStack records each FlowExecution that is spawned and maintains a
history of executed steps for debugging. Flows may originate from triggers,
commands or other service functions - whenever one flow spawns another, the
new execution is registered here.
"""

from collections import defaultdict
from typing import Any, DefaultDict, List, Optional

from flows.flow_execution import FlowExecution
from flows.trigger_registry import TriggerRegistry


class FlowStack:
    """Container for running flows.

    The stack maps a ``(flow_definition, origin)`` pair to a list of
    ``FlowExecution`` instances. Each executed step is recorded in
    ``step_history`` for later inspection. A record of all created executions is
    kept in ``execution_mapping`` keyed by their execution key.
    """

    def __init__(self, trigger_registry: Optional[TriggerRegistry] = None) -> None:
        """Initialize the FlowStack.

        Args:
            trigger_registry: Registry used when propagating flow events.
        """
        self.step_history: list[Any] = []  # List of executed flow steps.
        # Mapping from execution_key to a list of FlowExecution instances.
        self.execution_mapping: DefaultDict[str, List[FlowExecution]] = defaultdict(
            list
        )
        self.trigger_registry = trigger_registry

    def create_and_execute_flow(
        self,
        flow_definition,
        context,
        origin,
        variable_mapping=None,
    ):
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

    def execute_flow(self, flow_execution):
        """Execute a FlowExecution until completion.

        Each executed step is recorded in `step_history`.
        """
        while flow_execution.current_step:
            self.record_step_execution(flow_execution.current_step)
            flow_execution.execute_current_step()

    def record_step_execution(self, execution_step):
        """Record that a flow step has executed."""
        self.step_history.append(execution_step)
