"""has_species, has_upbringing and matched_leaves (#4145)."""

from django.test import SimpleTestCase, TestCase

from evennia_extensions.factories import CharacterFactory
from world.character_creation.factories import OriginTemplateFactory, OriginTemplateSlotFactory
from world.character_creation.models import CharacterOriginSlot
from world.character_sheets.factories import CharacterSheetFactory
from world.predicates.predicates import CharacterPredicateContext, evaluate, matched_leaves
from world.predicates.types import PredicateContext
from world.predicates.validation import validate_predicate_tree
from world.species.factories import SpeciesFactory


class _StubContext(PredicateContext):
    """Leaf truth keyed by leaf name."""

    def __init__(self, truth: dict[str, bool]) -> None:
        self.truth = truth

    def has_leaf(self, leaf: str, **_params: object) -> bool:
        return self.truth[leaf]


def _leaf(name: str) -> dict:
    return {"leaf": name, "params": {}}


class LeafTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.species = SpeciesFactory()
        cls.other_species = SpeciesFactory()
        cls.character = CharacterFactory()
        cls.sheet = CharacterSheetFactory(character=cls.character, species=cls.species)
        cls.ctx = CharacterPredicateContext(cls.character)
        cls.slot = OriginTemplateSlotFactory()

    def test_has_species_by_id(self) -> None:
        yes = {"leaf": "has_species", "params": {"species_id": self.species.pk}}
        no = {"leaf": "has_species", "params": {"species_id": self.other_species.pk}}
        self.assertTrue(evaluate(yes, self.ctx))
        self.assertFalse(evaluate(no, self.ctx))

    def test_has_upbringing(self) -> None:
        rule = {
            "leaf": "has_upbringing",
            "params": {"origin_template_id": self.slot.template_id},
        }
        self.assertFalse(evaluate(rule, self.ctx))
        CharacterOriginSlot.objects.create(sheet=self.sheet, slot=self.slot, value="x")
        self.assertTrue(evaluate(rule, self.ctx))
        other = {
            "leaf": "has_upbringing",
            "params": {"origin_template_id": OriginTemplateFactory().pk},
        }
        self.assertFalse(evaluate(other, self.ctx))


class ValidationTests(SimpleTestCase):
    def test_new_leaves_validate_with_int_params(self) -> None:
        rule = {
            "op": "AND",
            "of": [
                {"leaf": "has_species", "params": {"species_id": 3}},
                {"leaf": "has_upbringing", "params": {"origin_template_id": 4}},
            ],
        }
        self.assertEqual(validate_predicate_tree(rule), [])


class MatchedLeavesTests(SimpleTestCase):
    def test_failure_is_none(self) -> None:
        ctx = _StubContext({"a": False})
        self.assertIsNone(matched_leaves(_leaf("a"), ctx))

    def test_empty_rule_is_empty_list(self) -> None:
        self.assertEqual(matched_leaves({}, _StubContext({})), [])

    def test_single_leaf(self) -> None:
        self.assertEqual(matched_leaves(_leaf("a"), _StubContext({"a": True})), [_leaf("a")])

    def test_and_returns_all_children(self) -> None:
        rule = {"op": "AND", "of": [_leaf("a"), _leaf("b")]}
        ctx = _StubContext({"a": True, "b": True})
        self.assertEqual(matched_leaves(rule, ctx), [_leaf("a"), _leaf("b")])
        self.assertIsNone(matched_leaves(rule, _StubContext({"a": True, "b": False})))

    def test_or_returns_first_true_child(self) -> None:
        rule = {"op": "OR", "of": [_leaf("a"), _leaf("b"), _leaf("c")]}
        ctx = _StubContext({"a": False, "b": True, "c": True})
        self.assertEqual(matched_leaves(rule, ctx), [_leaf("b")])
        self.assertIsNone(matched_leaves(rule, _StubContext({"a": False, "b": False, "c": False})))

    def test_not(self) -> None:
        rule = {"op": "NOT", "of": [_leaf("a")]}
        self.assertEqual(matched_leaves(rule, _StubContext({"a": False})), [])
        self.assertIsNone(matched_leaves(rule, _StubContext({"a": True})))

    def test_malformed_raises_like_evaluate(self) -> None:
        with self.assertRaises(ValueError):
            matched_leaves({"op": "NOT", "of": []}, _StubContext({}))
        with self.assertRaises(ValueError):
            matched_leaves({"op": "XOR", "of": []}, _StubContext({}))
