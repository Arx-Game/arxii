"""Tests for VehicleKind.COMPANION (#1873)."""

from django.test import TestCase

from world.battles.constants import VehicleKind


class VehicleKindCompanionTests(TestCase):
    def test_companion_kind_exists(self):
        self.assertEqual(VehicleKind.COMPANION, "companion")
        self.assertEqual(VehicleKind.COMPANION.label, "Companion")

    def test_companion_in_choices(self):
        values = [value for value, _ in VehicleKind.choices]
        self.assertIn("companion", values)
