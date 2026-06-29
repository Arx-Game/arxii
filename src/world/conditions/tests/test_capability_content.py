"""Tests for capability catalog seed content (#1604 Task 4)."""

from django.test import TestCase

from world.conditions.capability_content import ensure_at_will_shifting_capability
from world.conditions.models import CapabilityType


class EnsureAtWillShiftingCapabilityTests(TestCase):
    def test_creates_at_will_shifting_capability(self):
        ensure_at_will_shifting_capability()
        self.assertTrue(CapabilityType.objects.filter(name="at_will_shifting").exists())

    def test_is_idempotent(self):
        ensure_at_will_shifting_capability()
        ensure_at_will_shifting_capability()
        self.assertEqual(CapabilityType.objects.filter(name="at_will_shifting").count(), 1)
