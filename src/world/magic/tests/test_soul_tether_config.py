"""Tests for SoulTetherConfig singleton model and getter."""

from django.test import TestCase


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
