"""Tests for process_damage_consequences wiring with thread survivability saves (#1250)."""

from __future__ import annotations

from unittest import mock

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.magic.constants import VitalBonusTarget
from world.magic.factories import ResonanceFactory, ThreadFactory
from world.magic.services import seed_thread_survivability_tuning, survivability_baseline
from world.vitals.factories import CharacterVitalsFactory
from world.vitals.services import process_damage_consequences


class ThreadSavesWiringTests(TestCase):
    """Verify that thread survivability saves reach the damage-consequence tiers (#1250)."""

    def _character_with_threads(self):
        """Return an ObjectDB character whose sheet has three level-10 threads seeded."""
        sheet = CharacterSheetFactory()
        CharacterVitalsFactory(character_sheet=sheet, health=100, max_health=100)
        for _i in range(3):
            ThreadFactory(owner=sheet, resonance=ResonanceFactory(), level=10)
        return sheet.character

    def test_thread_saves_raise_tier_rollmod(self) -> None:
        """A thread-invested character's death-save modifier reaches the death tier."""
        seed_thread_survivability_tuning()
        invested = self._character_with_threads()
        invested.sheet_data.vitals.health = 0
        invested.sheet_data.vitals.save(update_fields=["health"])
        with (
            mock.patch("world.vitals.services._apply_death_tier", return_value=False) as death_tier,
            mock.patch("world.vitals.services._death_pool", return_value=object()),
        ):
            process_damage_consequences(
                character_sheet=invested.sheet_data,
                damage_dealt=5,
                damage_type=None,
            )
        expected = survivability_baseline(invested, VitalBonusTarget.DEATH_SAVE)
        self.assertEqual(death_tier.call_args.kwargs["extra_modifiers"], expected)
        self.assertGreater(expected, 0)
