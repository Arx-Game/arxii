from django.test import TestCase

from world.combat.constants import (
    ClashActionSlot,
    ClashFlavor,
    ClashResolution,
    ClashStatus,
    LockPcRole,
)
from world.combat.models import ClashConfig, StrainConfig
from world.combat.services import get_clash_config, get_strain_config


class ClashConstantsTests(TestCase):
    def test_flavors_present(self):
        self.assertEqual(set(ClashFlavor.values), {"CLASH", "LOCK", "WARD", "BREAK"})

    def test_lock_roles_present(self):
        self.assertEqual(set(LockPcRole.values), {"SUSTAINING", "ESCAPING"})

    def test_status_and_slots(self):
        self.assertEqual(set(ClashStatus.values), {"ACTIVE", "RESOLVED"})
        self.assertEqual(set(ClashActionSlot.values), {"FOCUSED", "PASSIVE"})

    def test_resolution_tiers(self):
        self.assertEqual(
            set(ClashResolution.values),
            {"PC_DECISIVE", "PC_MARGINAL", "MUTUAL", "NPC_MARGINAL", "NPC_DECISIVE", "ABANDONED"},
        )


class ClashConfigTests(TestCase):
    def test_strain_config_singleton_defaults(self):
        cfg, _ = StrainConfig.objects.get_or_create(pk=1)
        self.assertGreater(cfg.conversion_base, 0)
        self.assertGreaterEqual(cfg.diminishing_step, 1)

    def test_clash_config_singleton_defaults(self):
        cfg, _ = ClashConfig.objects.get_or_create(pk=1)
        self.assertGreater(cfg.affinity_tilt_coefficient, 0)
        self.assertGreater(cfg.passive_anima_cap, 0)
        self.assertEqual(cfg.delta_great_success, 2)
        self.assertGreaterEqual(cfg.break_abandon_idle_rounds, 1)

    def test_get_strain_config_lazy_creates_singleton(self):
        self.assertFalse(StrainConfig.objects.filter(pk=1).exists())
        cfg = get_strain_config()
        self.assertEqual(cfg.pk, 1)
        self.assertGreater(cfg.conversion_base, 0)
        self.assertGreaterEqual(cfg.diminishing_step, 1)
        self.assertGreaterEqual(cfg.diminishing_floor, 1)

    def test_get_clash_config_lazy_creates_singleton(self):
        self.assertFalse(ClashConfig.objects.filter(pk=1).exists())
        cfg = get_clash_config()
        self.assertEqual(cfg.pk, 1)
        self.assertGreater(cfg.affinity_tilt_coefficient, 0)
        self.assertGreater(cfg.passive_anima_cap, 0)
        self.assertEqual(cfg.delta_critical_success, 3)
        self.assertEqual(cfg.delta_great_success, 2)
        self.assertEqual(cfg.delta_success, 1)
        self.assertEqual(cfg.delta_partial, 0)
        self.assertEqual(cfg.delta_failure, -1)
        self.assertEqual(cfg.delta_botch, -2)
