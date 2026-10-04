"""Tests for the one social difficulty function (#4145)."""

from unittest.mock import patch

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckTypeFactory, create_resistance_check_types
from world.checks.social_target import DriveHit, social_target_difficulty
from world.mechanics.factories import ModifierTargetFactory
from world.scenes.action_constants import DIFFICULTY_BAND_STEP


class SocialTargetDifficultyTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        create_resistance_check_types()
        cls.actor = CharacterSheetFactory()
        cls.target = CharacterSheetFactory()
        cls.check_type = CheckTypeFactory()
        cls.sway = ModifierTargetFactory()

    def test_drive_strength_eases_by_bands(self) -> None:
        plain = social_target_difficulty(
            actor_sheet=self.actor,
            target_character=self.target.character,
            check_type=self.check_type,
            base_difficulty=60,
        )
        eased = social_target_difficulty(
            actor_sheet=self.actor,
            target_character=self.target.character,
            check_type=self.check_type,
            base_difficulty=60,
            drive_hits=[DriveHit(label="fearful", strength=2)],
        )
        self.assertEqual(plain.difficulty - eased.difficulty, 2 * DIFFICULTY_BAND_STEP)
        self.assertEqual(eased.eased_bands, 2)

    def test_sway_counts_once_plus_drive_strength(self) -> None:
        with patch("world.checks.social_target.get_modifier_total", return_value=4):
            result = social_target_difficulty(
                actor_sheet=self.actor,
                target_character=None,
                check_type=self.check_type,
                sway_target=self.sway,
                drive_hits=[DriveHit(label="fearful", strength=2)],
            )
        self.assertEqual(sum(c.value for c in result.contributions), 4 * 3)

    def test_sway_counts_once_without_a_drive(self) -> None:
        with patch("world.checks.social_target.get_modifier_total", return_value=4):
            result = social_target_difficulty(
                actor_sheet=self.actor,
                target_character=None,
                check_type=self.check_type,
                sway_target=self.sway,
            )
        self.assertEqual(sum(c.value for c in result.contributions), 4)

    def test_mindless_resistance_and_never_negative(self) -> None:
        result = social_target_difficulty(
            actor_sheet=self.actor,
            target_character=None,
            check_type=self.check_type,
            base_difficulty=0,
            drive_hits=[DriveHit(label="x", strength=3)],
            mindless_resistance=30,
        )
        self.assertEqual(result.difficulty, 0)  # 30 - 45 clamps to 0

    def test_target_level_adds_resistance(self) -> None:
        low = social_target_difficulty(
            actor_sheet=self.actor,
            target_character=self.target.character,
            check_type=self.check_type,
            target_level=1,
        )
        high = social_target_difficulty(
            actor_sheet=self.actor,
            target_character=self.target.character,
            check_type=self.check_type,
            target_level=10,
        )
        self.assertGreater(high.difficulty, low.difficulty)
