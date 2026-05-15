"""Tests for the ResonanceEnvironmentConfig singleton and lazy getter."""

from decimal import Decimal

from django.test import TestCase

from world.magic.models import ResonanceEnvironmentConfig
from world.magic.services.resonance_environment import get_resonance_environment_config


class ResonanceEnvironmentConfigTests(TestCase):
    def test_singleton_lazy_create(self) -> None:
        """get_resonance_environment_config creates the row on first call."""
        self.assertFalse(ResonanceEnvironmentConfig.objects.exists())
        cfg = get_resonance_environment_config()
        self.assertIsNotNone(cfg)
        self.assertEqual(ResonanceEnvironmentConfig.objects.count(), 1)

    def test_singleton_idempotent(self) -> None:
        """Second call returns the same row; count stays at 1."""
        cfg1 = get_resonance_environment_config()
        cfg2 = get_resonance_environment_config()
        self.assertEqual(cfg1.pk, cfg2.pk)
        self.assertEqual(ResonanceEnvironmentConfig.objects.count(), 1)

    def test_singleton_pk_is_1(self) -> None:
        """The singleton is always stored at pk=1."""
        cfg = get_resonance_environment_config()
        self.assertEqual(cfg.pk, 1)

    def test_default_values(self) -> None:
        """Default values produce distinct difficulties for low/high room tiers."""
        cfg = get_resonance_environment_config()
        # base_coefficient: scales place_magnitude * caster_alignment * severity_multiplier
        # into raw severity. 1.000 is a neutral pass-through; staff tune from here.
        self.assertEqual(cfg.base_coefficient, Decimal("1.000"))
        # caster_power_scalar: at 0.500, a caster at 100% aura reads as strength 50
        # (mid-range on a 0-100 scale), keeping the default BALANCED band meaningful.
        self.assertEqual(cfg.caster_power_scalar, Decimal("0.500"))
        # balanced_band: |caster_strength - place_magnitude| ≤ 10 → BALANCED.
        # Produces DISTINCT outcomes: low room (magnitude ~10) vs high room (magnitude ~80)
        # differ by 70, far outside the band → different direction every time.
        self.assertEqual(cfg.balanced_band, 10)
        # backfire_base_difficulty: OPPOSED checks start at 30 (moderate challenge).
        self.assertEqual(cfg.backfire_base_difficulty, 30)
        # backfire_difficulty_per_magnitude: adds 0.500 per magnitude point so a
        # magnitude-10 room adds 5 (total 35) and a magnitude-80 room adds 40 (total 70).
        # The high-room backfire is dramatically harder than the low-room backfire.
        self.assertEqual(cfg.backfire_difficulty_per_magnitude, Decimal("0.500"))
