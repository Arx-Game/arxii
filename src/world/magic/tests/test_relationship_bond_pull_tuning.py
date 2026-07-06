"""Tests for the RelationshipBondPullTuning singleton config (#1849)."""

from __future__ import annotations

from django.test import TestCase

from world.magic.models import RelationshipBondPullTuning


class RelationshipBondPullTuningModelTests(TestCase):
    """Defaults and singleton shape."""

    def test_defaults(self) -> None:
        tuning = RelationshipBondPullTuning.objects.create(pk=1)
        self.assertEqual(tuning.coefficient, 1)
        self.assertEqual(tuning.cap, 20)
        self.assertEqual(tuning.half_saturation, 30)

    def test_str(self) -> None:
        tuning = RelationshipBondPullTuning.objects.create(pk=1)
        self.assertEqual(str(tuning), "RelationshipBondPullTuning(pk=1)")
