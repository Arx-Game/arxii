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


class ClashModelTests(TestCase):
    """Tests for the Clash discriminator model.

    Creates encounter and opponent inline (no CombatNPC typeclass ObjectDB) to avoid
    the setUpTestData deepcopy restriction on Evennia DbHolder objects.
    """

    def setUp(self) -> None:
        from actions.models import ConsequencePool
        from world.combat.constants import OpponentTier
        from world.combat.models import CombatEncounter, CombatOpponent

        self.encounter = CombatEncounter.objects.create()
        self.opponent = CombatOpponent.objects.create(
            encounter=self.encounter,
            tier=OpponentTier.MOOK,
            name="Test Opponent",
            health=50,
            max_health=50,
        )
        self.resolution_pool = ConsequencePool.objects.create(name="ClashTestResolutionPool")
        self.per_round_pool = ConsequencePool.objects.create(name="ClashTestPerRoundPool")

    def _make_clash(self, **kwargs):
        """Helper: build a minimal CLASH-flavor Clash with required fields."""
        from world.combat.models import Clash

        defaults = {
            "encounter": self.encounter,
            "npc_opponent": self.opponent,
            "resolution_consequence_pool": self.resolution_pool,
            "flavor": ClashFlavor.CLASH,
            "progress": 0,
            "pc_win_threshold": 5,
            "npc_win_threshold": -5,
            "started_round": 1,
        }
        defaults.update(kwargs)
        return Clash(**defaults)

    # (a) Valid CLASH-flavor row passes full_clean()
    def test_clash_flavor_valid(self) -> None:
        clash = self._make_clash()
        # full_clean() must pass before save
        clash.full_clean()
        clash.save()

    # (b) LOCK flavor requires lock_pc_role
    def test_lock_flavor_requires_lock_pc_role(self) -> None:
        from django.core.exceptions import ValidationError

        from world.combat.models import Clash

        # LOCK without lock_pc_role should fail full_clean() before hitting the DB
        lock = Clash(
            encounter=self.encounter,
            npc_opponent=self.opponent,
            resolution_consequence_pool=self.resolution_pool,
            flavor=ClashFlavor.LOCK,
            progress=0,
            pc_win_threshold=3,
            started_round=1,
            lock_pc_role=None,
        )
        with self.assertRaises(ValidationError):
            lock.full_clean()

    def test_lock_flavor_with_role_passes(self) -> None:
        clash = self._make_clash(
            flavor=ClashFlavor.LOCK,
            lock_pc_role=LockPcRole.SUSTAINING,
            npc_win_threshold=None,
        )
        clash.full_clean()
        clash.save()

    # (c) Non-LOCK row with lock_pc_role set is rejected
    def test_non_lock_with_lock_pc_role_rejected(self) -> None:
        from django.core.exceptions import ValidationError

        clash = self._make_clash(lock_pc_role=LockPcRole.ESCAPING)
        with self.assertRaises(ValidationError):
            clash.full_clean()

    # (d) status defaults to ACTIVE
    def test_status_defaults_to_active(self) -> None:
        from world.combat.models import Clash

        clash = Clash(
            encounter=self.encounter,
            npc_opponent=self.opponent,
            resolution_consequence_pool=self.resolution_pool,
            flavor=ClashFlavor.CLASH,
            progress=0,
            pc_win_threshold=5,
            npc_win_threshold=-5,
            started_round=1,
        )
        self.assertEqual(clash.status, ClashStatus.ACTIVE)
