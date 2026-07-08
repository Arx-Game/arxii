"""Tests for break-bar damage assessment: combo path and distinct-effect-type path."""

from django.test import TestCase

from world.combat.constants import OpponentTier
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    ComboDefinitionFactory,
)
from world.combat.services import assess_break_bar
from world.combat.types import ActionOutcome, OpponentDamageResult


def _dmg_result(opponent_id, damage_dealt=10):
    return OpponentDamageResult(
        damage_dealt=damage_dealt,
        health_damaged=True,
        probed=False,
        probing_increment=0,
        defeated=False,
        opponent_id=opponent_id,
    )


class BreakBarComboPathTests(TestCase):
    def test_combo_damages_break_bar(self):
        encounter = CombatEncounterFactory()
        opp = CombatOpponentFactory(
            encounter=encounter,
            tier=OpponentTier.BOSS,
            break_bar_threshold=30,
            break_bar_current=30,
            vulnerability_rounds=2,
            vulnerability_rounds_remaining=0,
        )
        combo = ComboDefinitionFactory(bonus_damage=15)
        outcome = ActionOutcome(
            entity_type="pc",
            entity_label="PC1",
            combo_used=combo,
            damage_results=[_dmg_result(opp.pk)],
            participant_id=1,
            effect_type_id=1,
        )
        assess_break_bar(encounter, [outcome])
        opp.refresh_from_db()
        self.assertEqual(opp.break_bar_current, 15)  # 30 - 15 = 15

    def test_break_bar_breaking_opens_window(self):
        encounter = CombatEncounterFactory()
        opp = CombatOpponentFactory(
            encounter=encounter,
            tier=OpponentTier.BOSS,
            break_bar_threshold=10,
            break_bar_current=10,
            vulnerability_rounds=2,
            vulnerability_rounds_remaining=0,
            vulnerability_intensity_bonus=2,
        )
        combo = ComboDefinitionFactory(bonus_damage=15)
        outcome = ActionOutcome(
            entity_type="pc",
            entity_label="PC1",
            combo_used=combo,
            damage_results=[_dmg_result(opp.pk)],
            participant_id=1,
            effect_type_id=1,
        )
        assess_break_bar(encounter, [outcome])
        opp.refresh_from_db()
        self.assertEqual(opp.break_bar_current, 0)
        self.assertEqual(opp.vulnerability_rounds_remaining, 2)

    def test_no_bar_is_noop(self):
        encounter = CombatEncounterFactory()
        opp = CombatOpponentFactory(
            encounter=encounter,
            tier=OpponentTier.MOOK,
            break_bar_threshold=0,
            break_bar_current=0,
        )
        combo = ComboDefinitionFactory(bonus_damage=15)
        outcome = ActionOutcome(
            entity_type="pc",
            entity_label="PC1",
            combo_used=combo,
            damage_results=[_dmg_result(opp.pk)],
            participant_id=1,
            effect_type_id=1,
        )
        assess_break_bar(encounter, [outcome])
        opp.refresh_from_db()
        self.assertEqual(opp.vulnerability_rounds_remaining, 0)


class BreakBarDistinctPathTests(TestCase):
    def test_two_distinct_pcs_distinct_effect_types_chips_bar(self):
        encounter = CombatEncounterFactory()
        opp = CombatOpponentFactory(
            encounter=encounter,
            tier=OpponentTier.BOSS,
            break_bar_threshold=5,
            break_bar_current=5,
            vulnerability_rounds=2,
            vulnerability_rounds_remaining=0,
        )
        outcomes = [
            ActionOutcome(
                entity_type="pc",
                entity_label="PC1",
                damage_results=[_dmg_result(opp.pk)],
                participant_id=1,
                effect_type_id=10,
            ),
            ActionOutcome(
                entity_type="pc",
                entity_label="PC2",
                damage_results=[_dmg_result(opp.pk)],
                participant_id=2,
                effect_type_id=20,
            ),
        ]
        assess_break_bar(encounter, outcomes)
        opp.refresh_from_db()
        self.assertEqual(opp.break_bar_current, 4)  # 5 - 1 chip = 4

    def test_same_pc_does_not_chip_bar(self):
        encounter = CombatEncounterFactory()
        opp = CombatOpponentFactory(
            encounter=encounter,
            tier=OpponentTier.BOSS,
            break_bar_threshold=5,
            break_bar_current=5,
            vulnerability_rounds=2,
            vulnerability_rounds_remaining=0,
        )
        outcomes = [
            ActionOutcome(
                entity_type="pc",
                entity_label="PC1",
                damage_results=[_dmg_result(opp.pk)],
                participant_id=1,
                effect_type_id=10,
            ),
            ActionOutcome(
                entity_type="pc",
                entity_label="PC1",
                damage_results=[_dmg_result(opp.pk)],
                participant_id=1,
                effect_type_id=20,
            ),
        ]
        assess_break_bar(encounter, outcomes)
        opp.refresh_from_db()
        self.assertEqual(opp.break_bar_current, 5)  # no chip — same PC

    def test_already_vulnerable_does_not_assess(self):
        encounter = CombatEncounterFactory()
        opp = CombatOpponentFactory(
            encounter=encounter,
            tier=OpponentTier.BOSS,
            break_bar_threshold=10,
            break_bar_current=10,
            vulnerability_rounds=2,
            vulnerability_rounds_remaining=2,
        )
        combo = ComboDefinitionFactory(bonus_damage=15)
        outcome = ActionOutcome(
            entity_type="pc",
            entity_label="PC1",
            combo_used=combo,
            damage_results=[_dmg_result(opp.pk)],
            participant_id=1,
            effect_type_id=1,
        )
        assess_break_bar(encounter, [outcome])
        opp.refresh_from_db()
        self.assertEqual(opp.break_bar_current, 10)  # unchanged — already vulnerable
