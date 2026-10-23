"""Authored defense piercing at the combat damage and cast seams."""

from dataclasses import replace
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase

from world.checks.factories import CheckTypeFactory
from world.combat.factories import CombatOpponentFactory, CombatParticipantFactory
from world.combat.models import VowAddedEffectFiring
from world.combat.services import apply_damage_to_opponent, apply_damage_to_participant
from world.combat.tests.penetration_helpers import _build_resolver, _ledger
from world.conditions.factories import (
    ConditionResistanceModifierFactory,
    ConditionTemplateFactory,
    DamageSuccessLevelMultiplierFactory,
    DamageTypeFactory,
)
from world.conditions.services import apply_condition
from world.covenants.constants import VowEffectContext, VowEffectFrequency
from world.covenants.factories import (
    CovenantFactory,
    CovenantRoleFactory,
    VowAddedEffectDamageProfileFactory,
    VowAddedEffectFactory,
    engage_vow_with_thread,
)
from world.items.constants import BodyRegion, EquipmentLayer, GearArchetype
from world.items.factories import EquippedItemFactory, ItemInstanceFactory, ItemTemplateFactory
from world.magic.constants import EffectKind, TargetKind, TechniqueFunction, VitalBonusTarget
from world.magic.factories import (
    ResonanceFactory,
    SignatureMotifBonusFactory,
    TechniqueAppliedConditionFactory,
    TechniqueDamageProfileFactory,
    TechniqueFunctionTagFactory,
    ThreadFactory,
    ThreadPullEffectFactory,
)
from world.magic.models.signature import SignatureMotifBonusDamageProfile
from world.magic.specialization.models import TechniqueVariant, TechniqueVariantDamageProfile
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

    def test_pc_armor_and_thread_soak_skipped_without_wear_or_typed_resistance_loss(self):
        participant = CombatParticipantFactory()
        sheet = participant.character_sheet
        character = sheet.character
        CharacterVitalsFactory(
            character_sheet=sheet, health=200, max_health=200, base_max_health=200
        )
        template = ItemTemplateFactory(
            gear_archetype=GearArchetype.HEAVY_ARMOR,
            base_armor_soak=8,
            max_durability=30,
        )
        armor = ItemInstanceFactory(template=template, durability=30)
        EquippedItemFactory(
            character=character.sheet_data,
            item_instance=armor,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )
        character.equipped_items.invalidate()
        resonance = ResonanceFactory()
        thread = ThreadFactory(owner=sheet, resonance=resonance, level=10)
        ThreadPullEffectFactory(
            target_kind=thread.target_kind,
            resonance=resonance,
            tier=0,
            min_thread_level=0,
            effect_kind=EffectKind.VITAL_BONUS,
            flat_bonus_amount=None,
            vital_bonus_amount=3,
            vital_target=VitalBonusTarget.DAMAGE_TAKEN_REDUCTION,
        )
        damage_type = DamageTypeFactory()
        condition = ConditionTemplateFactory()
        ConditionResistanceModifierFactory(
            condition=condition, damage_type=damage_type, modifier_value=4
        )
        apply_condition(character, condition)
        character.threads.invalidate()
        result = apply_damage_to_participant(
            participant, 20, damage_type=damage_type, ignores_soak=True
        )
        self.assertEqual(result.damage_dealt, 16)
        armor.refresh_from_db()
        self.assertEqual(armor.durability, 30)
        control = apply_damage_to_participant(participant, 20, damage_type=damage_type)
        self.assertLess(control.damage_dealt, 16)


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
            damage_type=DamageTypeFactory(),
            minimum_success_level=99,
            base_damage=500,
        )
        bleeding = ConditionTemplateFactory(name="Piercing Bleeding")
        TechniqueAppliedConditionFactory(
            technique=resolver.action.focused_action, condition=bleeding
        )
        with patch("world.combat.services.perform_check") as penetration:
            result = resolver(power=20, ledger=_ledger(20))
        self.assertEqual(len(result.applied_conditions), 1)
        penetration.assert_not_called()
        self.assertEqual(len(result.damage_results), 1)
        self.assertGreater(result.scaled_damage, 0)
        self.assertEqual(result.power_ledger.total, 20)
        resolver.action.focused_opponent_target.refresh_from_db()
        self.assertEqual(resolver.action.focused_opponent_target.barrier_strength, 100)

    def test_active_signature_provides_cast_wide_bypass(self):
        resolver = _build_resolver(barrier_strength=100)
        bonus = SignatureMotifBonusFactory()
        SignatureMotifBonusDamageProfile.objects.create(
            signature_bonus=bonus, bypasses_wards=True, base_damage=7
        )
        character = resolver.participant.character_sheet.character
        ThreadFactory(
            owner=resolver.participant.character_sheet,
            target_kind=TargetKind.TECHNIQUE,
            target_trait=None,
            target_technique=resolver.action.focused_action,
            resonance=bonus.required_resonance,
            signature_bonus=bonus,
            level=10,
        )
        character.threads.invalidate()
        with patch("world.combat.services.perform_check") as penetration:
            result = resolver(power=20, ledger=_ledger(20))
        penetration.assert_not_called()
        self.assertEqual(len(result.damage_results), 2)

    def test_resolved_variant_replaces_parent_profiles_for_bypass_and_damage(self):
        resolver = _build_resolver(barrier_strength=100)
        technique = resolver.action.focused_action
        resonance = ResonanceFactory()
        variant = TechniqueVariant.objects.create(
            parent_technique=technique, resonance=resonance, unlock_thread_level=1
        )
        TechniqueVariantDamageProfile.objects.create(
            variant=variant, bypasses_wards=True, base_damage=7, minimum_success_level=1
        )
        ThreadFactory(
            owner=resolver.participant.character_sheet,
            target_kind=TargetKind.GIFT,
            target_trait=None,
            target_gift=technique.gift,
            resonance=resonance,
            level=10,
        )
        resolver.participant.character_sheet.character.threads.invalidate()
        with patch("world.combat.services.perform_check") as penetration:
            result = resolver(power=20, ledger=_ledger(20))
        penetration.assert_not_called()
        self.assertEqual(len(result.damage_results), 1)
        self.assertEqual(result.scaled_damage, 7)

    def test_ward_bypass_preserves_failed_offense_gates(self):
        resolver = _build_resolver(barrier_strength=100, offense_sl=-10)
        profile = resolver.action.focused_action.damage_profiles.get()
        profile.bypasses_wards = True
        profile.save(update_fields=["bypasses_wards"])
        TechniqueAppliedConditionFactory(
            technique=resolver.action.focused_action,
            condition=ConditionTemplateFactory(name="Failed Bleeding"),
        )
        with patch("world.combat.services.perform_check") as penetration:
            result = resolver(power=20, ledger=_ledger(20))
        penetration.assert_not_called()
        self.assertEqual(result.scaled_damage, 0)
        self.assertEqual(result.applied_conditions, [])


class DefensePiercingVowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        DamageSuccessLevelMultiplierFactory(
            min_success_level=2, multiplier=Decimal("1.00"), label="Full"
        )

    def _vow_cast(self, *, offense_sl=2, minimum_success_level=1):
        resolver = replace(
            _build_resolver(barrier_strength=100, offense_sl=offense_sl),
            offense_check_type=CheckTypeFactory(),
        )
        technique = resolver.action.focused_action
        TechniqueFunctionTagFactory(technique=technique, function=TechniqueFunction.HOLD)
        role = CovenantRoleFactory()
        covenant = CovenantFactory(covenant_type=role.covenant_type)
        engage_vow_with_thread(
            resolver.participant.character_sheet, role, covenant=covenant, thread_level=3
        )
        resolver.participant.character_sheet.character.threads.invalidate()
        effect = VowAddedEffectFactory(
            covenant_role=role,
            cast_context=VowEffectContext.IN_COMBAT,
            frequency=VowEffectFrequency.ONCE_PER_FIGHT,
        )
        damage_type = DamageTypeFactory()
        VowAddedEffectDamageProfileFactory(
            effect=effect,
            damage_type=damage_type,
            base_damage=20,
            ignores_soak=True,
            resistance_shift=5,
            bypasses_wards=True,
            minimum_success_level=minimum_success_level,
        )
        condition = ConditionTemplateFactory()
        ConditionResistanceModifierFactory(
            condition=condition, damage_type=damage_type, modifier_value=8
        )
        target = resolver.action.focused_opponent_target
        target.soak_value = 8
        target.save(update_fields=["soak_value"])
        apply_condition(target.objectdb, condition)
        TechniqueAppliedConditionFactory(
            technique=technique, condition=ConditionTemplateFactory(name="Vow Piercing Bleeding")
        )
        return resolver, effect

    def test_vow_profile_pierces_all_defenses_and_carries_bleeding_then_is_spent(self):
        resolver, effect = self._vow_cast()
        with patch.object(
            type(resolver), "_apply_penetration", return_value=(_ledger(0), True)
        ) as penetration:
            result = resolver(power=20, ledger=_ledger(20))
        penetration.assert_not_called()
        self.assertEqual(len(result.damage_results), 2)
        self.assertEqual(result.damage_results[-1].damage_dealt, 17)
        self.assertEqual(len(result.applied_conditions), 1)
        self.assertEqual(VowAddedEffectFiring.objects.filter(effect=effect).count(), 1)
        with patch.object(
            type(resolver), "_apply_penetration", return_value=(_ledger(0), True)
        ) as penetration:
            second = resolver(power=20, ledger=_ledger(20))
        penetration.assert_called_once()
        self.assertEqual(second.damage_results, [])
        self.assertEqual(second.applied_conditions, [])
        self.assertEqual(VowAddedEffectFiring.objects.filter(effect=effect).count(), 1)

    def test_eligible_vow_bypasses_ward_even_when_damage_row_threshold_is_unmet(self):
        resolver, effect = self._vow_cast(minimum_success_level=99)
        with patch.object(
            type(resolver), "_apply_penetration", return_value=(_ledger(0), True)
        ) as penetration:
            result = resolver(power=20, ledger=_ledger(20))
        penetration.assert_not_called()
        self.assertEqual(len(result.damage_results), 1)
        self.assertEqual(len(result.applied_conditions), 1)
        self.assertEqual(VowAddedEffectFiring.objects.filter(effect=effect).count(), 1)

    def test_failed_offense_cannot_use_or_spend_vow_ward_bypass(self):
        resolver, effect = self._vow_cast(offense_sl=0, minimum_success_level=0)
        with patch.object(
            type(resolver), "_apply_penetration", return_value=(_ledger(0), True)
        ) as penetration:
            result = resolver(power=20, ledger=_ledger(20))
        penetration.assert_called_once()
        self.assertEqual(result.damage_results, [])
        self.assertEqual(result.applied_conditions, [])
        self.assertFalse(VowAddedEffectFiring.objects.filter(effect=effect).exists())
