"""Authored defense piercing at the combat damage and cast seams."""

from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase

from world.combat.factories import CombatOpponentFactory, CombatParticipantFactory
from world.combat.services import apply_damage_to_opponent, apply_damage_to_participant
from world.combat.tests.penetration_helpers import _build_resolver, _ledger
from world.conditions.factories import (
    ConditionResistanceModifierFactory,
    ConditionTemplateFactory,
    DamageSuccessLevelMultiplierFactory,
    DamageTypeFactory,
)
from world.conditions.services import apply_condition
from world.magic.factories import TechniqueDamageProfileFactory
from world.vitals.factories import CharacterVitalsFactory


class DefensePiercingDamageTests(TestCase):
    def test_shift_signed_resistance_once_for_both_damage_seams(self):
        for resistance, expected in ((8, 17), (0, 25), (-4, 29)):
            for pc in (False, True):
                with self.subTest(resistance=resistance, pc=pc):
                    damage_type = DamageTypeFactory()
                    condition = ConditionTemplateFactory()
                    ConditionResistanceModifierFactory(
                        condition=condition,
                        damage_type=damage_type,
                        modifier_value=resistance,
                    )
                    if pc:
                        target = CombatParticipantFactory()
                        CharacterVitalsFactory(
                            character_sheet=target.character_sheet,
                            health=200,
                            max_health=200,
                            base_max_health=200,
                        )
                        character = target.character_sheet.character
                        apply = apply_damage_to_participant
                    else:
                        target = CombatOpponentFactory(health=200, max_health=200, soak_value=0)
                        character = target.objectdb
                        apply = apply_damage_to_opponent
                    apply_condition(character, condition)
                    result = apply(target, 20, damage_type=damage_type, resistance_shift=5)
                    self.assertEqual(result.damage_dealt, expected)
                    self.assertEqual(
                        character.conditions.resistance_modifier(damage_type), resistance
                    )
                    ordinary = apply(target, 20, damage_type=damage_type)
                    self.assertEqual(ordinary.damage_dealt, 20 - resistance)

    def test_npc_soak_bypass_is_bounded_and_still_probes(self):
        for soak in (0, 8):
            target = CombatOpponentFactory(health=200, max_health=200, soak_value=soak)
            before = target.probing_current
            self.assertEqual(
                apply_damage_to_opponent(target, 20, ignores_soak=True).damage_dealt, 20
            )
            self.assertEqual(target.probing_current, before + 20)
            apply_damage_to_opponent(target, 20, bypass_soak=True)
            self.assertEqual(target.probing_current, before + 20)

    def test_zero_and_untyped_hits_do_not_gain_shift_damage(self):
        target = CombatOpponentFactory(health=200, max_health=200, soak_value=0)
        typed = DamageTypeFactory()
        self.assertEqual(
            apply_damage_to_opponent(
                target, 0, damage_type=typed, resistance_shift=5, bypass_pre_apply=True
            ).damage_dealt,
            0,
        )
        self.assertEqual(apply_damage_to_opponent(target, 20, resistance_shift=5).damage_dealt, 20)


class DefensePiercingWardTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        DamageSuccessLevelMultiplierFactory(
            min_success_level=2, multiplier=Decimal("1.00"), label="Full"
        )

    def test_high_threshold_bypass_row_carries_other_damage_past_ward(self):
        resolver = _build_resolver(barrier_strength=100)
        TechniqueDamageProfileFactory(
            technique=resolver.action.focused_action,
            bypasses_wards=True,
            minimum_success_level=99,
            base_damage=500,
        )
        with patch("world.combat.services.perform_check") as penetration:
            result = resolver(power=20, ledger=_ledger(20))
        penetration.assert_not_called()
        self.assertEqual(len(result.damage_results), 1)
        self.assertGreater(result.scaled_damage, 0)
        self.assertEqual(result.power_ledger.total, 20)
        resolver.action.focused_opponent_target.refresh_from_db()
        self.assertEqual(resolver.action.focused_opponent_target.barrier_strength, 100)
