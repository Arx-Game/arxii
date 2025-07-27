from unittest.mock import MagicMock, patch

from django.test import TestCase

from flows.consts import FlowActionChoices
from flows.factories import (
    FlowDefinitionFactory,
    FlowExecutionFactory,
    FlowStepDefinitionFactory,
    SceneDataManagerFactory,
)
from flows.flow_stack import FlowStack


class FlowStepDefinitionTests(TestCase):
    """Comprehensive tests for FlowStepDefinition methods, including all execute actions."""

    @classmethod
    def setUpTestData(cls):
        cls.flow_def = FlowDefinitionFactory()
        cls.context = SceneDataManagerFactory()

    def setUp(self):
        self.variable_mapping = {}

    def get_flow_execution(self, **overrides):
        """Create a new FlowExecution instance with test defaults and optional overrides."""
        # Create a copy of the variable mapping
        variable_mapping = dict(self.variable_mapping)

        # Update with any variable mapping from overrides
        if "variable_mapping" in overrides:
            variable_mapping.update(overrides.pop("variable_mapping"))

        # Create the execution with the combined variable mapping
        return FlowExecutionFactory(
            flow_definition=self.flow_def,
            context=self.context,
            variable_mapping=variable_mapping,
            **overrides,
        )

    def test_resolve_modifier_add_simple(self):
        step = FlowStepDefinitionFactory(
            flow=self.flow_def,
            parameters={"attribute": "foo", "modifier": {"name": "add", "args": [3]}},
        )
        fx = self.get_flow_execution()
        mod = step.resolve_modifier(fx)
        self.assertEqual(mod(2), 5)

    def test_resolve_modifier_with_variable(self):
        step = FlowStepDefinitionFactory(
            flow=self.flow_def,
            parameters={
                "attribute": "foo",
                "modifier": {"name": "add", "args": ["@bonus"]},
            },
        )
        fx = self.get_flow_execution(variable_mapping={"bonus": 7})
        mod = step.resolve_modifier(fx)
        self.assertEqual(mod(3), 10)

    def test_resolve_modifier_with_variable_attr(self):
        class Bonus:
            def __init__(self):
                self.val = 4

        step = FlowStepDefinitionFactory(
            flow=self.flow_def,
            parameters={
                "attribute": "foo",
                "modifier": {"name": "add", "args": ["@bonus.val"]},
            },
        )
        fx = self.get_flow_execution(variable_mapping={"bonus": Bonus()})
        mod = step.resolve_modifier(fx)
        self.assertEqual(mod(3), 7)

    def test_resolve_modifier_invalid_schema(self):
        step = FlowStepDefinitionFactory(
            flow=self.flow_def,
            parameters={"attribute": "foo", "modifier": {"args": [3]}},  # Missing name
        )
        fx = self.get_flow_execution()
        with self.assertRaises(ValueError):
            step.resolve_modifier(fx)

    def test_resolve_modifier_unknown_operator(self):
        step = FlowStepDefinitionFactory(
            flow=self.flow_def,
            parameters={
                "attribute": "foo",
                "modifier": {"name": "notarealop", "args": [3]},
            },
        )
        fx = self.get_flow_execution()
        with self.assertRaises(ValueError):
            step.resolve_modifier(fx)

    def test_resolve_modifier_int_shortcut(self):
        step = FlowStepDefinitionFactory(
            flow=self.flow_def,
            parameters={"attribute": "foo", "modifier": 5},
        )
        fx = self.get_flow_execution()
        mod = step.resolve_modifier(fx)
        self.assertEqual(mod(2), 7)

    def test_resolve_flow_reference_missing_var(self):
        # A step must exist for FlowExecution to be valid
        FlowStepDefinitionFactory(flow=self.flow_def)
        fx = self.get_flow_execution()
        with self.assertRaises(RuntimeError):
            fx.resolve_flow_reference("@missing")

    def test_resolve_flow_reference_attr_missing(self):
        class Bonus:
            pass

        # A step must exist for FlowExecution to be valid
        FlowStepDefinitionFactory(flow=self.flow_def)
        fx = self.get_flow_execution(variable_mapping={"bonus": Bonus()})
        with self.assertRaises(RuntimeError):
            fx.resolve_flow_reference("@bonus.val")

    def test_execute_conditional_equals_pass(self):
        step = FlowStepDefinitionFactory(
            flow=self.flow_def,
            action=FlowActionChoices.EVALUATE_EQUALS,
            variable_name="test_var",
            parameters={"value": 42},
        )
        fx = self.get_flow_execution(variable_mapping={"test_var": 42})
        next_step = step.execute(fx)
        self.assertEqual(next_step, fx.get_next_child(step))

    def test_execute_conditional_equals_fail(self):
        step = FlowStepDefinitionFactory(
            flow=self.flow_def,
            action=FlowActionChoices.EVALUATE_EQUALS,
            variable_name="test_var",
            parameters={"value": 42},
        )
        fx = self.get_flow_execution(variable_mapping={"test_var": 100})
        next_step = step.execute(fx)
        self.assertEqual(next_step, fx.get_next_sibling(step))

    def test_execute_set_context_value(self):
        step = FlowStepDefinitionFactory(
            flow=self.flow_def,
            action=FlowActionChoices.SET_CONTEXT_VALUE,
            variable_name="test_obj",
            parameters={"attribute": "count", "value": 42},
        )
        test_obj = object()
        fx = self.get_flow_execution(variable_mapping={"test_obj": test_obj})

        with patch.object(fx.context, "set_context_value") as mock_set:
            next_step = step.execute(fx)
            mock_set.assert_called_once_with(key=test_obj, attribute="count", value=42)
        self.assertEqual(next_step, fx.get_next_child(step))

    def test_execute_modify_context_value(self):
        step = FlowStepDefinitionFactory(
            flow=self.flow_def,
            action=FlowActionChoices.MODIFY_CONTEXT_VALUE,
            variable_name="test_obj",
            parameters={"attribute": "count", "modifier": {"name": "add", "args": [5]}},
        )
        test_obj = object()
        fx = self.get_flow_execution(variable_mapping={"test_obj": test_obj})

        with patch.object(fx.context, "modify_context_value") as mock_modify:
            next_step = step.execute(fx)
            mock_modify.assert_called_once()
            _, kwargs = mock_modify.call_args
            self.assertEqual(kwargs["key"], test_obj)
            self.assertEqual(kwargs["attribute"], "count")
            self.assertEqual(kwargs["modifier"](10), 15)
        self.assertEqual(next_step, fx.get_next_child(step))

    def test_execute_add_context_list_value(self):
        step = FlowStepDefinitionFactory(
            flow=self.flow_def,
            action=FlowActionChoices.ADD_CONTEXT_LIST_VALUE,
            variable_name="test_obj",
            parameters={"attribute": "names", "value": 3},
        )
        test_obj = object()
        fx = self.get_flow_execution(variable_mapping={"test_obj": test_obj})

        with patch.object(fx.context, "add_to_context_list") as mock_add:
            next_step = step.execute(fx)
            mock_add.assert_called_once_with(key=test_obj, attribute="names", value=3)
        self.assertEqual(next_step, fx.get_next_child(step))

    def test_execute_remove_context_list_value(self):
        step = FlowStepDefinitionFactory(
            flow=self.flow_def,
            action=FlowActionChoices.REMOVE_CONTEXT_LIST_VALUE,
            variable_name="test_obj",
            parameters={"attribute": "names", "value": 5},
        )
        test_obj = object()
        fx = self.get_flow_execution(variable_mapping={"test_obj": test_obj})

        with patch.object(fx.context, "remove_from_context_list") as mock_remove:
            next_step = step.execute(fx)
            mock_remove.assert_called_once_with(
                key=test_obj, attribute="names", value=5
            )
        self.assertEqual(next_step, fx.get_next_child(step))

    def test_execute_set_context_dict_value(self):
        step = FlowStepDefinitionFactory(
            flow=self.flow_def,
            action=FlowActionChoices.SET_CONTEXT_DICT_VALUE,
            variable_name="test_obj",
            parameters={"attribute": "mapping", "key": "foo", "value": 1},
        )
        test_obj = object()
        fx = self.get_flow_execution(variable_mapping={"test_obj": test_obj})

        with patch.object(fx.context, "set_context_dict_value") as mock_set:
            next_step = step.execute(fx)
            mock_set.assert_called_once_with(
                key=test_obj, attribute="mapping", dict_key="foo", value=1
            )
        self.assertEqual(next_step, fx.get_next_child(step))

    def test_execute_remove_context_dict_value(self):
        step = FlowStepDefinitionFactory(
            flow=self.flow_def,
            action=FlowActionChoices.REMOVE_CONTEXT_DICT_VALUE,
            variable_name="test_obj",
            parameters={"attribute": "mapping", "key": "foo"},
        )
        test_obj = object()
        fx = self.get_flow_execution(variable_mapping={"test_obj": test_obj})

        with patch.object(fx.context, "remove_context_dict_value") as mock_remove:
            next_step = step.execute(fx)
            mock_remove.assert_called_once_with(
                key=test_obj, attribute="mapping", dict_key="foo"
            )
        self.assertEqual(next_step, fx.get_next_child(step))

    def test_execute_modify_context_dict_value(self):
        step = FlowStepDefinitionFactory(
            flow=self.flow_def,
            action=FlowActionChoices.MODIFY_CONTEXT_DICT_VALUE,
            variable_name="test_obj",
            parameters={
                "attribute": "mapping",
                "key": "foo",
                "modifier": {"name": "add", "args": [2]},
            },
        )
        test_obj = object()
        fx = self.get_flow_execution(variable_mapping={"test_obj": test_obj})

        with patch.object(fx.context, "modify_context_dict_value") as mock_modify:
            next_step = step.execute(fx)
            mock_modify.assert_called_once()
            _, kwargs = mock_modify.call_args
            self.assertEqual(kwargs["key"], test_obj)
            self.assertEqual(kwargs["attribute"], "mapping")
            self.assertEqual(kwargs["dict_key"], "foo")
            self.assertEqual(kwargs["modifier"](3), 5)
        self.assertEqual(next_step, fx.get_next_child(step))

    @patch("flows.flow_execution.FlowExecution.get_service_function")
    def test_execute_call_service_function(self, mock_get_service):
        mock_service = MagicMock(return_value="result_value")
        mock_get_service.return_value = mock_service

        step = FlowStepDefinitionFactory(
            flow=self.flow_def,
            action=FlowActionChoices.CALL_SERVICE_FUNCTION,
            variable_name="test_service",
            parameters={"arg1": 1, "arg2": "test", "result_variable": "result"},
        )

        fx = self.get_flow_execution()
        next_step = step.execute(fx)

        mock_get_service.assert_called_once_with("test_service")
        mock_service.assert_called_once_with(
            fx, arg1=1, arg2="test", result_variable="result"
        )
        self.assertEqual(fx.get_variable("result"), "result_value")
        self.assertEqual(next_step, fx.get_next_child(step))

    def test_execute_emit_flow_event(self):
        step = FlowStepDefinitionFactory(
            flow=self.flow_def,
            action=FlowActionChoices.EMIT_FLOW_EVENT,
            variable_name="test_event",
            parameters={"data": {"key": "value"}},
        )

        fx = self.get_flow_execution(flow_stack=FlowStack(trigger_registry=MagicMock()))

        next_step = step.execute(fx)

        event = fx.context.flow_events["test_event"]
        self.assertEqual(event.event_type, "test_event")
        self.assertEqual(event.data, {"key": "value"})
        self.assertIs(event.source, fx)

        fx.flow_stack.trigger_registry.process_event.assert_called_once_with(
            event, fx.flow_stack, fx.context
        )
        self.assertEqual(next_step, fx.get_next_child(step))

    def test_execute_unknown_action(self):
        step = FlowStepDefinitionFactory(
            flow=self.flow_def,
            action="INVALID_ACTION",
        )
        fx = self.get_flow_execution()
        next_step = step.execute(fx)
        self.assertEqual(next_step, fx.get_next_child(step))
