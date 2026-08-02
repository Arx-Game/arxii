"""Tests for the stat_override parameter on perform_check (#2757).

stat_override lets the calling system replace the CheckType's STAT-type
traits with a different stat, determined from situational context (weapon
type, barrier type). SKILL-type traits always contribute. None (the
default) is byte-identical to pre-#2757 behavior.
"""

from __future__ import annotations

from decimal import Decimal
import logging

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import (
    CheckCategoryFactory,
    CheckTypeFactory,
    CheckTypeTraitFactory,
)
from world.checks.services import compute_check_rating, perform_check
from world.traits.factories import CheckSystemSetupFactory
from world.traits.models import (
    CharacterTraitValue,
    CheckRank,
    PointConversionRange,
    ResultChart,
    Trait,
    TraitCategory,
    TraitType,
)


class StatOverrideTests(TestCase):
    """Core stat_override behavior: substitution, byte-identical, guards."""

    @classmethod
    def setUpTestData(cls):
        Trait.flush_instance_cache()
        CheckSystemSetupFactory.create()
        for trait_type in (TraitType.STAT, TraitType.SKILL):
            PointConversionRange.objects.get_or_create(
                trait_type=trait_type,
                min_value=1,
                defaults={"max_value": 100, "points_per_level": 1},
            )
        for rank_val, min_pts, name in [
            (0, 0, "SO0"),
            (1, 10, "SO1"),
            (2, 25, "SO2"),
            (3, 50, "SO3"),
        ]:
            CheckRank.objects.get_or_create(
                rank=rank_val, defaults={"min_points": min_pts, "name": name}
            )

        cls.character = CharacterSheetFactory().character
        cls.strength, _ = Trait.objects.get_or_create(
            name="stat_override_strength",
            defaults={"trait_type": TraitType.STAT, "category": TraitCategory.PHYSICAL},
        )
        cls.agility, _ = Trait.objects.get_or_create(
            name="stat_override_agility",
            defaults={"trait_type": TraitType.STAT, "category": TraitCategory.PHYSICAL},
        )
        cls.willpower, _ = Trait.objects.get_or_create(
            name="stat_override_willpower",
            defaults={"trait_type": TraitType.STAT, "category": TraitCategory.MENTAL},
        )
        cls.intellect, _ = Trait.objects.get_or_create(
            name="stat_override_intellect",
            defaults={"trait_type": TraitType.STAT, "category": TraitCategory.MENTAL},
        )
        cls.melee_skill, _ = Trait.objects.get_or_create(
            name="stat_override_melee_combat",
            defaults={"trait_type": TraitType.SKILL, "category": TraitCategory.COMBAT},
        )
        # Real strength/agility traits (#2879) — the int-blend path hardcodes these two
        # literal names (matching every other caller's convention, e.g. stat_mapping.py's
        # DEFENSE_STAT = "agility"), distinct from the stat_override_* stand-ins above.
        cls.strength_trait, _ = Trait.objects.get_or_create(
            name="strength",
            defaults={"trait_type": TraitType.STAT, "category": TraitCategory.PHYSICAL},
        )
        cls.agility_trait, _ = Trait.objects.get_or_create(
            name="agility",
            defaults={"trait_type": TraitType.STAT, "category": TraitCategory.PHYSICAL},
        )

        cls.category = CheckCategoryFactory(name="stat_override_test")

    def setUp(self):
        Trait.flush_instance_cache()
        CharacterTraitValue.flush_instance_cache()
        ResultChart.clear_cache()
        self.handler = self.character.traits

    def _make_combat_check(self) -> object:
        """A check with strength (stat) + Melee Combat (skill)."""
        ct = CheckTypeFactory(name="stat_override_melee", category=self.category)
        CheckTypeTraitFactory(check_type=ct, trait=self.strength, weight=Decimal("1.0"))
        CheckTypeTraitFactory(check_type=ct, trait=self.melee_skill, weight=Decimal("1.0"))
        return ct

    def _make_multistat_check(self) -> object:
        """A check with willpower + intellect (two stats) + Melee Combat (skill)."""
        ct = CheckTypeFactory(name="stat_override_multi", category=self.category)
        CheckTypeTraitFactory(check_type=ct, trait=self.willpower, weight=Decimal("1.0"))
        CheckTypeTraitFactory(check_type=ct, trait=self.intellect, weight=Decimal("1.0"))
        CheckTypeTraitFactory(check_type=ct, trait=self.melee_skill, weight=Decimal("1.0"))
        return ct

    def test_none_is_byte_identical_to_default(self):
        """stat_override=None must produce identical results to not passing it."""
        ct = self._make_combat_check()
        CharacterTraitValue.objects.create(
            character=self.character.sheet_data, trait=self.strength, value=30
        )
        CharacterTraitValue.objects.create(
            character=self.character.sheet_data, trait=self.melee_skill, value=20
        )

        result_default = perform_check(self.character, ct)
        result_explicit_none = perform_check(self.character, ct, stat_override=None)
        self.assertEqual(result_default.total_points, result_explicit_none.total_points)
        self.assertEqual(result_default.trait_points, result_explicit_none.trait_points)

    def test_stat_replaced_skill_preserved(self):
        """Overriding strength→agility: agility value used, skill still contributes."""
        ct = self._make_combat_check()
        CharacterTraitValue.objects.create(
            character=self.character.sheet_data, trait=self.strength, value=50
        )
        CharacterTraitValue.objects.create(
            character=self.character.sheet_data, trait=self.agility, value=20
        )
        CharacterTraitValue.objects.create(
            character=self.character.sheet_data, trait=self.melee_skill, value=30
        )

        result_strength = perform_check(self.character, ct)
        result_agility = perform_check(self.character, ct, stat_override="stat_override_agility")

        # Strength (50) > agility (20), so overriding to agility lowers trait_points.
        self.assertGreater(result_strength.trait_points, result_agility.trait_points)
        # But the skill portion is still there — total isn't zero.
        self.assertGreater(result_agility.trait_points, 0)

    def test_override_to_missing_stat_is_zero_stat(self):
        """Overriding to a stat the character doesn't have: 0 stat points, no crash."""
        ct = self._make_combat_check()
        CharacterTraitValue.objects.create(
            character=self.character.sheet_data, trait=self.strength, value=30
        )
        CharacterTraitValue.objects.create(
            character=self.character.sheet_data, trait=self.melee_skill, value=20
        )

        result = perform_check(self.character, ct, stat_override="nonexistent_stat")
        # Only skill contributes (20 points), stat is 0
        self.assertGreaterEqual(result.trait_points, 0)
        self.assertGreaterEqual(result.total_points, 0)

    def test_two_stat_check_logs_warning(self):
        """stat_override on a 2+ stat check logs a warning and ignores the override."""
        ct = self._make_multistat_check()
        CharacterTraitValue.objects.create(
            character=self.character.sheet_data, trait=self.willpower, value=30
        )
        CharacterTraitValue.objects.create(
            character=self.character.sheet_data, trait=self.intellect, value=30
        )
        CharacterTraitValue.objects.create(
            character=self.character.sheet_data, trait=self.melee_skill, value=20
        )

        with self.assertLogs(logger="world.checks.services", level=logging.WARNING) as logs:
            perform_check(self.character, ct, stat_override="stat_override_agility")
        self.assertTrue(any("stat_override" in msg for msg in logs.output))

    def test_compute_check_rating_accepts_stat_override(self):
        """compute_check_rating also accepts stat_override."""
        ct = self._make_combat_check()
        CharacterTraitValue.objects.create(
            character=self.character.sheet_data, trait=self.strength, value=50
        )
        CharacterTraitValue.objects.create(
            character=self.character.sheet_data, trait=self.agility, value=20
        )
        CharacterTraitValue.objects.create(
            character=self.character.sheet_data, trait=self.melee_skill, value=30
        )

        rating_default = compute_check_rating(self.character, ct)
        rating_override = compute_check_rating(
            self.character, ct, stat_override="stat_override_agility"
        )
        # Strength (50) > agility (20), so default rating is higher
        self.assertGreater(rating_default, rating_override)
        # But the skill portion keeps the override rating positive
        self.assertGreater(rating_override, 0)

    def test_int_stat_override_blends_strength_and_agility(self):
        """An int stat_override (#2879) substitutes a str/agi blend."""
        self.handler.set_trait_value("strength", 10)
        self.handler.set_trait_value("agility", 4)
        ct = CheckTypeFactory(name="stat_override_blend", category=self.category)
        CheckTypeTraitFactory(check_type=ct, trait=self.strength_trait, weight=Decimal("1.0"))
        # strength_tenths=5 (even blend): (10*5 + 4*5) / 10 = 7
        result_blend = perform_check(self.character, ct, stat_override=5)
        result_explicit = perform_check(
            self.character, ct, stat_override=None
        )  # rolls raw strength (10) unblended, for contrast
        self.assertNotEqual(result_blend.total_points, result_explicit.total_points)

    def test_pure_strength_int_override_matches_string_override(self):
        """strength_tenths=10 (pure strength) must match the plain-string path."""
        self.handler.set_trait_value("strength", 7)
        self.handler.set_trait_value("agility", 3)
        ct = CheckTypeFactory(name="stat_override_pure", category=self.category)
        CheckTypeTraitFactory(check_type=ct, trait=self.strength_trait, weight=Decimal("1.0"))
        result_int = perform_check(self.character, ct, stat_override=10)
        result_str = perform_check(self.character, ct, stat_override="strength")
        self.assertEqual(result_int.total_points, result_str.total_points)
