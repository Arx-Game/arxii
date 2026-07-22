"""Tests for world.mechanics.factories helpers."""

from django.test import TestCase

from world.mechanics.constants import POWER_CATEGORY_NAME, TEAM_DAMAGE_PERCENT_TARGET_NAME
from world.mechanics.factories import ensure_team_damage_percent_target, max_health_modifier_target
from world.vitals.constants import MAX_HEALTH_MODIFIER_TARGET


class MaxHealthModifierTargetHelperTests(TestCase):
    def test_idempotent_and_named(self):
        a = max_health_modifier_target()
        b = max_health_modifier_target()
        self.assertEqual(a.pk, b.pk)
        self.assertEqual(a.name, MAX_HEALTH_MODIFIER_TARGET)


class EnsureTeamDamagePercentTargetTests(TestCase):
    """#2643 — mirrors the power_multiplier ModifierTarget-ensure idiom."""

    def test_idempotent_and_named(self):
        a = ensure_team_damage_percent_target()
        b = ensure_team_damage_percent_target()
        self.assertEqual(a.pk, b.pk)
        self.assertEqual(a.name, TEAM_DAMAGE_PERCENT_TARGET_NAME)
        self.assertEqual(a.category.name, POWER_CATEGORY_NAME)
