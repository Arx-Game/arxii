"""Tests for condition-damage interactions wired into the combat damage path (#2018)."""

from __future__ import annotations

from django.test import TestCase

from world.combat.factories import CombatOpponentFactory
from world.combat.services import apply_damage_to_opponent
from world.conditions.factories import (
    ConditionDamageInteractionFactory,
    ConditionInstanceFactory,
    ConditionTemplateFactory,
    DamageTypeFactory,
)
from world.conditions.models import ConditionInstance


class OpponentDamageInteractionTests(TestCase):
    """Tests that apply_damage_to_opponent fires condition-damage interactions."""

    def setUp(self):
        self.lightning = DamageTypeFactory(name="Lightning-test-opp")
        self.wet = ConditionTemplateFactory(name="Wet-test-opp")

    def test_interaction_amplifies_damage_and_consumes_condition(self):
        """Wet + Lightning = +50% damage, removes Wet."""
        opponent = CombatOpponentFactory(health=10000, max_health=10000, soak_value=0)

        ConditionInstanceFactory(target=opponent.objectdb, condition=self.wet)
        ConditionDamageInteractionFactory(
            condition=self.wet,
            damage_type=self.lightning,
            damage_modifier_percent=50,
            removes_condition=True,
        )

        result = apply_damage_to_opponent(opponent, 100, damage_type=self.lightning)

        # 100 base, +50% = 150
        self.assertEqual(result.damage_dealt, 150)
        self.assertIsNotNone(result.damage_interaction)
        self.assertEqual(result.damage_interaction.damage_modifier_percent, 50)
        # Condition was consumed
        self.assertEqual(
            ConditionInstance.objects.filter(target=opponent.objectdb, condition=self.wet).count(),
            0,
        )

    def test_baseline_without_condition(self):
        """Without Wet, Lightning damage is unmodified and no interaction fires."""
        opponent = CombatOpponentFactory(health=10000, max_health=10000, soak_value=0)

        result = apply_damage_to_opponent(opponent, 100, damage_type=self.lightning)

        self.assertEqual(result.damage_dealt, 100)
        # Resolver ran but found no interactions
        self.assertIsNotNone(result.damage_interaction)
        self.assertEqual(len(result.damage_interaction.fired_interactions), 0)

    def test_dampening_reduces_damage_silently(self):
        """Wet + Fire = -30% damage, no transition (condition not consumed)."""
        fire = DamageTypeFactory(name="Fire-test-opp-dampen")
        opponent = CombatOpponentFactory(health=10000, max_health=10000, soak_value=0)

        ConditionInstanceFactory(target=opponent.objectdb, condition=self.wet)
        ConditionDamageInteractionFactory(
            condition=self.wet,
            damage_type=fire,
            damage_modifier_percent=-30,
            removes_condition=False,
        )

        result = apply_damage_to_opponent(opponent, 100, damage_type=fire)

        # 100 * 0.7 = 70
        self.assertEqual(result.damage_dealt, 70)
        self.assertIsNotNone(result.damage_interaction)
        # No transition interactions (no removal/apply)
        transition_interactions = [
            i
            for i in result.damage_interaction.fired_interactions
            if i.removes_condition or i.applies_condition is not None
        ]
        self.assertEqual(len(transition_interactions), 0)
        # Condition NOT consumed
        self.assertEqual(
            ConditionInstance.objects.filter(target=opponent.objectdb, condition=self.wet).count(),
            1,
        )


class ParticipantDamageInteractionTests(TestCase):
    """Tests that apply_damage_to_participant fires condition-damage interactions."""

    def setUp(self):
        self.lightning = DamageTypeFactory(name="Lightning-test-part")
        self.wet = ConditionTemplateFactory(name="Wet-test-part")

    def test_interaction_amplifies_participant_damage(self):
        """Wet + Lightning = +50% damage on a PC participant."""
        from world.combat.factories import CombatParticipantFactory
        from world.combat.services import apply_damage_to_participant
        from world.vitals.factories import CharacterVitalsFactory

        participant = CombatParticipantFactory()
        character = participant.character_sheet.character
        CharacterVitalsFactory(
            character_sheet=participant.character_sheet,
            health=10000,
            max_health=10000,
            base_max_health=10000,
        )

        ConditionInstanceFactory(target=character, condition=self.wet)
        ConditionDamageInteractionFactory(
            condition=self.wet,
            damage_type=self.lightning,
            damage_modifier_percent=50,
            removes_condition=True,
        )

        result = apply_damage_to_participant(participant, 100, damage_type=self.lightning)

        # 100 base, +50% = 150
        self.assertEqual(result.damage_dealt, 150)
        self.assertIsNotNone(result.damage_interaction)
        self.assertEqual(result.damage_interaction.damage_modifier_percent, 50)
