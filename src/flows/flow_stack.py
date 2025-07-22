"""Utility class coordinating multiple running flows.

The FlowStack records each FlowExecution that is spawned and keeps them from
looping endlessly. It also maintains a simple history of executed steps for
debugging. Flows may originate from triggers, commands or other service
functions - whenever one flow spawns another, the new execution is registered
here.
"""

from collections import defaultdict

from flows.flow_execution import FlowExecution


class FlowStack:
    """Container for running flows.

    The stack maps a (flow_definition, origin) pair to a list of FlowExecution
    instances. This prevents endless recursion by limiting how many times the
    same flow can run for the same origin. Each executed step is recorded in
    `step_history` for later inspection.
    """

    def __init__(self):
        self.step_history = []  # List of executed flow steps.
        # Mapping from execution_key to a list of FlowExecution instances.
        self.execution_mapping = defaultdict(list)

    def create_and_execute_flow(
        self, flow_definition, context, origin, limit=1, variable_mapping=None
    ):
        """Create and execute a flow definition.

        Args:
            flow_definition: The FlowDefinition to execute.
            context: Shared ContextData instance.
            origin: Object that initiated the flow.
            limit: Maximum allowed executions for this `(flow, origin)` pair.
            variable_mapping: Optional initial variable mapping.

        Returns:
            The newly created FlowExecution.
        """
        flow_execution = FlowExecution(
            flow_definition, context, self, origin, variable_mapping=variable_mapping
        )
        execution_key = flow_execution.execution_key()

        if len(self.execution_mapping[execution_key]) < limit:
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
