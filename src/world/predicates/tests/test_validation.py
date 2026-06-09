"""validate_predicate_tree — server-side rule well-formedness (#870).

Pure structural tests (no DB): the validator inspects the resolver
registry's signatures, never evaluates against a character. Mirrors the
FE builder's validatePredicate checks plus the param-type layer.
"""

from django.test import SimpleTestCase

from world.predicates.validation import validate_predicate_tree


class ValidTreeTests(SimpleTestCase):
    def test_empty_rule_is_valid(self) -> None:
        self.assertEqual(validate_predicate_tree({}), [])

    def test_well_formed_leaf_is_valid(self) -> None:
        rule = {"leaf": "min_character_level", "params": {"level": 3}}
        self.assertEqual(validate_predicate_tree(rule), [])

    def test_nested_groups_are_valid(self) -> None:
        rule = {
            "op": "AND",
            "of": [
                {"leaf": "min_trait", "params": {"trait": "strength", "value": 2}},
                {
                    "op": "NOT",
                    "of": [{"leaf": "has_distinction", "params": {"slug": "craven"}}],
                },
                {"op": "OR", "of": []},
            ],
        }
        self.assertEqual(validate_predicate_tree(rule), [])

    def test_new_870_leaves_are_known(self) -> None:
        rule = {
            "op": "AND",
            "of": [
                {"leaf": "min_org_rank", "params": {"org": "Guild", "rank": 2}},
                {"leaf": "min_resonance_level", "params": {"resonance": "Umbra", "amount": 5}},
                {"leaf": "is_member_of_society", "params": {"society": "The Compact"}},
            ],
        }
        self.assertEqual(validate_predicate_tree(rule), [])


class MalformedTreeTests(SimpleTestCase):
    def _assert_one_error(self, rule: object, fragment: str) -> None:
        errors = validate_predicate_tree(rule)
        self.assertTrue(errors, "expected validation errors, got none")
        self.assertIn(fragment, "\n".join(errors))

    def test_non_dict_root(self) -> None:
        self._assert_one_error(["not", "a", "node"], "must be an object")

    def test_non_dict_child(self) -> None:
        self._assert_one_error({"op": "AND", "of": ["bogus"]}, "must be an object")

    def test_unknown_op(self) -> None:
        self._assert_one_error({"op": "XOR", "of": []}, "unknown op")

    def test_of_not_a_list(self) -> None:
        self._assert_one_error({"op": "AND", "of": "nope"}, "'of' must be a list")

    def test_not_requires_exactly_one_operand(self) -> None:
        self._assert_one_error({"op": "NOT", "of": [{}, {}]}, "exactly one operand")

    def test_unknown_leaf(self) -> None:
        self._assert_one_error({"leaf": "no_such_leaf", "params": {}}, "unknown leaf")

    def test_empty_leaf_name(self) -> None:
        self._assert_one_error({"leaf": "", "params": {}}, "non-empty string")

    def test_node_neither_op_nor_leaf(self) -> None:
        self._assert_one_error({"banana": True}, "empty, an op group, or a leaf")

    def test_missing_required_param(self) -> None:
        self._assert_one_error({"leaf": "min_character_level", "params": {}}, "is required")

    def test_blank_param_rejected(self) -> None:
        self._assert_one_error({"leaf": "has_distinction", "params": {"slug": ""}}, "is required")

    def test_mistyped_param_rejected(self) -> None:
        # The FE coerces before save; raw API writers don't — "3" must 400.
        self._assert_one_error(
            {"leaf": "min_character_level", "params": {"level": "3"}}, "must be of type int"
        )

    def test_bool_does_not_satisfy_int_param(self) -> None:
        # bool subclasses int in Python; the validator must not let
        # ``true`` slip into an int-typed param.
        self._assert_one_error(
            {"leaf": "min_character_level", "params": {"level": True}}, "must be of type int"
        )

    def test_unexpected_extra_param_rejected(self) -> None:
        # Extras would TypeError at resolver call time deep in availability.
        self._assert_one_error(
            {"leaf": "min_character_level", "params": {"level": 1, "bogus": 1}},
            "unexpected param",
        )

    def test_params_not_a_dict(self) -> None:
        self._assert_one_error({"leaf": "min_character_level", "params": [1]}, "must be an object")

    def test_error_paths_locate_the_bad_node(self) -> None:
        rule = {"op": "AND", "of": [{}, {"leaf": "no_such_leaf", "params": {}}]}
        errors = validate_predicate_tree(rule)
        self.assertEqual(len(errors), 1)
        self.assertIn("root.AND[1]", errors[0])
