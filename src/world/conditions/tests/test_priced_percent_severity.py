"""Tests for priced_percent_severity — the bounded team-damage-percent lane's apply-time
pricing formula (#2643): power buys the percentage, priced inversely against the
buffed/debuffed target's level."""

from __future__ import annotations

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.classes.factories import CharacterClassLevelFactory
from world.combat.constants import OPPONENT_TIER_LEVEL, OpponentTier
from world.combat.factories import CombatOpponentFactory
from world.conditions.services import priced_percent_severity
from world.magic.constants import TEAM_BUFF_LANE_CAP_PERCENT


class PricedPercentSeverityPcTargetTests(TestCase):
    """Target level resolves from CharacterSheet.current_level for a PC target."""

    def test_same_power_higher_level_yields_smaller_severity(self):
        low_sheet = CharacterSheetFactory()
        CharacterClassLevelFactory(character=low_sheet, level=2)
        low_sheet.invalidate_class_level_cache()

        high_sheet = CharacterSheetFactory()
        CharacterClassLevelFactory(character=high_sheet, level=10)
        high_sheet.invalidate_class_level_cache()

        low_severity = priced_percent_severity(eff_intensity=40, target=low_sheet.character)
        high_severity = priced_percent_severity(eff_intensity=40, target=high_sheet.character)

        self.assertGreater(low_severity, high_severity)
        # eff_intensity=40, PCT_PER_POWER_TENTHS=10 -> 40/2=20, 40/10=4
        self.assertEqual(low_severity, 20)
        self.assertEqual(high_severity, 4)

    def test_floors_at_one(self):
        sheet = CharacterSheetFactory()
        CharacterClassLevelFactory(character=sheet, level=50)
        sheet.invalidate_class_level_cache()

        severity = priced_percent_severity(eff_intensity=1, target=sheet.character)

        self.assertEqual(severity, 1)

    def test_clamps_to_lane_cap(self):
        sheet = CharacterSheetFactory()
        CharacterClassLevelFactory(character=sheet, level=1)
        sheet.invalidate_class_level_cache()

        severity = priced_percent_severity(eff_intensity=1000, target=sheet.character)

        self.assertEqual(severity, TEAM_BUFF_LANE_CAP_PERCENT)

    def test_zero_level_treated_as_one(self):
        """A character with no class assignments (current_level == 0) is priced as
        if level 1 (max(1, target_level) in the formula)."""
        sheet = CharacterSheetFactory()

        severity = priced_percent_severity(eff_intensity=20, target=sheet.character)

        self.assertEqual(severity, 20)  # same as level 1: 20/1


class PricedPercentSeverityOpponentTargetTests(TestCase):
    """Target level resolves from OPPONENT_TIER_LEVEL for a CombatOpponent target."""

    def test_opponent_tier_pseudo_level_used(self):
        opponent = CombatOpponentFactory(tier=OpponentTier.ELITE)

        severity = priced_percent_severity(eff_intensity=40, target=opponent.objectdb)

        # ELITE -> pseudo-level 4: eff_intensity 40 / target_level 4 = 10
        self.assertEqual(OPPONENT_TIER_LEVEL[OpponentTier.ELITE], 4)
        self.assertEqual(severity, 10)

    def test_higher_tier_yields_smaller_severity_for_same_power(self):
        mook = CombatOpponentFactory(tier=OpponentTier.MOOK)
        boss = CombatOpponentFactory(tier=OpponentTier.BOSS)

        mook_severity = priced_percent_severity(eff_intensity=40, target=mook.objectdb)
        boss_severity = priced_percent_severity(eff_intensity=40, target=boss.objectdb)

        self.assertGreater(mook_severity, boss_severity)

    def test_unresolvable_target_defaults_to_level_one(self):
        """A target that is neither a PC nor a CombatOpponent (an unlinked ObjectDB)
        prices as level 1."""
        from evennia_extensions.factories import ObjectDBFactory

        stray = ObjectDBFactory(db_key="Unlinked")

        severity = priced_percent_severity(eff_intensity=20, target=stray)

        self.assertEqual(severity, 20)
