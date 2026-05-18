"""Tests for the missions shared predicate evaluator (Phase 0).

The evaluator walks an AND/OR/NOT rule tree whose leaves test the acting
character's own durable state via a ``PredicateContext``. These tests use a
tiny in-memory context so the structural behaviour is verified independently
of any descriptor model. No database is touched here, so plain
``unittest.TestCase`` is sufficient.
"""

import unittest

from world.missions.predicates import evaluate
from world.missions.types import PredicateContext


class _StubContext:
    """Minimal PredicateContext: ``always_true`` resolves True, all else False."""

    def has_leaf(self, leaf: str, **_params: object) -> bool:
        return leaf == "always_true"


class PredicateComposeTests(unittest.TestCase):
    """Task 0.1 — AND / OR / NOT compose correctly over leaf resolution."""

    def setUp(self) -> None:
        self.ctx: PredicateContext = _StubContext()

    def test_and_or_not_compose(self) -> None:
        rule = {
            "op": "AND",
            "of": [
                {"leaf": "always_true"},
                {"op": "NOT", "of": [{"leaf": "always_false"}]},
            ],
        }
        self.assertIs(evaluate(rule, self.ctx), True)

        or_all_false = {
            "op": "OR",
            "of": [{"leaf": "always_false"}, {"leaf": "also_false"}],
        }
        self.assertIs(evaluate(or_all_false, self.ctx), False)


class PredicateContractTests(unittest.TestCase):
    """Task 0.2 — empty / malformed rule contract is locked.

    The Task 0.1 evaluator already satisfies these; the tests pin the
    contract so later phases cannot regress empty-tree or unknown-op
    behaviour.
    """

    def setUp(self) -> None:
        self.ctx: PredicateContext = _StubContext()

    def test_empty_rule_is_true(self) -> None:
        self.assertIs(evaluate({}, self.ctx), True)

    def test_empty_and_is_true(self) -> None:
        self.assertIs(evaluate({"op": "AND", "of": []}, self.ctx), True)

    def test_empty_or_is_false(self) -> None:
        self.assertIs(evaluate({"op": "OR", "of": []}, self.ctx), False)

    def test_unknown_op_raises_value_error(self) -> None:
        with self.assertRaises(ValueError):
            evaluate({"op": "BOGUS", "of": []}, self.ctx)
