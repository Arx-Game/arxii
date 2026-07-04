"""Tests for the drowning/falling DamageType helpers (#1714)."""

from django.test import TestCase

from world.conditions.factories import ensure_drowning_damage_type, ensure_falling_damage_type


class VehicleDamageTypeTests(TestCase):
    def test_idempotent_drowning(self):
        first = ensure_drowning_damage_type()
        second = ensure_drowning_damage_type()
        self.assertEqual(first.pk, second.pk)

    def test_idempotent_falling(self):
        first = ensure_falling_damage_type()
        second = ensure_falling_damage_type()
        self.assertEqual(first.pk, second.pk)
