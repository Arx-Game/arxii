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

    def _make_clash(self, **kwargs) -> "Clash":
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

    # (e) WARD biconditional — missing ward_ends_on_round fails
    def test_ward_flavor_requires_ward_ends_on_round(self) -> None:
        from django.core.exceptions import ValidationError

        clash = self._make_clash(
            flavor=ClashFlavor.WARD,
            npc_win_threshold=None,
            ward_ends_on_round=None,
        )
        with self.assertRaises(ValidationError):
            clash.full_clean()

    # (f) WARD biconditional — valid row passes
    def test_ward_flavor_valid(self) -> None:
        clash = self._make_clash(
            flavor=ClashFlavor.WARD,
            npc_win_threshold=None,
            ward_ends_on_round=5,
        )
        clash.full_clean()
        clash.save()

    # (g) Non-WARD row with ward_ends_on_round set is rejected
    def test_non_ward_with_ward_ends_on_round_rejected(self) -> None:
        from django.core.exceptions import ValidationError

        # BREAK flavor has no flavored fields — add ward_ends_on_round to trigger error
        clash = self._make_clash(
            flavor=ClashFlavor.BREAK,
            npc_win_threshold=None,
            ward_ends_on_round=3,
        )
        with self.assertRaises(ValidationError):
            clash.full_clean()

    # (h) Valid BREAK row — all flavored fields null
    def test_break_flavor_valid(self) -> None:
        clash = self._make_clash(
            flavor=ClashFlavor.BREAK,
            npc_win_threshold=None,
        )
        clash.full_clean()
        clash.save()

    # (i) CLASH biconditional negative — non-CLASH row with npc_win_threshold set is rejected
    def test_non_clash_with_npc_win_threshold_rejected(self) -> None:
        from django.core.exceptions import ValidationError

        # BREAK flavor should not have npc_win_threshold
        clash = self._make_clash(
            flavor=ClashFlavor.BREAK,
            npc_win_threshold=-5,
        )
        with self.assertRaises(ValidationError):
            clash.full_clean()


class ClashRoundModelTests(TestCase):
    """Tests for the ClashRound per-round record model.

    Builds Clash dependencies inline following the ClashModelTests pattern.
    """

    def setUp(self) -> None:
        from actions.models import ConsequencePool
        from world.combat.constants import OpponentTier
        from world.combat.models import CombatEncounter, CombatOpponent

        self.encounter = CombatEncounter.objects.create()
        self.opponent = CombatOpponent.objects.create(
            encounter=self.encounter,
            tier=OpponentTier.MOOK,
            name="Round Test Opponent",
            health=50,
            max_health=50,
        )
        self.resolution_pool = ConsequencePool.objects.create(name="RoundTestResolutionPool")

    def _make_clash(self, **kwargs) -> "Clash":
        """Build a minimal CLASH-flavor Clash and save it."""
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
        clash = Clash(**defaults)
        clash.save()
        return clash

    # (a) A valid ClashRound row can be created and persists.
    def test_clash_round_creates_and_persists(self) -> None:
        from world.combat.models import ClashRound

        clash = self._make_clash()
        round_row = ClashRound.objects.create(
            clash=clash,
            round_number=1,
            pc_progress_delta=2,
            npc_progress_delta=-1,
            progress_after=2,
        )
        fetched = ClashRound.objects.get(pk=round_row.pk)
        self.assertEqual(fetched.clash_id, clash.pk)
        self.assertEqual(fetched.round_number, 1)
        self.assertEqual(fetched.pc_progress_delta, 2)
        self.assertEqual(fetched.npc_progress_delta, -1)
        self.assertEqual(fetched.progress_after, 2)

    # (b) UniqueConstraint on (clash, round_number) rejects a duplicate.
    def test_unique_constraint_rejects_duplicate_round(self) -> None:
        from django.db import IntegrityError

        from world.combat.models import ClashRound

        clash = self._make_clash()
        ClashRound.objects.create(
            clash=clash,
            round_number=1,
            pc_progress_delta=1,
            npc_progress_delta=0,
            progress_after=1,
        )
        with self.assertRaises(IntegrityError):
            ClashRound.objects.create(
                clash=clash,
                round_number=1,
                pc_progress_delta=2,
                npc_progress_delta=-1,
                progress_after=2,
            )

    # (c) Two ClashRound rows with the same round_number but different clashes are allowed.
    def test_same_round_number_different_clashes_allowed(self) -> None:
        from world.combat.models import ClashRound

        clash_a = self._make_clash()
        clash_b = self._make_clash()
        row_a = ClashRound.objects.create(
            clash=clash_a,
            round_number=1,
            pc_progress_delta=1,
            npc_progress_delta=0,
            progress_after=1,
        )
        row_b = ClashRound.objects.create(
            clash=clash_b,
            round_number=1,
            pc_progress_delta=-1,
            npc_progress_delta=2,
            progress_after=-1,
        )
        self.assertNotEqual(row_a.clash_id, row_b.clash_id)
        self.assertEqual(row_a.round_number, row_b.round_number)


