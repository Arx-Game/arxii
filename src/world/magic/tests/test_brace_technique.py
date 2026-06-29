"""Unit test for BraceTechniqueFactory — brace/steel technique authoring pattern (#1580).

Asserts that the factory produces a valid Technique with:
- SELF-targeted applied condition
- secondary-action eligibility (combo_opening_probing=None, no combo probing)
- an attached ConditionResistanceModifier with positive modifier_value
- UNTIL_END_OF_COMBAT condition duration (no SCENE tier today)
"""

from typing import ClassVar

from django.test import TestCase

from world.conditions.constants import DurationType
from world.conditions.models import ConditionResistanceModifier
from world.magic.constants import GiftKind
from world.magic.factories import BraceTechniqueFactory, GiftFactory
from world.magic.models import Technique, TechniqueAppliedCondition


class BraceTechniqueFactoryTests(TestCase):
    """BraceTechniqueFactory produces the brace/steel secondary-action pattern."""

    technique: ClassVar[Technique]

    @classmethod
    def setUpTestData(cls) -> None:
        gift = GiftFactory(kind=GiftKind.MINOR)
        cls.technique = BraceTechniqueFactory(gift=gift, name="Species Brace")

    # ------------------------------------------------------------------
    # SELF-targeted applied condition
    # ------------------------------------------------------------------

    def test_has_applied_condition_with_self_target(self) -> None:
        """The technique's applied conditions include exactly one SELF-targeted row."""
        apps = TechniqueAppliedCondition.objects.filter(technique=self.technique)
        self.assertEqual(apps.count(), 1)
        self.assertEqual(apps.get().target_kind, "self")

    # ------------------------------------------------------------------
    # Secondary-action eligibility
    # ------------------------------------------------------------------

    def test_secondary_action_eligible(self) -> None:
        """combo_opening_probing=None marks the technique secondary-action eligible.

        A technique with combo_opening_probing=None carries no probing when
        declared in a passive slot, making it usable as a secondary action
        without opening combo gates — the canonical secondary-action pattern.
        """
        self.assertIsNone(self.technique.combo_opening_probing)

    # ------------------------------------------------------------------
    # ConditionResistanceModifier (positive modifier_value)
    # ------------------------------------------------------------------

    def test_resistance_condition_has_positive_modifier_value(self) -> None:
        """The applied condition carries a ConditionResistanceModifier with positive value."""
        app = TechniqueAppliedCondition.objects.select_related("condition").get(
            technique=self.technique
        )
        resist_mod = ConditionResistanceModifier.objects.get(condition=app.condition, stage=None)
        self.assertGreater(resist_mod.modifier_value, 0)

    # ------------------------------------------------------------------
    # UNTIL_END_OF_COMBAT duration (scene-length approximation)
    # ------------------------------------------------------------------

    def test_condition_uses_until_end_of_combat_duration(self) -> None:
        """The resistance condition uses UNTIL_END_OF_COMBAT (scene-length proxy today)."""
        app = TechniqueAppliedCondition.objects.select_related("condition").get(
            technique=self.technique
        )
        self.assertEqual(app.condition.default_duration_type, DurationType.UNTIL_END_OF_COMBAT)

    # ------------------------------------------------------------------
    # Custom tunables: resist_amount and damage_type
    # ------------------------------------------------------------------

    def test_custom_resist_amount(self) -> None:
        """A custom resist_amount is honoured on the ConditionResistanceModifier."""
        gift = GiftFactory(kind=GiftKind.MINOR)
        tech = BraceTechniqueFactory(gift=gift, brace_condition__resist_amount=40)
        app = TechniqueAppliedCondition.objects.select_related("condition").get(technique=tech)
        resist_mod = ConditionResistanceModifier.objects.get(condition=app.condition, stage=None)
        self.assertEqual(resist_mod.modifier_value, 40)
