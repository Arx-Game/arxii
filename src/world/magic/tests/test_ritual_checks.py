"""Tests for world.magic.services.ritual_checks (#709)."""

from __future__ import annotations

from django.test import TestCase

from world.magic.exceptions import RitualCheckConfigMissing
from world.magic.services.ritual_checks import (
    OutcomeTier,
    RitualCheckRoll,
    outcome_tier,
    perform_ritual_check,
)


class OutcomeTierBoundaryTests(TestCase):
    """outcome_tier boundary cases over the canonical −10..+10 scale."""

    def test_10_is_crit(self):
        self.assertIs(outcome_tier(10), OutcomeTier.CRIT)

    def test_2_is_crit(self):
        self.assertIs(outcome_tier(2), OutcomeTier.CRIT)

    def test_1_is_success(self):
        self.assertIs(outcome_tier(1), OutcomeTier.SUCCESS)

    def test_0_is_fail(self):
        self.assertIs(outcome_tier(0), OutcomeTier.FAIL)

    def test_neg1_is_fail(self):
        self.assertIs(outcome_tier(-1), OutcomeTier.FAIL)

    def test_neg2_is_botch(self):
        self.assertIs(outcome_tier(-2), OutcomeTier.BOTCH)

    def test_neg10_is_botch(self):
        self.assertIs(outcome_tier(-10), OutcomeTier.BOTCH)


class PerformRitualCheckMissingConfigTests(TestCase):
    """perform_ritual_check raises RitualCheckConfigMissing when no config seeded."""

    def test_service_ritual_without_config_raises(self):
        from world.magic.constants import RitualExecutionKind
        from world.magic.factories import RitualFactory
        from world.scenes.factories import PersonaFactory

        ritual = RitualFactory(execution_kind=RitualExecutionKind.SERVICE)
        persona = PersonaFactory()
        character = persona.character_sheet.character

        with self.assertRaises(RitualCheckConfigMissing):
            perform_ritual_check(ritual.name, character)

    def test_missing_ritual_row_raises(self):
        """Ritual.DoesNotExist is re-raised as RitualCheckConfigMissing."""
        from world.scenes.factories import PersonaFactory

        persona = PersonaFactory()
        character = persona.character_sheet.character

        with self.assertRaises(RitualCheckConfigMissing):
            perform_ritual_check("This Ritual Does Not Exist", character)


class PerformRitualCheckReturnShapeTests(TestCase):
    """perform_ritual_check returns RitualCheckRoll with consistent tier/success_level."""

    def _mock_check_result(self, success_level: int):
        outcome = type("O", (), {"success_level": success_level})()
        return type("CR", (), {"outcome": outcome})()

    def test_returns_ritual_check_roll_with_consistent_tier(self):
        from unittest.mock import patch

        from world.magic.seeds_checks import ensure_magic_check_content
        from world.magic.seeds_sanctum import (
            DISSOLUTION_RITUAL_NAME,
            ensure_sanctum_rituals,
        )
        from world.scenes.factories import PersonaFactory

        ensure_sanctum_rituals()
        ensure_magic_check_content()
        persona = PersonaFactory()
        character = persona.character_sheet.character

        with patch("world.checks.services.perform_check") as mock_check:
            mock_check.return_value = self._mock_check_result(success_level=3)
            roll = perform_ritual_check(DISSOLUTION_RITUAL_NAME, character)

        self.assertIsInstance(roll, RitualCheckRoll)
        self.assertEqual(roll.success_level, 3)
        self.assertIs(roll.tier, OutcomeTier.CRIT)

    def test_non_founder_falls_back_to_target_difficulty_when_no_non_founder_config(self):
        """founder_standing=False falls back to target_difficulty when non_founder is None."""
        from unittest.mock import patch

        from world.magic.seeds_checks import ensure_magic_check_content
        from world.magic.seeds_sanctum import (
            HOMECOMING_RITUAL_NAME,
            ensure_sanctum_rituals,
        )
        from world.scenes.factories import PersonaFactory

        ensure_sanctum_rituals()
        ensure_magic_check_content()
        persona = PersonaFactory()
        character = persona.character_sheet.character

        with patch("world.checks.services.perform_check") as mock_check:
            mock_check.return_value = self._mock_check_result(success_level=1)
            # Homecoming has non_founder_target_difficulty=None — should fall back
            perform_ritual_check(HOMECOMING_RITUAL_NAME, character, founder_standing=False)
            _args, kwargs = mock_check.call_args
            # target_difficulty for Homecoming is 10 (from seeds_checks._RITUAL_CHECK_CONFIGS)
            self.assertEqual(kwargs["target_difficulty"], 10)
