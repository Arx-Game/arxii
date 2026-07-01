from django.test import TestCase

from world.conditions.factories import ensure_radiant_damage_type
from world.conditions.models import DamageType


class EnsureRadiantDamageTypeTest(TestCase):
    def test_creates_radiant(self):
        dt = ensure_radiant_damage_type()
        self.assertEqual(dt.name, "Radiant")
        self.assertTrue(DamageType.objects.filter(name="Radiant").exists())

    def test_idempotent(self):
        first = ensure_radiant_damage_type()
        second = ensure_radiant_damage_type()
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(DamageType.objects.filter(name="Radiant").count(), 1)
