from django.test import TestCase

from flows.consts import FlowActionChoices
from flows.factories import (
    FlowDefinitionFactory,
    FlowExecutionFactory,
    FlowStepDefinitionFactory,
)
from flows.service_functions.perception import get_formatted_description


class FlowExecutionServiceFunctionTests(TestCase):
    def test_get_service_function_returns_callable(self):
        fx = FlowExecutionFactory()
        func = fx.get_service_function("get_formatted_description")
        self.assertIs(func, get_formatted_description)

    def test_execute_call_service_function_integration(self):
        flow_def = FlowDefinitionFactory()
        FlowStepDefinitionFactory(
            flow=flow_def,
            action=FlowActionChoices.CALL_SERVICE_FUNCTION,
            variable_name="get_formatted_description",
            parameters={"obj": "sword", "result_variable": "desc"},
        )

        fx = FlowExecutionFactory(flow_definition=flow_def)
        fx.execute_current_step()

        self.assertEqual(fx.get_variable("desc"), "Formatted description for sword")
