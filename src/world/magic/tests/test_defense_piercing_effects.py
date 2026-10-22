"""Piercing mechanics reach the same effect description a player reads (#4575)."""

from django.test import TestCase

from world.conditions.factories import ConditionTemplateFactory, DamageTypeFactory
from world.magic.factories import (
    BinaryEffectTypeFactory,
    TechniqueAppliedConditionFactory,
    TechniqueDamageProfileFactory,
    TechniqueFactory,
)
from world.magic.serializers import DamageEffectSerializer
from world.magic.services.technique_effects import summarize_technique_effects


class DefensePiercingEffectTests(TestCase):
    """Keep per-hit piercing separate from the whole-technique ward property."""

    def test_mixed_hits_describe_their_piercing_and_conditions(self):
        technique = TechniqueFactory(effect_type=BinaryEffectTypeFactory(), damage_profile=False)
        TechniqueDamageProfileFactory(
            technique=technique,
            damage_type=DamageTypeFactory(name="fire"),
            base_damage=20,
            ignores_soak=True,
            resistance_shift=5,
            bypasses_wards=True,
        )
        TechniqueDamageProfileFactory(
            technique=technique, damage_type=DamageTypeFactory(name="cold"), base_damage=7
        )
        TechniqueAppliedConditionFactory(
            technique=technique, condition=ConditionTemplateFactory(name="Bleeding")
        )

        result = summarize_technique_effects(technique)
        rows = DamageEffectSerializer(result["damage"], many=True).data
        self.assertEqual(
            [(row["ignores_soak"], row["resistance_shift"], row["bypasses_wards"]) for row in rows],
            [(True, 5, True), (False, 0, False)],
        )
        self.assertIn(
            "One fire hit ignores armor-like protection and shifts resistance 5 points "
            "toward vulnerability.",
            result["summary"],
        )
        self.assertNotIn("One cold hit", result["summary"])
        self.assertIn(
            "The whole technique bypasses wards, including its conditions.", result["summary"]
        )
        self.assertIn("Applies Bleeding.", result["summary"])

    def test_untyped_shift_is_not_advertised_as_a_damage_bonus(self):
        technique = TechniqueFactory(effect_type=BinaryEffectTypeFactory(), damage_profile=False)
        TechniqueDamageProfileFactory(technique=technique, damage_type=None, resistance_shift=5)

        result = summarize_technique_effects(technique)

        self.assertNotIn("toward vulnerability", result["summary"])
        self.assertNotIn("bypasses wards", result["summary"])
