"""Tests for relationship_gated_contributions — the directed allure engine (#1696)."""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.checks.constants import ModifierSourceKind
from world.mechanics.factories import CharacterModifierFactory
from world.relationships.factories import (
    CharacterRelationshipFactory,
    RelationshipConditionFactory,
)
from world.relationships.services import relationship_gated_contributions


class RelationshipGatedContributionsTests(TestCase):
    """A perceiver's gating relationship-condition folds the *perceived's* gated modifier in.

    Allure is directed + conditional: B's allure applies against A only when A holds a gating
    condition ("Attracted To") toward B. Counting once per gating condition makes "Very Attracted"
    stack the double with no allure-specific code.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        # A is the perceiver (does the feeling); B is the perceived (the allure-haver).
        cls.perceiver = CharacterSheetFactory()  # A
        cls.perceived = CharacterSheetFactory()  # B
        # A recognized (distinction-sourced) modifier on B; gate ITS target as "allure".
        cls.modifier = CharacterModifierFactory(character=cls.perceived, value=10)
        cls.allure_target = cls.modifier.target

    def _attracted(self, name: str = "Attracted To"):
        condition = RelationshipConditionFactory(name=name)
        condition.gates_modifiers.add(self.allure_target)
        return condition

    def test_no_relationship_returns_empty(self) -> None:
        self.assertEqual(
            relationship_gated_contributions(perceiver=self.perceiver, perceived=self.perceived),
            [],
        )

    def test_attracted_folds_perceived_allure_once(self) -> None:
        rel = CharacterRelationshipFactory(
            source=self.perceiver, target=self.perceived, is_active=True
        )
        rel.conditions.add(self._attracted())

        contribs = relationship_gated_contributions(
            perceiver=self.perceiver, perceived=self.perceived
        )

        self.assertEqual(len(contribs), 1)
        self.assertEqual(contribs[0].value, 10)
        self.assertEqual(contribs[0].source_kind, ModifierSourceKind.RELATIONSHIP)

    def test_very_attracted_stacks_the_double(self) -> None:
        rel = CharacterRelationshipFactory(
            source=self.perceiver, target=self.perceived, is_active=True
        )
        rel.conditions.add(self._attracted("Attracted To"))
        rel.conditions.add(self._attracted("Very Attracted"))

        contribs = relationship_gated_contributions(
            perceiver=self.perceiver, perceived=self.perceived
        )

        # Two allure-gating conditions → allure counted twice (the double).
        self.assertEqual(len(contribs), 2)
        self.assertEqual(sum(c.value for c in contribs), 20)

    def test_inactive_relationship_is_ignored(self) -> None:
        rel = CharacterRelationshipFactory(
            source=self.perceiver, target=self.perceived, is_active=False
        )
        rel.conditions.add(self._attracted())

        self.assertEqual(
            relationship_gated_contributions(perceiver=self.perceiver, perceived=self.perceived),
            [],
        )

    def test_directed_one_way_only(self) -> None:
        # A attracted to B (A→B). The reverse query (B perceives A) sees no relationship.
        rel = CharacterRelationshipFactory(
            source=self.perceiver, target=self.perceived, is_active=True
        )
        rel.conditions.add(self._attracted())

        self.assertEqual(
            relationship_gated_contributions(perceiver=self.perceived, perceived=self.perceiver),
            [],
        )

    def test_condition_without_gated_modifier_contributes_nothing(self) -> None:
        rel = CharacterRelationshipFactory(
            source=self.perceiver, target=self.perceived, is_active=True
        )
        rel.conditions.add(RelationshipConditionFactory(name="Trusts"))  # gates nothing

        self.assertEqual(
            relationship_gated_contributions(perceiver=self.perceiver, perceived=self.perceived),
            [],
        )