class ClashContributionModelTests(TestCase):
    """Tests for the ClashContribution per-PC-per-round audit record.

    Builds Clash/ClashRound dependencies inline following the existing pattern.
    """

    def setUp(self) -> None:
        from actions.models import ConsequencePool
        from world.character_sheets.factories import CharacterSheetFactory
        from world.combat.constants import OpponentTier
        from world.combat.models import Clash, ClashRound, CombatEncounter, CombatOpponent
        from world.traits.factories import CheckOutcomeFactory

        self.encounter = CombatEncounter.objects.create()
        self.opponent = CombatOpponent.objects.create(
            encounter=self.encounter,
            tier=OpponentTier.MOOK,
            name="Contribution Test Opponent",
            health=50,
            max_health=50,
        )
        self.resolution_pool = ConsequencePool.objects.create(name="ContribTestResolutionPool")
        self.clash = Clash.objects.create(
            encounter=self.encounter,
            npc_opponent=self.opponent,
            resolution_consequence_pool=self.resolution_pool,
            flavor=ClashFlavor.CLASH,
            progress=0,
            pc_win_threshold=5,
            npc_win_threshold=-5,
            started_round=1,
        )
        self.clash_round = ClashRound.objects.create(
            clash=self.clash,
            round_number=1,
            pc_progress_delta=1,
            npc_progress_delta=0,
            progress_after=1,
        )
        self.sheet = CharacterSheetFactory()
        self.check_outcome = CheckOutcomeFactory(name="ContribTestSuccess", success_level=1)

    def _make_contribution(self, sheet=None, clash_round=None, **kwargs):
        """Helper: create a ClashContribution with required fields."""
        from world.combat.constants import ClashActionSlot
        from world.combat.models import ClashContribution

        defaults = {
            "clash_round": clash_round or self.clash_round,
            "character": sheet or self.sheet,
            "action_slot": ClashActionSlot.FOCUSED,
            "anima_committed": 10,
            "check_outcome": self.check_outcome,
            "progress_delta": 1,
        }
        defaults.update(kwargs)
        return ClashContribution.objects.create(**defaults)

    # (a) A valid ClashContribution row persists.
    def test_valid_contribution_persists(self) -> None:
        from world.combat.models import ClashContribution

        contrib = self._make_contribution()
        fetched = ClashContribution.objects.get(pk=contrib.pk)
        self.assertEqual(fetched.clash_round_id, self.clash_round.pk)
        self.assertEqual(fetched.character_id, self.sheet.pk)
        self.assertEqual(fetched.anima_committed, 10)
        self.assertEqual(fetched.progress_delta, 1)
        self.assertFalse(fetched.was_overburn)
        self.assertFalse(fetched.was_audere)
        self.assertEqual(fetched.soulfray_severity_accrued, 0)

    # (b) UniqueConstraint(clash_round, character) rejects a second contribution
    # from the same character in the same ClashRound.
    def test_unique_constraint_rejects_duplicate_character_per_round(self) -> None:
        from django.db import IntegrityError

        self._make_contribution()
        with self.assertRaises(IntegrityError):
            self._make_contribution()

    # (c) Two contributions from the same character in different ClashRounds are allowed.
    def test_same_character_different_rounds_allowed(self) -> None:
        from world.combat.models import ClashRound

        round_2 = ClashRound.objects.create(
            clash=self.clash,
            round_number=2,
            pc_progress_delta=2,
            npc_progress_delta=-1,
            progress_after=3,
        )
        contrib_1 = self._make_contribution()
        contrib_2 = self._make_contribution(clash_round=round_2)
        self.assertNotEqual(contrib_1.clash_round_id, contrib_2.clash_round_id)
        self.assertEqual(contrib_1.character_id, contrib_2.character_id)


