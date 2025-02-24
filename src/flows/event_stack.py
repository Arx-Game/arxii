"""
The event stack is responsible for resolving a series of flows, each of which is an
event handler object, in flows/handlers/. Any event handler object will
emit a notification, and listeners for that event can spawn many more flows.
Those are all added to an event stack to make them all aware of other flows and
to prevent any sort of infinite recursion.
"""

from collections import defaultdict

from flows.flow_execution import FlowExecution


class EventStack:
    """
    A container for a sequence of FlowExecutions, keeping track of which flows have been
    added to the stack and in which order. Every FlowExecution in the stack has knowledge
    of its origin: generally a trigger, but it could also be a command. The tuple of the
    FlowExecution and its Origin are used to determine which flows have been added - a
    given flow could be operating on several different characters and different origins,
    and only need to be capped/stopped if the same flow from the same origin is being
    created/added many times.
    """

    def __init__(self):
        self.step_history = []  # List of tuples (FlowExecution, FlowExecutionStep)
        self.execution_mapping = defaultdict(
            list
        )  # { execution_key: [FlowExecution, ...] }

    def create_and_execute_flow(self, flow_definition, context, origin, limit=1):
        flow_execution = FlowExecution(flow_definition, context, self, origin)
        execution_key = flow_execution.execution_key()

        if len(self.execution_mapping[execution_key]) >= limit:
            return  # Do not add a new flow if we've reached the limit.

        self.execution_mapping[execution_key].append(flow_execution)
        self.execute_flow(flow_execution)

    def execute_flow(self, flow_execution):
        while flow_execution.current_step:
            self.record_step_execution(flow_execution.current_step)
            flow_execution.execute_current_step()

    def record_step_execution(self, execution_step):
        self.step_history.append(execution_step)
