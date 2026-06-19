"""Tests for SoulTetherConfig singleton model and getter."""

from unittest.mock import MagicMock

from django.test import TestCase


class SoulTetherConfigSineatingKnobsTest(TestCase):
    """Verify the sineating helpers read from SoulTetherConfig, not module constants."""

    def _make_thread(self, level: int) -> MagicMock:
        """Return a minimal mock Thread with the given level."""
        t = MagicMock()
        t.level = level
        return t

    def test_hollow_max_reads_level_mult_from_config(self):
        from world.magic.services.soul_tether import _compute_hollow_max, get_soul_tether_config

        cfg = get_soul_tether_config()
        cfg.hollow_max_level_mult = 7
        cfg.save()
        thread = self._make_thread(level=2)
        self.assertEqual(_compute_hollow_max(thread), 14)  # 2 * 7

    def test_per_scene_cap_reads_knobs_from_config(self):
        from world.magic.services.soul_tether import (
            _compute_per_scene_sineating_cap,
            get_soul_tether_config,
        )

        cfg = get_soul_tether_config()
        cfg.per_scene_cap_level_mult = 3
        cfg.per_scene_cap_base = 10
        cfg.per_scene_cap_hard_max = 100
        cfg.save()
        thread = self._make_thread(level=4)
        # min(100, 4*3 + 10) = min(100, 22) = 22
        self.assertEqual(_compute_per_scene_sineating_cap(thread, MagicMock()), 22)


class SoulTetherConfigKnobsTest(TestCase):
    """Verify the rescue helpers read from SoulTetherConfig, not module constants."""

    def test_strain_cost_reads_from_config(self):
        from world.magic.services.soul_tether import _compute_strain_cost, get_soul_tether_config

        cfg = get_soul_tether_config()
        cfg.rescue_strain_stage4 = 99
        cfg.save()
        self.assertEqual(_compute_strain_cost(4), 99)

    def test_resonance_cost_reads_from_config(self):
        from world.magic.services.soul_tether import (
            _compute_resonance_cost,
            get_soul_tether_config,
        )

        cfg = get_soul_tether_config()
        cfg.rescue_resonance_stage3 = 77
        cfg.save()
        self.assertEqual(_compute_resonance_cost(3), 77)

    def test_rescue_budget_reads_base_from_config(self):
        from world.magic.services.soul_tether import _compute_rescue_budget, get_soul_tether_config

        cfg = get_soul_tether_config()
        cfg.rescue_budget_base_stage5 = 500
        # multiplier: 10/10 + 0*(5/10) + 0*(5/100) = 1.0  → budget = max(1, int(500*1.0))
        cfg.save()
        self.assertEqual(_compute_rescue_budget(0, 5, 0), 500)

    def test_rescue_budget_reads_multipliers_from_config(self):
        from world.magic.services.soul_tether import _compute_rescue_budget, get_soul_tether_config

        cfg = get_soul_tether_config()
        # base=60, success_mult = 10 tenths = 1.0 per level, thread=0
        cfg.rescue_budget_success_mult_tenths = 10
        cfg.save()
        # budget = max(1, int(60 * (1.0 + 1*1.0 + 0*0.05))) = int(60*2.0) = 120
        self.assertEqual(_compute_rescue_budget(1, 3, 0), 120)


class SoulTetherConfigGetterTest(TestCase):
    def test_get_soul_tether_config_lazy_creates_with_defaults(self):
        from world.magic.services.soul_tether import get_soul_tether_config

        cfg = get_soul_tether_config()
        self.assertEqual(cfg.pk, 1)
        # Sineating fields
        self.assertEqual(cfg.anima_cost_per_unit, 2)
        self.assertEqual(cfg.fatigue_cost_per_unit, 1)
        self.assertEqual(cfg.per_scene_cap_hard_max, 20)
        self.assertEqual(cfg.per_scene_cap_level_mult, 2)
        self.assertEqual(cfg.per_scene_cap_base, 5)
        self.assertEqual(cfg.hollow_max_level_mult, 10)
        # Rescue strain thresholds
        self.assertEqual(cfg.rescue_strain_stage3, 5)
        self.assertEqual(cfg.rescue_strain_stage4, 10)
        self.assertEqual(cfg.rescue_strain_stage5, 18)
        # Rescue resonance costs
        self.assertEqual(cfg.rescue_resonance_stage3, 10)
        self.assertEqual(cfg.rescue_resonance_stage4, 20)
        self.assertEqual(cfg.rescue_resonance_stage5, 35)
        # Rescue budget bases
        self.assertEqual(cfg.rescue_budget_base_stage3, 60)
        self.assertEqual(cfg.rescue_budget_base_stage4, 120)
        self.assertEqual(cfg.rescue_budget_base_stage5, 250)
        # Rescue budget multipliers (integer-encoded)
        self.assertEqual(cfg.rescue_budget_base_mult_tenths, 10)  # 1.0
        self.assertEqual(cfg.rescue_budget_success_mult_tenths, 5)  # 0.5
        self.assertEqual(cfg.rescue_budget_thread_mult_hundredths, 5)  # 0.05

    def test_get_soul_tether_config_idempotent(self):
        from world.magic.services.soul_tether import get_soul_tether_config

        cfg1 = get_soul_tether_config()
        cfg2 = get_soul_tether_config()
        self.assertEqual(cfg1.pk, cfg2.pk)
