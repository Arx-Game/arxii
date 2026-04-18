"""FlowExecution carries dispatch_result + flow_stack for reactive flow steps."""

from django.test import TestCase

from flows.factories import FlowDefinitionFactory
from flows.flow_execution import FlowExecution
from flows.flow_stack import FlowStack
from flows.scene_data_manager import SceneDataManager
from flows.trigger_handler import DispatchResult


class FlowExecutionDispatchContextTests(TestCase):
    def test_dispatch_result_and_flow_stack_plumbed(self) -> None:
        flow_def = FlowDefinitionFactory()
        context = SceneDataManager()
        stack = FlowStack(owner=None, originating_event="damage_pre_apply")
        dr = DispatchResult()
        execution = FlowExecution(
            flow_definition=flow_def,
            context=context,
            flow_stack=stack,
            origin=None,
            variable_mapping={"payload": object()},
            dispatch_result=dr,
        )
        self.assertIs(execution.dispatch_result, dr)
        self.assertIs(execution.flow_stack, stack)

    def test_dispatch_result_defaults_to_none(self) -> None:
        flow_def = FlowDefinitionFactory()
        context = SceneDataManager()
        stack = FlowStack(owner=None, originating_event="x")
        execution = FlowExecution(
            flow_definition=flow_def,
            context=context,
            flow_stack=stack,
            origin=None,
        )
        self.assertIsNone(execution.dispatch_result)
