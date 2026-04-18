from dataclasses import dataclass
from types import SimpleNamespace

from django.test import TestCase

from flows.filters.errors import FilterPathError
from flows.filters.evaluator import evaluate_filter


@dataclass
class FakePayload:
    target: object
    damage_type: str
    amount: int


class FilterEvaluatorTests(TestCase):
    def test_eq_true(self) -> None:
        payload = FakePayload(target=None, damage_type="fire", amount=10)
        f = {"path": "damage_type", "op": "==", "value": "fire"}
        self.assertTrue(evaluate_filter(f, payload, self_ref=None))

    def test_eq_false(self) -> None:
        payload = FakePayload(target=None, damage_type="cold", amount=10)
        f = {"path": "damage_type", "op": "==", "value": "fire"}
        self.assertFalse(evaluate_filter(f, payload, self_ref=None))

    def test_and_combines(self) -> None:
        payload = FakePayload(target=None, damage_type="fire", amount=10)
        f = {
            "and": [
                {"path": "damage_type", "op": "==", "value": "fire"},
                {"path": "amount", "op": ">=", "value": 5},
            ]
        }
        self.assertTrue(evaluate_filter(f, payload, self_ref=None))

    def test_not_negates(self) -> None:
        payload = FakePayload(target=None, damage_type="fire", amount=10)
        f = {"not": {"path": "damage_type", "op": "==", "value": "cold"}}
        self.assertTrue(evaluate_filter(f, payload, self_ref=None))

    def test_in_operator(self) -> None:
        payload = FakePayload(target=None, damage_type="fire", amount=10)
        f = {"path": "damage_type", "op": "in", "value": ["fire", "flame"]}
        self.assertTrue(evaluate_filter(f, payload, self_ref=None))

    def test_contains_operator(self) -> None:
        payload = SimpleNamespace(tags=["silvered", "sharp"])
        f = {"path": "tags", "op": "contains", "value": "silvered"}
        self.assertTrue(evaluate_filter(f, payload, self_ref=None))

    def test_dotted_path_traversal(self) -> None:
        tech = SimpleNamespace(affinity="abyssal")
        source = SimpleNamespace(type="technique", technique=tech)
        payload = SimpleNamespace(source=source)
        f = {"path": "source.technique.affinity", "op": "==", "value": "abyssal"}
        self.assertTrue(evaluate_filter(f, payload, self_ref=None))

    def test_self_placeholder(self) -> None:
        owner = SimpleNamespace(covenant="iron", id=42)
        payload = SimpleNamespace(attacker=SimpleNamespace(covenant="iron"))
        f = {"path": "attacker.covenant", "op": "==", "value": "self.covenant"}
        self.assertTrue(evaluate_filter(f, payload, self_ref=owner))

    def test_unknown_path_raises(self) -> None:
        payload = FakePayload(target=None, damage_type="fire", amount=10)
        f = {"path": "nonexistent_attr", "op": "==", "value": "x"}
        with self.assertRaises(FilterPathError):
            evaluate_filter(f, payload, self_ref=None)

    def test_has_property(self) -> None:
        payload = SimpleNamespace(
            attacker=SimpleNamespace(has_property=lambda name: name == "flesh-and-blood")
        )
        f = {"path": "attacker", "op": "has_property", "value": "flesh-and-blood"}
        self.assertTrue(evaluate_filter(f, payload, self_ref=None))

    def test_empty_filter_matches(self) -> None:
        payload = FakePayload(target=None, damage_type="fire", amount=10)
        self.assertTrue(evaluate_filter(None, payload, self_ref=None))
        self.assertTrue(evaluate_filter({}, payload, self_ref=None))

    def test_self_placeholder_on_path(self) -> None:
        owner = SimpleNamespace(covenant="iron")
        payload = SimpleNamespace(attacker=SimpleNamespace(covenant="iron"))
        f = {"path": "self.covenant", "op": "==", "value": "iron"}
        self.assertTrue(evaluate_filter(f, payload, self_ref=owner))

    def test_unknown_operator_raises(self) -> None:
        payload = FakePayload(target=None, damage_type="fire", amount=10)
        f = {"path": "damage_type", "op": "~=", "value": "fire"}
        with self.assertRaises(FilterPathError):
            evaluate_filter(f, payload, self_ref=None)

    def test_has_property_missing_method_raises(self) -> None:
        payload = SimpleNamespace(attacker=SimpleNamespace())
        f = {"path": "attacker", "op": "has_property", "value": "anything"}
        with self.assertRaises(FilterPathError):
            evaluate_filter(f, payload, self_ref=None)
