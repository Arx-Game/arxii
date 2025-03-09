"""
The FlowStack is responsible for managing a series of flows—each represented by a
FlowExecution—that occur during game processing. Flows are spawned by triggers,
commands, or service functions, and they can emit FlowEvents or update context data
as needed. The FlowStack keeps track of these flows to prevent infinite recursion or
excessive duplication, and it maintains a history of executed flow steps for debugging
and auditing purposes.
"""

from collections import defaultdict

from flows.flow_execution import FlowExecution


class FlowStack:
    """
    A container for FlowExecutions, tracking which flows have been spawned and in which order.
    Each FlowExecution is associated with an origin (e.g., a trigger, command, etc.) and is
    identified by an execution key (combining the flow definition and its origin). The FlowStack
    limits how many times a flow from a given origin may be spawned and records the history of
    executed flow steps.
    """

    def __init__(self):
        self.step_history = []  # List of executed flow steps.
        # Mapping from execution_key to a list of FlowExecution instances.
        self.execution_mapping = defaultdict(list)

    def create_and_execute_flow(
        self, flow_definition, context, origin, limit=1, variable_mapping=None
    ):
        """
        Creates and executes a FlowExecution for the given flow definition, context, and origin.
        If the number of FlowExecutions for the same (flow, origin) combination has reached the
        specified limit, no new flow is spawned.

        :param flow_definition: The FlowDefinition to execute.
        :param context: The shared ContextData instance.
        :param origin: The object (e.g. a Trigger or Command) that initiated the flow.
        :param limit: Maximum allowed FlowExecutions for this (flow, origin) combination.
        :param variable_mapping: Optional initial mapping of flow variables.
        """
        flow_execution = FlowExecution(
            flow_definition, context, self, origin, variable_mapping=variable_mapping
        )
        execution_key = flow_execution.execution_key()

        if len(self.execution_mapping[execution_key]) >= limit:
            return  # Do not spawn another flow if the limit is reached.

        self.execution_mapping[execution_key].append(flow_execution)
        self.execute_flow(flow_execution)

    def execute_flow(self, flow_execution):
        """
        Executes a FlowExecution by repeatedly executing its current step until the flow
        completes. Each executed step is recorded in the step history.
        """
        while flow_execution.current_step:
            self.record_step_execution(flow_execution.current_step)
            flow_execution.execute_current_step()

    def record_step_execution(self, execution_step):
        """
        Records that a specific flow step has been executed by adding it to the step history.
        """
        self.step_history.append(execution_step)
