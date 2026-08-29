"""Tests for the catalog-driven step-tree validation module."""

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase

from flows.catalog import ParamSpec
from flows.step_validation import _check_param_value, validate_step_tree


def _step(client_id, parent_client_id, action, variable_name="", parameters=None):
    return {
        "client_id": client_id,
        "parent_client_id": parent_client_id,
        "action": action,
        "variable_name": variable_name,
        "parameters": parameters or {},
    }


class ValidateStepTreeShapeTests(SimpleTestCase):
    def test_empty_list_is_valid(self):
        validate_step_tree([])

    def test_valid_one_root_tree_passes(self):
        steps = [
            _step("a", None, "evaluate_equals", "some_var", {"value": "1"}),
            _step("b", "a", "cancel_event"),
        ]
        validate_step_tree(steps)

    def test_duplicate_client_id_fails(self):
        steps = [
            _step("a", None, "cancel_event"),
            _step("a", "a", "cancel_event"),
        ]
        with self.assertRaises(ValidationError):
            validate_step_tree(steps)

    def test_blank_client_id_fails(self):
        steps = [_step("", None, "cancel_event")]
        with self.assertRaises(ValidationError):
            validate_step_tree(steps)

    def test_two_roots_fails(self):
        steps = [
            _step("a", None, "cancel_event"),
            _step("b", None, "cancel_event"),
        ]
        with self.assertRaises(ValidationError):
            validate_step_tree(steps)

    def test_no_root_fails(self):
        # Non-empty list where every step has a (valid) parent - no root at all.
        steps = [
            _step("a", "b", "cancel_event"),
            _step("b", "a", "cancel_event"),
        ]
        with self.assertRaises(ValidationError):
            validate_step_tree(steps)

    def test_unknown_parent_client_id_fails(self):
        steps = [
            _step("a", None, "cancel_event"),
            _step("b", "does-not-exist", "cancel_event"),
        ]
        with self.assertRaises(ValidationError):
            validate_step_tree(steps)

    def test_cycle_fails(self):
        # a is root; b and c form a cycle hanging off nothing valid overall -
        # per rule 3 there must be exactly one root, so make b/c cycle while
        # a is the (only) declared root but unreachable from the cycle check,
        # which walks parents from every node regardless of root status.
        steps = [
            _step("a", None, "cancel_event"),
            _step("b", "c", "cancel_event"),
            _step("c", "b", "cancel_event"),
        ]
        with self.assertRaises(ValidationError):
            validate_step_tree(steps)

    def test_unknown_action_fails(self):
        steps = [_step("a", None, "not_a_real_action")]
        with self.assertRaises(ValidationError):
            validate_step_tree(steps)


class ValidateStepTreeSpecTests(SimpleTestCase):
    def test_missing_variable_name_on_evaluate_equals_fails(self):
        steps = [_step("a", None, "evaluate_equals", "", {"value": "1"})]
        with self.assertRaises(ValidationError):
            validate_step_tree(steps)

    def test_missing_required_param_fails(self):
        # modify_payload requires field, op, and value.
        steps = [_step("a", None, "modify_payload", "", {"field": "hp", "value": 1})]
        with self.assertRaises(ValidationError):
            validate_step_tree(steps)

    def test_op_not_in_choices_fails(self):
        steps = [
            _step(
                "a",
                None,
                "modify_payload",
                "",
                {"field": "hp", "op": "not-a-choice", "value": 1},
            )
        ]
        with self.assertRaises(ValidationError):
            validate_step_tree(steps)

    def test_modify_payload_value_accepts_any_json(self):
        steps = [
            _step(
                "a",
                None,
                "modify_payload",
                "",
                {"field": "hp", "op": "set", "value": {"nested": [1, 2, 3]}},
            )
        ]
        validate_step_tree(steps)

    def test_wrong_type_for_str_param_fails(self):
        # set_context_value's 'attribute' param is a required str.
        steps = [
            _step(
                "a",
                None,
                "set_context_value",
                "some_var",
                {"attribute": 123, "value": "x"},
            )
        ]
        with self.assertRaises(ValidationError):
            validate_step_tree(steps)

    def test_str_param_rejects_bool_value(self):
        # set_context_value's 'attribute' param is a required str.
        steps = [
            _step(
                "a",
                None,
                "set_context_value",
                "some_var",
                {"attribute": True, "value": "x"},
            )
        ]
        with self.assertRaises(ValidationError):
            validate_step_tree(steps)

    def test_unknown_parameter_key_rejected_when_not_allowed(self):
        steps = [
            _step(
                "a",
                None,
                "modify_payload",
                "",
                {"field": "hp", "op": "set", "value": 1, "bogus_extra": True},
            )
        ]
        with self.assertRaises(ValidationError):
            validate_step_tree(steps)

    def test_service_function_extra_params_are_unchecked(self):
        # call_service_function allows_extra_params, and result_variable is
        # itself a declared (optional) param - an "@var" reference string is
        # accepted for any extra kwarg since extras aren't type-checked.
        steps = [
            _step(
                "a",
                None,
                "call_service_function",
                "some_service_function",
                {"result_variable": "out", "amount": "@some_var"},
            )
        ]
        validate_step_tree(steps)

    def test_reference_string_bypasses_type_check_when_accepts_reference(self):
        # emit_flow_event's 'data' param is dict-typed with accepts_reference
        # True (default) - a plain dict-typed value must be a dict, but an
        # "@" reference string bypasses that type check.
        steps = [
            _step(
                "a",
                None,
                "emit_flow_event",
                "some_event",
                {"data": "@other_var"},
            )
        ]
        validate_step_tree(steps)

    def test_dict_type_rejects_non_dict_non_reference_value(self):
        steps = [
            _step(
                "a",
                None,
                "emit_flow_event",
                "some_event",
                {"data": "not-a-dict-and-not-a-reference"},
            )
        ]
        with self.assertRaises(ValidationError):
            validate_step_tree(steps)

    def test_int_type_accepts_int_rejects_bool(self):
        param = ParamSpec(name="n", type="int", accepts_reference=False)
        _check_param_value("a", param, 5)
        with self.assertRaises(ValidationError):
            _check_param_value("a", param, True)
        with self.assertRaises(ValidationError):
            _check_param_value("a", param, 5.0)

    def test_float_type_accepts_int_and_float_rejects_bool(self):
        param = ParamSpec(name="n", type="float", accepts_reference=False)
        _check_param_value("a", param, 5)
        _check_param_value("a", param, 5.5)
        with self.assertRaises(ValidationError):
            _check_param_value("a", param, False)

    def test_bool_type_accepts_only_bool(self):
        param = ParamSpec(name="flag", type="bool", accepts_reference=False)
        _check_param_value("a", param, True)
        with self.assertRaises(ValidationError):
            _check_param_value("a", param, 1)

    def test_reference_string_rejected_when_accepts_reference_false(self):
        # modify_payload's 'op' param has accepts_reference=False and is
        # restricted to choices, so an "@" string must not bypass the
        # choices check.
        steps = [
            _step(
                "a",
                None,
                "modify_payload",
                "",
                {"field": "hp", "op": "@some_var", "value": 1},
            )
        ]
        with self.assertRaises(ValidationError):
            validate_step_tree(steps)
