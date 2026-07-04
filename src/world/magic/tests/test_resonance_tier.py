"""Tests for the ResonanceTier lookup model (#707)."""

from __future__ import annotations

from django.db import IntegrityError
from django.test import TestCase

from world.magic.factories import ResonanceTierFactory
from world.magic.models import ResonanceTier


class ResonanceTierTests(TestCase):
    def test_ordered_by_tier_level(self) -> None:
        ResonanceTierFactory(name="Profound", tier_level=3)
        ResonanceTierFactory(name="Faint", tier_level=1)
        ResonanceTierFactory(name="Resonant", tier_level=2)
        levels = list(ResonanceTier.objects.values_list("tier_level", flat=True))
        assert levels == [1, 2, 3]

    def test_tier_level_unique(self) -> None:
        ResonanceTierFactory(name="Faint", tier_level=1)
        with self.assertRaises(IntegrityError):
            ResonanceTierFactory(name="Duplicate", tier_level=1)

    def test_str_returns_name(self) -> None:
        tier = ResonanceTierFactory(name="Faint", tier_level=1)
        assert str(tier) == "Faint"
