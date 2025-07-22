from unittest.mock import MagicMock, patch

from django.test import TestCase

from flows.consts import FlowActionChoices
from flows.factories import (
    FlowDefinitionFactory,
    FlowExecutionFactory,
    FlowStepDefinitionFactory,
)


class TestEmitFlowEventForEach(TestCase):
    def test_emit_event_for_each_creates_events(self):
        flow_def = FlowDefinitionFactory()
        FlowStepDefinitionFactory(
            flow=flow_def,
            action=FlowActionChoices.EMIT_FLOW_EVENT_FOR_EACH,
            variable_name="glance",
            parameters={
                "iterable": "$items",
                "event_type": "glance",
                "data": {"target": "$item"},
            },
        )

        fx = FlowExecutionFactory(
            flow_definition=flow_def,
            variable_mapping={"items": [1, 2]},
        )

        with patch.object(fx, "get_trigger_registry") as mock_registry:
            mock_registry.return_value = MagicMock()
            fx.flow_stack.execute_flow(fx)

        self.assertIn("glance_0", fx.context.flow_events)
        self.assertIn("glance_1", fx.context.flow_events)
        self.assertEqual(fx.context.flow_events["glance_0"].data["target"], 1)
        self.assertEqual(fx.context.flow_events["glance_1"].data["target"], 2)
