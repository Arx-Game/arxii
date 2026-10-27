"""Severity-scaled damage resistance at the combat damage seams (#4728)."""

from django.test import TestCase, tag

from world.character_sheets.factories import CharacterSheetFactory
from world.combat.factories import CombatOpponentFactory, CombatParticipantFactory
from world.combat.services import apply_damage_to_opponent, apply_damage_to_participant
from world.conditions.factories import (
    ConditionResistanceModifierFactory,
    ConditionStageFactory,
    ConditionTemplateFactory,
    DamageTypeFactory,
)
from world.conditions.models import ConditionInstance
from world.conditions.services import apply_condition
from world.conditions.views import _aggregate_resistance_modifiers, _build_effect_lookups
from world.vitals.factories import CharacterVitalsFactory


def _pc_target():
    target = CombatParticipantFactory()
    CharacterVitalsFactory(
        character_sheet=target.character_sheet,
        health=500,
        max_health=500,
        base_max_health=500,
    )
    return target, target.character_sheet.character, apply_damage_to_participant


def _npc_target():
    target = CombatOpponentFactory(health=500, max_health=500, soak_value=0)
    return target, target.objectdb, apply_damage_to_opponent


class SeverityScaledResistanceTests(TestCase):
    def test_scaling_row_resists_by_severity_on_both_seams(self):
        for make_target in (_pc_target, _npc_target):
            for severity, expected in ((1, 40), (3, 20), (5, 0)):
                with self.subTest(target=make_target.__name__, severity=severity):
                    physical = DamageTypeFactory()
                    smoke = ConditionTemplateFactory()
                    ConditionResistanceModifierFactory(
                        condition=smoke,
                        damage_type=physical,
                        modifier_value=10,
                        scales_with_severity=True,
                    )
                    target, character, apply = make_target()
                    apply_condition(character, smoke, severity=severity)

                    result = apply(target, 50, damage_type=physical)

                    self.assertEqual(result.damage_dealt, expected)

    def test_overwhelming_damage_still_gets_through_scaled_resistance(self):
        physical = DamageTypeFactory()
        smoke = ConditionTemplateFactory()
        ConditionResistanceModifierFactory(
            condition=smoke, damage_type=physical, modifier_value=10, scales_with_severity=True
        )
        target, character, apply = _pc_target()
        apply_condition(character, smoke, severity=4)

        self.assertEqual(apply(target, 100, damage_type=physical).damage_dealt, 60)

    def test_flat_row_ignores_severity(self):
        physical = DamageTypeFactory()
        ward = ConditionTemplateFactory()
        ConditionResistanceModifierFactory(condition=ward, damage_type=physical, modifier_value=10)
        target, character, apply = _pc_target()
        apply_condition(character, ward, severity=4)

        self.assertEqual(apply(target, 50, damage_type=physical).damage_dealt, 40)

    @tag("postgres")
    def test_stage_rows_scale_by_effective_severity_or_stay_flat(self):
        """PG-only: applying a staged condition uses DISTINCT ON in _build_bulk_context."""
        physical = DamageTypeFactory()
        stage = ConditionStageFactory(stage_order=1, severity_multiplier=2)
        ConditionResistanceModifierFactory(
            condition=None,
            stage=stage,
            damage_type=physical,
            modifier_value=5,
            scales_with_severity=True,
        )
        ConditionResistanceModifierFactory(
            condition=None, stage=stage, damage_type=None, modifier_value=3
        )
        target, character, apply = _pc_target()
        apply_condition(character, stage.condition, severity=2)
        instance = ConditionInstance.objects.get(target=character, condition=stage.condition)
        instance.current_stage = stage
        instance.save(update_fields=["current_stage"])
        character.conditions.invalidate()

        # Effective severity is 2 x stage multiplier 2 = 4: 5 x 4 scaled + 3 flat = 23.
        self.assertEqual(character.conditions.resistance_modifier(physical), 23)
        self.assertEqual(apply(target, 50, damage_type=physical).damage_dealt, 27)


class ResistanceSummaryMatchesDamageSeamTests(TestCase):
    """The conditions summary a player reads shows the resistance the damage seam applies.

    Compared oracle-to-oracle (summary vs handler), as the capability cross-reader
    tests in world/conditions/tests/test_effective_capability_value.py do.
    """

    def _summary_and_seam(self, instance, character, damage_type):
        lookups = _build_effect_lookups([instance])
        summary = _aggregate_resistance_modifiers(lookups)
        return summary.get(damage_type.name, 0), character.conditions.resistance_modifier(
            damage_type
        )

    def test_scaled_row_summary_matches_seam(self):
        physical = DamageTypeFactory()
        smoke = ConditionTemplateFactory()
        ConditionResistanceModifierFactory(
            condition=smoke, damage_type=physical, modifier_value=10, scales_with_severity=True
        )
        character = CharacterSheetFactory().character
        result = apply_condition(character, smoke, severity=4)

        summary, seam = self._summary_and_seam(result.instance, character, physical)

        self.assertEqual(seam, 40)
        self.assertEqual(summary, seam)

    @tag("postgres")
    def test_flat_stage_row_summary_matches_seam(self):
        """PG-only: applying a staged condition uses DISTINCT ON in _build_bulk_context."""
        radiant = DamageTypeFactory()
        stage = ConditionStageFactory(stage_order=1, severity_multiplier=2)
        ConditionResistanceModifierFactory(
            condition=None, stage=stage, damage_type=radiant, modifier_value=-30
        )
        character = CharacterSheetFactory().character
        apply_condition(character, stage.condition)
        instance = ConditionInstance.objects.get(target=character, condition=stage.condition)
        instance.current_stage = stage
        instance.save(update_fields=["current_stage"])
        character.conditions.invalidate()

        summary, seam = self._summary_and_seam(instance, character, radiant)

        self.assertEqual(seam, -30)
        self.assertEqual(summary, seam)