class TechniqueLockApplyingTests(TestCase):
    """Tests for Technique.is_lock_applying property."""

    # (a) A Technique with an applied ConditionTemplate flagged is_clash_lock=True
    # returns is_lock_applying=True.
    def test_technique_with_lock_condition_is_lock_applying(self) -> None:
        from world.conditions.factories import ConditionTemplateFactory
        from world.magic.factories import TechniqueAppliedConditionFactory, TechniqueFactory

        technique = TechniqueFactory(damage_profile=False)
        lock_condition = ConditionTemplateFactory(name="LockTestCondition", is_clash_lock=True)
        TechniqueAppliedConditionFactory(technique=technique, condition=lock_condition)
        fresh = technique.__class__.objects.get(pk=technique.pk)
        self.assertTrue(fresh.is_lock_applying)

    # (b) A Technique with no lock-flagged applied condition returns is_lock_applying=False.
    def test_technique_without_lock_condition_is_not_lock_applying(self) -> None:
        from world.conditions.factories import ConditionTemplateFactory
        from world.magic.factories import TechniqueAppliedConditionFactory, TechniqueFactory

        technique = TechniqueFactory(damage_profile=False)
        normal_condition = ConditionTemplateFactory(name="NormalTestCondition", is_clash_lock=False)
        TechniqueAppliedConditionFactory(technique=technique, condition=normal_condition)
        fresh = technique.__class__.objects.get(pk=technique.pk)
        self.assertFalse(fresh.is_lock_applying)


class ClashFactoriesTests(TestCase):
    """Verify that each clash factory produces a valid, persisted row.

    Each factory must produce a row that passes full_clean() — the
    per-flavor Clash subclass factories are the critical case because
    Clash.clean() enforces the flavor↔field couplings.
    """

    def test_strain_config_factory_valid(self) -> None:
        from world.combat.factories import StrainConfigFactory

        cfg = StrainConfigFactory()
        self.assertIsNotNone(cfg.pk)
        cfg.full_clean()

    def test_clash_config_factory_valid(self) -> None:
        from world.combat.factories import ClashConfigFactory

        cfg = ClashConfigFactory()
        self.assertIsNotNone(cfg.pk)
        cfg.full_clean()

    def test_clash_factory_default_flavor(self) -> None:
        """Default ClashFactory produces a CLASH-flavor row that passes full_clean()."""
        from world.combat.factories import ClashFactory

        clash = ClashFactory()
        self.assertIsNotNone(clash.pk)
        self.assertEqual(clash.flavor, ClashFlavor.CLASH)
        clash.full_clean()

    def test_lock_clash_factory_valid(self) -> None:
        """LockClashFactory produces a LOCK-flavor Clash that passes full_clean()."""
        from world.combat.factories import LockClashFactory

        clash = LockClashFactory()
        self.assertIsNotNone(clash.pk)
        self.assertEqual(clash.flavor, ClashFlavor.LOCK)
        self.assertIsNotNone(clash.lock_pc_role)
        self.assertIsNone(clash.npc_win_threshold)
        clash.full_clean()

    def test_ward_clash_factory_valid(self) -> None:
        """WardClashFactory produces a WARD-flavor Clash that passes full_clean()."""
        from world.combat.factories import WardClashFactory

        clash = WardClashFactory()
        self.assertIsNotNone(clash.pk)
        self.assertEqual(clash.flavor, ClashFlavor.WARD)
        self.assertIsNotNone(clash.ward_ends_on_round)
        self.assertIsNone(clash.npc_win_threshold)
        clash.full_clean()

    def test_break_clash_factory_valid(self) -> None:
        """BreakClashFactory produces a BREAK-flavor Clash that passes full_clean()."""
        from world.combat.factories import BreakClashFactory

        clash = BreakClashFactory()
        self.assertIsNotNone(clash.pk)
        self.assertEqual(clash.flavor, ClashFlavor.BREAK)
        self.assertIsNone(clash.npc_win_threshold)
        self.assertIsNone(clash.lock_pc_role)
        self.assertIsNone(clash.ward_ends_on_round)
        clash.full_clean()

    def test_clash_round_factory_valid(self) -> None:
        from world.combat.factories import ClashRoundFactory

        clash_round = ClashRoundFactory()
        self.assertIsNotNone(clash_round.pk)
        clash_round.full_clean()

    def test_clash_contribution_factory_valid(self) -> None:
        from world.combat.factories import ClashContributionFactory

        contrib = ClashContributionFactory()
        self.assertIsNotNone(contrib.pk)
        contrib.full_clean()


