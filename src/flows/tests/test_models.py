from django.test import TestCase

from flows.factories import (
    ContextDataFactory,
    FlowDefinitionFactory,
    FlowStepDefinitionFactory,
)
from flows.flow_execution import FlowExecution


class FlowStepDefinitionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.flow_def = FlowDefinitionFactory()
        cls.context = ContextDataFactory()

    def setUp(self):
        # Each test gets a fresh variable mapping and flow execution
        self.variable_mapping = {}
        self.fx = FlowExecution(
            flow_definition=self.flow_def,
            context=self.context,
            event_stack=None,
            origin=None,
            variable_mapping=self.variable_mapping,
        )

    def test_resolve_modifier_add_simple(self):
        step = FlowStepDefinitionFactory(
            flow_definition=self.flow_def,
            parameters={"attribute": "foo", "modifier": {"name": "add", "args": [3]}},
        )
        mod = step.resolve_modifier(self.fx)
        self.assertEqual(mod(2), 5)

    def test_resolve_modifier_with_variable(self):
        step = FlowStepDefinitionFactory(
            flow_definition=self.flow_def,
            parameters={
                "attribute": "foo",
                "modifier": {"name": "add", "args": ["$bonus"]},
            },
        )
        self.fx.variable_mapping["bonus"] = 7
        mod = step.resolve_modifier(self.fx)
        self.assertEqual(mod(3), 10)

    def test_resolve_modifier_with_variable_attr(self):
        class Bonus:
            def __init__(self):
                self.val = 4

        step = FlowStepDefinitionFactory(
            flow_definition=self.flow_def,
            parameters={
                "attribute": "foo",
                "modifier": {"name": "add", "args": ["$bonus.val"]},
            },
        )
        self.fx.variable_mapping["bonus"] = Bonus()
        mod = step.resolve_modifier(self.fx)
        self.assertEqual(mod(3), 7)

    def test_resolve_modifier_invalid_schema(self):
        step = FlowStepDefinitionFactory(
            flow_definition=self.flow_def,
            parameters={"attribute": "foo", "modifier": {"args": [3]}},  # Missing name
        )
        with self.assertRaises(ValueError):
            step.resolve_modifier(self.fx)

    def test_resolve_modifier_unknown_operator(self):
        step = FlowStepDefinitionFactory(
            flow_definition=self.flow_def,
            parameters={
                "attribute": "foo",
                "modifier": {"name": "notarealop", "args": [3]},
            },
        )
        with self.assertRaises(ValueError):
            step.resolve_modifier(self.fx)

    def test_resolve_modifier_int_shortcut(self):
        step = FlowStepDefinitionFactory(
            flow_definition=self.flow_def,
            parameters={"attribute": "foo", "modifier": 5},
        )
        mod = step.resolve_modifier(self.fx)
        self.assertEqual(mod(2), 7)

    def test_resolve_flow_reference_missing_var(self):
        with self.assertRaises(RuntimeError):
            self.fx.resolve_flow_reference("$missing")

    def test_resolve_flow_reference_attr_missing(self):
        class Bonus:
            pass

        self.fx.variable_mapping["bonus"] = Bonus()
        with self.assertRaises(RuntimeError):
            self.fx.resolve_flow_reference("$bonus.val")
