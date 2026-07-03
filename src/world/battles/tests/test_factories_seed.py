"""Tests for the battles app's idempotent content-seed helpers (#1711)."""

from __future__ import annotations

from django.test import TestCase

from world.mechanics.constants import STAT_CATEGORY_NAME
from world.mechanics.models import ModifierTarget


class EnsureBattleCommandModifierTargetTests(TestCase):
    def test_creates_target_in_stat_category(self) -> None:
        from world.battles.constants import BATTLE_COMMAND_TARGET_NAME
        from world.battles.factories import ensure_battle_command_modifier_target

        target = ensure_battle_command_modifier_target()

        self.assertEqual(target.name, BATTLE_COMMAND_TARGET_NAME)
        self.assertEqual(target.category.name, STAT_CATEGORY_NAME)
        self.assertTrue(ModifierTarget.objects.filter(name=BATTLE_COMMAND_TARGET_NAME).exists())

    def test_idempotent(self) -> None:
        from world.battles.factories import ensure_battle_command_modifier_target

        first = ensure_battle_command_modifier_target()
        second = ensure_battle_command_modifier_target()

        self.assertEqual(first.pk, second.pk)
        self.assertEqual(ModifierTarget.objects.filter(name=first.name).count(), 1)
