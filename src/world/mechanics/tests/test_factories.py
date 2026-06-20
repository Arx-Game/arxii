"""Tests for world.mechanics.factories helpers."""

from django.test import TestCase

from world.mechanics.factories import max_health_modifier_target
from world.vitals.constants import MAX_HEALTH_MODIFIER_TARGET


class MaxHealthModifierTargetHelperTests(TestCase):
    def test_idempotent_and_named(self):
        a = max_health_modifier_target()
        b = max_health_modifier_target()
        self.assertEqual(a.pk, b.pk)
        self.assertEqual(a.name, MAX_HEALTH_MODIFIER_TARGET)