class StrainConfigTests(TestCase):
    def test_strain_config_fatigue_ratio_defaults(self):
        """StrainConfig singleton has correct default fatigue ratio fields."""
        from world.combat.factories import StrainConfigFactory

        cfg = StrainConfigFactory()
        self.assertEqual(cfg.base_anima_fatigue_ratio, 25)
        self.assertEqual(cfg.strain_anima_fatigue_ratio, 50)


class ThreatPoolEntryClashValidationTests(TestCase):
    """Tests for ThreatPoolEntry.clean() clash-field coupling validation."""

    def setUp(self) -> None:
        from world.combat.factories import ThreatPoolFactory

        self.pool = ThreatPoolFactory()

    # (a) is_lock_applying=True without clash_break_free_force fails full_clean().
    def test_lock_applying_without_break_free_force_fails(self) -> None:
        from django.core.exceptions import ValidationError

        from world.combat.factories import ThreatPoolEntryFactory

        entry = ThreatPoolEntryFactory.build(
            pool=self.pool,
            is_lock_applying=True,
            clash_break_free_force=None,
        )
        with self.assertRaises(ValidationError) as ctx:
            entry.full_clean()
        self.assertIn("clash_break_free_force", ctx.exception.message_dict)

    # (b) is_lock_applying=True with clash_break_free_force set passes full_clean().
    def test_lock_applying_with_break_free_force_passes(self) -> None:
        from world.combat.factories import ThreatPoolEntryFactory

        entry = ThreatPoolEntryFactory.build(
            pool=self.pool,
            is_lock_applying=True,
            clash_break_free_force=8,
        )
        entry.full_clean()

    # (c) is_sustained_attack=True without sustained_duration_rounds fails full_clean().
    def test_sustained_without_duration_rounds_fails(self) -> None:
        from django.core.exceptions import ValidationError

        from world.combat.factories import ThreatPoolEntryFactory

        entry = ThreatPoolEntryFactory.build(
            pool=self.pool,
            is_sustained_attack=True,
            sustained_duration_rounds=None,
        )
        with self.assertRaises(ValidationError) as ctx:
            entry.full_clean()
        self.assertIn("sustained_duration_rounds", ctx.exception.message_dict)

    # (d) is_sustained_attack=True with sustained_duration_rounds set passes full_clean().
    def test_sustained_with_duration_rounds_passes(self) -> None:
        from world.combat.factories import ThreatPoolEntryFactory

        entry = ThreatPoolEntryFactory.build(
            pool=self.pool,
            is_sustained_attack=True,
            sustained_duration_rounds=3,
        )
        entry.full_clean()
