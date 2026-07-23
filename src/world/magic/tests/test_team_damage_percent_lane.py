"""Tests for the bounded team-damage-percent lane's composition in _derive_power
(#2643): read separately from the legacy power_multiplier target, vow-keyed DR'd,
clamped, then folded into ONE MULTIPLIER stage entry alongside the legacy aggregate.
"""

from __future__ import annotations

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.conditions.factories import (
    ConditionInstanceFactory,
    ConditionModifierEffectFactory,
    ConditionTemplateFactory,
)
from world.covenants.factories import CovenantRoleFactory
from world.magic.constants import TEAM_BUFF_LANE_CAP_PERCENT, PowerStage
from world.magic.factories import TechniqueFactory
from world.magic.services.techniques import _derive_power
from world.mechanics.factories import PowerMultiplierTargetFactory, TeamDamagePercentTargetFactory


class TeamDamagePercentLaneTests(TestCase):
    def setUp(self):
        self.character = CharacterFactory()
        self.sheet = CharacterSheetFactory(character=self.character)
        self.technique = TechniqueFactory()
        self.lane_target = TeamDamagePercentTargetFactory()

    def _add_lane_condition(self, value, *, vow=None, name_suffix=""):
        cond = ConditionTemplateFactory(name=f"lane-cond-{value}-{name_suffix}")
        ConditionModifierEffectFactory(
            condition=cond, modifier_target=self.lane_target, value=value
        )
        ConditionInstanceFactory(target=self.character, condition=cond, source_vow=vow)

    def _mult_amount(self):
        ledger = _derive_power(
            channeled_intensity=100, technique=self.technique, character=self.character
        )
        mult_entries = [e for e in ledger.entries if e.stage == PowerStage.MULTIPLIER]
        self.assertEqual(len(mult_entries), 1)
        return mult_entries[0].amount

    def test_empty_lane_is_unaffected_no_multiplier_entry(self):
        """No power_multiplier and no team lane contributions -> no MULTIPLIER entry
        at all (existing behavior preserved byte-for-byte)."""
        ledger = _derive_power(
            channeled_intensity=100, technique=self.technique, character=self.character
        )
        mult_entries = [e for e in ledger.entries if e.stage == PowerStage.MULTIPLIER]
        self.assertEqual(len(mult_entries), 0)
        self.assertEqual(ledger.total, 100)

    def test_lane_sum_within_cap_passes_through(self):
        role = CovenantRoleFactory()
        self._add_lane_condition(20, vow=role)

        self.assertEqual(self._mult_amount(), 20)

    def test_lane_sum_over_cap_clamps_to_cap(self):
        """Two DIFFERENT vows stack fully (80 > 50 cap) -> clamped to the cap."""
        role_a = CovenantRoleFactory()
        role_b = CovenantRoleFactory()
        self._add_lane_condition(40, vow=role_a, name_suffix="a")
        self._add_lane_condition(40, vow=role_b, name_suffix="b")

        self.assertEqual(self._mult_amount(), TEAM_BUFF_LANE_CAP_PERCENT)

    def test_two_same_vow_sources_weight_full_and_half(self):
        role = CovenantRoleFactory()
        self._add_lane_condition(20, vow=role, name_suffix="a")
        self._add_lane_condition(20, vow=role, name_suffix="b")

        # 20*1.0 + 20*0.5 = 30
        self.assertEqual(self._mult_amount(), 30)

    def test_third_same_vow_source_weights_quarter(self):
        role = CovenantRoleFactory()
        self._add_lane_condition(20, vow=role, name_suffix="a")
        self._add_lane_condition(20, vow=role, name_suffix="b")
        self._add_lane_condition(20, vow=role, name_suffix="c")

        # 20*1.0 + 20*0.5 + 20*0.25 = 35
        self.assertEqual(self._mult_amount(), 35)

    def test_two_different_vows_stack_fully(self):
        role_a = CovenantRoleFactory()
        role_b = CovenantRoleFactory()
        self._add_lane_condition(10, vow=role_a, name_suffix="a")
        self._add_lane_condition(10, vow=role_b, name_suffix="b")

        # No diminishing across distinct vows: 10 + 10 = 20.
        self.assertEqual(self._mult_amount(), 20)

    def test_lane_folds_into_single_multiply_with_legacy_target(self):
        """The lane's clamped delta and the legacy power_multiplier's unbounded delta
        combine into ONE MULTIPLIER entry — never a second multiplicative stage."""
        role = CovenantRoleFactory()
        self._add_lane_condition(20, vow=role)

        legacy_target = PowerMultiplierTargetFactory()
        legacy_cond = ConditionTemplateFactory(name="legacy-mult")
        ConditionModifierEffectFactory(
            condition=legacy_cond, modifier_target=legacy_target, value=15
        )
        ConditionInstanceFactory(target=self.character, condition=legacy_cond)

        # lane 20 + legacy 15 = 35, one entry.
        self.assertEqual(self._mult_amount(), 35)


class TeamDamagePercentPricingIntegrationTests(TestCase):
    """priced_percent_severity is wired through apply_technique_conditions (#2643)."""

    def test_team_lane_condition_severity_is_priced_not_authored(self):
        from world.classes.factories import CharacterClassLevelFactory
        from world.magic.factories import TechniqueAppliedConditionFactory
        from world.magic.models.techniques import ConditionTargetKind
        from world.magic.services.condition_application import apply_technique_conditions

        lane_target = TeamDamagePercentTargetFactory()
        buff_condition = ConditionTemplateFactory(name="priced-buff")
        ConditionModifierEffectFactory(
            condition=buff_condition,
            modifier_target=lane_target,
            value=1,
            scales_with_severity=True,
        )

        caster = CharacterFactory()
        target_sheet = CharacterSheetFactory()
        CharacterClassLevelFactory(character=target_sheet, level=4)
        target_sheet.invalidate_class_level_cache()

        technique = TechniqueFactory()
        row = TechniqueAppliedConditionFactory(
            technique=technique,
            condition=buff_condition,
            target_kind=ConditionTargetKind.ALLY,
            minimum_success_level=1,
            base_severity=99,  # authored formula would give 99 — pricing must override it
        )

        results = apply_technique_conditions(
            technique=technique,
            success_level=3,
            eff_intensity=40,
            targets_by_kind={row.target_kind: [target_sheet.character]},
            source_character=caster,
        )

        self.assertEqual(len(results), 1)
        # priced: eff_intensity=40, PCT_PER_POWER_TENTHS=10, target_level=4 -> 40/4=10
        self.assertEqual(results[0].severity_applied, 10)
